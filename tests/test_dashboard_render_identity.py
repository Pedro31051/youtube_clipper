"""Render identity bridge between the legacy UI and persistent UI-1 domain."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

import youtube_clipper.web_dashboard as web_dashboard


YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def _post(base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def _get(base_url: str, path: str) -> dict[str, Any]:
    with urllib.request.urlopen(f"{base_url}{path}") as response:
        return json.loads(response.read().decode("utf-8"))


def _analysis_result() -> dict[str, Any]:
    return {
        "success": True,
        "clips": [
            {
                "rank": 1,
                "start_time": 0.0,
                "end_time": 3.0,
                "duration": 3.0,
                "score": 90,
                "title": "Persistente",
                "summary": "Resumo",
                "transcript": "Trecho",
                "hashtags": ["#teste"],
                "start_timestamp": "00:00",
                "end_timestamp": "00:03",
            }
        ],
    }


def test_render_response_and_manifest_share_the_persisted_clip_identity(
    dashboard_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        web_dashboard,
        "extract_transcript_and_analyze",
        lambda *args, **kwargs: _analysis_result(),
    )

    def fake_pipeline(**kwargs: Any) -> str:
        output = Path(kwargs["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"physical-render" * 256)
        return str(output)

    monkeypatch.setattr(web_dashboard, "run_pipeline", fake_pipeline)
    monkeypatch.setattr(
        web_dashboard,
        "probe_video_metadata",
        lambda path: {
            "duration": 3.0,
            "width": 1080,
            "height": 1920,
            "fps": 30.0,
            "video_codec": "h264",
            "audio_codec": "aac",
            "audio_channels": 2,
            "file_size": Path(path).stat().st_size,
            "sha256": "sha256:test-render",
        },
    )

    analyzed = _post(
        dashboard_server,
        "/api/analyze",
        {"url": YOUTUBE_URL},
    )
    clip = analyzed["clips"][0]
    rendered = _post(
        dashboard_server,
        "/api/generate-clip",
        {
            "url": YOUTUBE_URL,
            "project_id": clip["project_id"],
            "analysis_id": clip["analysis_id"],
            "clip_id": clip["clip_id"],
            "start": 0,
            "end": 3,
            "format": "blur_background",
            "include_audio": True,
            "overlay_text": "Análise editorial",
            "confirmed_configuration": True,
        },
    )

    assert rendered["project_id"] == clip["project_id"]
    assert rendered["clip_id"] == clip["clip_id"]
    assert rendered["render_id"].startswith("rnd_")
    assert rendered["asset"]["asset_id"].startswith("ast_")
    assert rendered["asset"]["clip_id"] == clip["clip_id"]
    assert rendered["asset"]["url"].endswith("?v=1")
    assert "file_path" not in rendered["asset"]

    persisted = _get(dashboard_server, f"/api/v1/clips/{clip['clip_id']}")
    assert persisted["clip"]["status"] == "rendered"
    assert persisted["clip"]["assets"][0]["asset_id"] == rendered["asset"]["asset_id"]


def test_render_rejects_interval_that_differs_from_persisted_plan(
    dashboard_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        web_dashboard,
        "extract_transcript_and_analyze",
        lambda *args, **kwargs: _analysis_result(),
    )

    def fake_pipeline(**kwargs: Any) -> str:
        output = Path(kwargs["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"physical-render" * 256)
        return str(output)

    monkeypatch.setattr(web_dashboard, "run_pipeline", fake_pipeline)
    monkeypatch.setattr(
        web_dashboard,
        "probe_video_metadata",
        lambda path: {
            "duration": 2.5,
            "width": 1080,
            "height": 1920,
            "fps": 30.0,
            "video_codec": "h264",
            "audio_codec": "aac",
            "audio_channels": 2,
            "file_size": Path(path).stat().st_size,
            "sha256": "sha256:test-render",
        },
    )
    analyzed = _post(
        dashboard_server,
        "/api/analyze",
        {"url": YOUTUBE_URL},
    )
    clip = analyzed["clips"][0]

    with pytest.raises(urllib.error.HTTPError) as error:
        _post(
            dashboard_server,
            "/api/generate-clip",
            {
                "url": YOUTUBE_URL,
                "project_id": clip["project_id"],
                "clip_id": clip["clip_id"],
                "start": 0.5,
                "end": 3,
                "format": "blur_background",
                "include_audio": True,
                "overlay_text": "Análise editorial",
                "confirmed_configuration": True,
            },
        )
    assert error.value.code == 409
