"""Physical UI-2 preview, identity, invalidation, and seek contracts."""

from __future__ import annotations

import base64
import json
import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

import youtube_clipper.web_dashboard as web_dashboard
from cortes.log import run_cmd, run_context
from youtube_clipper.project_store import DomainConflictError, ProjectStore


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "panel_preview_identity"
    / "source_three_candidates.mp4"
).resolve()


def _analysis_result() -> dict[str, Any]:
    colors = (("Vermelho", 0.0, 3.0), ("Verde", 3.0, 6.0), ("Azul", 6.0, 9.0))
    return {
        "success": True,
        "clips": [
            {
                "rank": rank,
                "title": title,
                "start_time": start,
                "end_time": end,
                "score": 100 - rank,
            }
            for rank, (title, start, end) in enumerate(colors, start=1)
        ],
    }


def _json_request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base_url + path,
        data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _asset_request(
    base_url: str,
    path: str,
    *,
    byte_range: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    headers = {"Range": byte_range} if byte_range else {}
    request = urllib.request.Request(base_url + path, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.status, dict(response.headers.items()), response.read()


def _color_signature(preview_path: Path, run_id: str) -> tuple[float, float, float]:
    with run_context(run_id=run_id, actions=[], component="tests.ui2"):
        result = run_cmd(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostdin",
                "-i",
                str(preview_path),
                "-vf",
                "signalstats,metadata=print",
                "-frames:v",
                "1",
                "-f",
                "null",
                "-",
            ],
            stage="verify",
        )
    assert result.returncode == 0

    def value(channel: str) -> float:
        match = re.search(
            rf"lavfi\.signalstats\.{channel}AVG=([0-9.]+)",
            result.stderr,
        )
        assert match, f"missing {channel} average in FFmpeg output"
        return float(match.group(1))

    return value("Y"), value("U"), value("V")


def _browser_video_contract(
    base_url: str,
    preview_urls: list[str],
    tmp_path: Path,
) -> list[dict[str, Any]]:
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if chrome is None:
        pytest.skip("Chrome/Chromium is required for the UI-2 browser proof")
    sources = json.dumps([base_url + url for url in preview_urls])
    proof = tmp_path / "ui2-browser-proof.html"
    proof.write_text(
        f"""<!doctype html>
<meta charset="utf-8">
<title>UI-2 browser proof</title>
<main id="players"></main>
<script>
const sources = {sources};
const players = sources.map((src, index) => {{
  const video = document.createElement("video");
  video.id = "clip-" + (index + 1);
  video.controls = true;
  video.preload = "metadata";
  video.src = src;
  document.getElementById("players").append(video);
  video.load();
  return video;
}});
const result = players.map(video => ({{
  id: video.id,
  resolvedSrc: video.currentSrc || video.src
}}));
document.body.dataset.result = btoa(JSON.stringify(result));
document.title = "UI2_READY";
</script>
""",
        encoding="utf-8",
    )
    with run_context(
        run_id="run_ui2_browser_contract_20260728a",
        actions=[],
        component="tests.ui2.browser",
    ):
        result = run_cmd(
            [
                chrome,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--allow-file-access-from-files",
                "--disable-web-security",
                "--disable-features=BlockInsecurePrivateNetworkRequests",
                "--autoplay-policy=no-user-gesture-required",
                "--virtual-time-budget=10000",
                "--dump-dom",
                proof.as_uri(),
            ],
            stage="verify",
        )
    assert result.returncode == 0
    encoded = re.search(r'data-result="([^"]+)"', result.stdout)
    assert encoded, result.stdout[-2000:]
    return json.loads(base64.b64decode(encoded.group(1)).decode("utf-8"))


def test_three_physical_previews_have_distinct_identity_color_and_range_seek(
    dashboard_server: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        web_dashboard,
        "extract_transcript_and_analyze",
        lambda *args, **kwargs: _analysis_result(),
    )
    _, created = _json_request(
        dashboard_server,
        "/api/v1/projects",
        method="POST",
        payload={
            "name": "Prova física UI-2",
            "source": {"kind": "local", "uri": str(FIXTURE)},
        },
    )
    project_id = created["project"]["project_id"]
    _, analyzed = _json_request(
        dashboard_server,
        f"/api/v1/projects/{project_id}/analysis-jobs",
        method="POST",
        payload={},
    )

    previews = []
    signatures = []
    for index, clip in enumerate(analyzed["clips"], start=1):
        status, generated = _json_request(
            dashboard_server,
            f"/api/v1/clips/{clip['clip_id']}/preview-jobs",
            method="POST",
            payload={},
        )
        assert status == 201
        assert generated["job"]["state"] == "completed"
        assert generated["clip"]["preview_status"] == "ready"
        preview = generated["preview"]
        assert preview["clip_id"] == clip["clip_id"]
        assert preview["width"] == 360
        assert preview["height"] == 640
        previews.append(preview)

        full_status, full_headers, full_body = _asset_request(
            dashboard_server, preview["url"]
        )
        assert full_status == 200
        assert full_headers["Accept-Ranges"] == "bytes"
        assert "immutable" in full_headers["Cache-Control"]
        local_preview = tmp_path / f"preview-{index}.mp4"
        local_preview.write_bytes(full_body)
        signatures.append(
            _color_signature(
                local_preview,
                f"run_ui2_color_contract_{index}_20260728a",
            )
        )

        range_status, range_headers, range_body = _asset_request(
            dashboard_server,
            preview["url"],
            byte_range="bytes=0-99",
        )
        assert range_status == 206
        assert range_headers["Content-Range"].startswith("bytes 0-99/")
        assert len(range_body) == 100
        assert range_body == full_body[:100]

    assert len({item["asset_id"] for item in previews}) == 3
    assert len({item["url"] for item in previews}) == 3
    assert len({item["sha256"] for item in previews}) == 3
    red, green, blue = signatures
    assert red[2] > red[1] + 60
    assert green[0] > red[0] + 10 and green[0] > blue[0] + 10
    assert blue[1] > blue[2] + 60

    browser_media = _browser_video_contract(
        dashboard_server,
        [item["url"] for item in previews],
        tmp_path,
    )
    assert len({item["resolvedSrc"] for item in browser_media}) == 3
    assert all(item["resolvedSrc"].startswith(dashboard_server) for item in browser_media)

    first_clip_id = analyzed["clips"][0]["clip_id"]
    _, changed = _json_request(
        dashboard_server,
        f"/api/v1/clips/{first_clip_id}",
        method="PATCH",
        payload={"start_ms": 100, "end_ms": 2900},
    )
    assert changed["clip"]["plan_version"] == 2
    assert changed["clip"]["preview_status"] == "stale"
    with pytest.raises(urllib.error.HTTPError) as stale:
        _asset_request(dashboard_server, previews[0]["url"])
    assert stale.value.code == 409

    _, untouched = _json_request(
        dashboard_server,
        f"/api/v1/clips/{analyzed['clips'][1]['clip_id']}",
    )
    assert untouched["clip"]["preview_status"] == "ready"

    _, regenerated = _json_request(
        dashboard_server,
        f"/api/v1/clips/{first_clip_id}/preview-jobs",
        method="POST",
        payload={},
    )
    assert regenerated["preview"]["version"] == 2
    assert regenerated["preview"]["url"] != previews[0]["url"]
    assert regenerated["clip"]["preview_status"] == "ready"


def test_asset_integrity_mutation_is_rejected(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects.sqlite3", tmp_path / "workspace")
    project = store.create_project(
        name="Mutação UI-2",
        source_uri=str(FIXTURE),
        source_kind="local",
    )
    analysis = store.create_analysis(project_id=project["project_id"])
    clip = store.finish_analysis(
        analysis_id=analysis["analysis_id"],
        result={"success": True, "clips": _analysis_result()["clips"][:1]},
    )[0]
    media = tmp_path / "preview.mp4"
    media.write_bytes(b"valid-preview-bytes")
    asset = store.add_asset(
        clip_id=clip["clip_id"],
        kind="preview",
        source_path=media,
        mime_type="video/mp4",
    )

    _, immutable_path = store.resolve_asset_file(asset["asset_id"], version=1)
    immutable_path.write_bytes(b"mutated-preview-bytes")

    with pytest.raises(DomainConflictError, match="integrity"):
        store.resolve_asset_file(asset["asset_id"], version=1)
