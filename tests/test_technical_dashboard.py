"""Focused tests for the separate local T2/T3 dashboard surface."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

import youtube_clipper.web_dashboard as web_dashboard


def _payload(input_path: Path) -> dict[str, object]:
    return {
        "phase": "t3",
        "input_path": str(input_path),
        "whisper_model": "small",
        "device": "cpu",
        "language": "pt",
        "scene_threshold": 29.5,
        "min_scene_len": 0.8,
        "vertical_mode": "blur_background",
        "blur_sigma": 14.0,
        "subtitle_font_name": "Roboto",
        "subtitle_font_size": 76,
        "subtitle_margin_v": 380,
        "analytical_overlay": True,
        "overlay_text": "ANÁLISE técnica do argumento",
        "narration_path": None,
        "template_variant": "variant_dashboard_test",
    }


def _post(base_url: str, payload: dict[str, object], request_id: str | None = None):
    request = urllib.request.Request(
        f"{base_url}/api/cortes/run",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Request-ID": request_id or f"technical-{uuid.uuid4().hex}",
        },
        method="POST",
    )
    return urllib.request.urlopen(request)


def _install_pipeline_measurement_stubs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[dict[str, object], list[Path]]:
    captured: dict[str, object] = {}
    verified: list[Path] = []

    def fake_pipeline(**kwargs):
        captured.update(kwargs)
        render_path = tmp_path / f"render-{uuid.uuid4().hex}.mp4"
        render_path.write_bytes(b"technical-render" * 128)
        return {
            "run_id": kwargs["run_id"],
            "render_path": str(render_path),
            "subtitles_path": str(tmp_path / "captions.ass"),
            "report_path": str(tmp_path / "report.md"),
        }

    def fake_verify(run_dir):
        verified.append(Path(run_dir))
        return {
            "overall_passed": False,
            "total_checks": 12,
            "passed_checks": 10,
            "failed_checks": 2,
        }

    monkeypatch.setattr(web_dashboard, "run_full_pipeline", fake_pipeline)
    monkeypatch.setattr(web_dashboard, "verify_run", fake_verify)
    return captured, verified


def test_get_technical_page_is_separate_from_quick_clipper(
    dashboard_server: str,
) -> None:
    with urllib.request.urlopen(f"{dashboard_server}/technical") as response:
        assert response.status == 200
        technical = response.read().decode("utf-8")
    with urllib.request.urlopen(f"{dashboard_server}/") as response:
        quick = response.read().decode("utf-8")

    assert 'id="technicalForm"' in technical
    assert 'name="input_path"' in technical
    assert 'name="whisper_model"' in technical
    assert 'name="scene_threshold"' in technical
    assert 'name="subtitle_font_name"' in technical
    assert 'name="analytical_overlay"' in technical
    assert "fetch('/api/cortes/run'" in technical
    assert "/api/status/" in technical
    assert technical.count('class="stage" data-stage=') == 9
    assert 'id="technicalForm"' not in quick
    assert 'href="/technical"' in quick


def test_run_t3_registers_child_measures_and_exports_unique_download(
    dashboard_server: str,
    dummy_video_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured, verified = _install_pipeline_measurement_stubs(monkeypatch, tmp_path)
    request_id = f"technical-t3-{uuid.uuid4().hex}"

    with _post(dashboard_server, _payload(dummy_video_file), request_id) as response:
        assert response.status == 200
        assert response.headers.get("Cache-Control") == "no-store"
        data = json.loads(response.read().decode("utf-8"))

    assert captured["request_id"] == request_id
    assert captured["input_source"] == dummy_video_file.resolve()
    assert captured["require_editorial_transformation"] is True
    assert captured["subtitle_font_name"] == "Roboto"
    assert captured["scene_threshold"] == 29.5
    assert captured["template_variant"] == "variant_dashboard_test"
    assert verified == [Path.cwd() / "runs" / captured["run_id"]]

    expected_measurement = {
        "overall_passed": False,
        "total_checks": 12,
        "passed_checks": 10,
        "failed_checks": 2,
    }
    receipt = data["render_receipt"]
    assert data["overall_status"] == "measured"
    assert receipt["status"] == "measured"
    assert receipt["verification"] == expected_measurement
    assert receipt["report_snapshot"]["label"] == "Snapshot interno não verificado"
    assert Path(data["output_path"]).parent == Path.cwd() / "media_workspace"
    assert Path(data["output_path"]).is_file()

    with urllib.request.urlopen(f"{dashboard_server}{data['download_url']}") as download:
        assert download.status == 200
        assert download.read().startswith(b"technical-render")

    with urllib.request.urlopen(
        f"{dashboard_server}/api/status/{request_id}"
    ) as status_response:
        status = json.loads(status_response.read().decode("utf-8"))
    assert captured["run_id"] in status["run_ids"]
    assert any(event["action"] == "pipeline.verify" for event in status["events"])


def test_t2_derives_non_editorial_semantics(
    dashboard_server: str,
    dummy_video_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured, _ = _install_pipeline_measurement_stubs(monkeypatch, tmp_path)
    payload = _payload(dummy_video_file)
    payload.update(
        {
            "phase": "t2",
            "analytical_overlay": False,
            "overlay_text": None,
            "template_variant": "variant_default",
        }
    )

    with _post(dashboard_server, payload) as response:
        assert response.status == 200
        response.read()

    assert captured["require_editorial_transformation"] is False
    assert captured["analytical_overlay"] is False
    assert captured["template_variant"] == "variant_default"


@pytest.mark.parametrize(
    "override",
    [
        {"input_path": "https://www.youtube.com/watch?v=abc"},
        {"phase": "t3", "analytical_overlay": False, "overlay_text": None},
        {"phase": "t3", "template_variant": "variant_default"},
        {"vertical_mode": "crop_center", "blur_sigma": 12},
        {"unapplied_toggle": True},
        {"subtitle_font_size": True},
    ],
)
def test_run_rejects_invalid_or_unapplied_configuration(
    dashboard_server: str,
    dummy_video_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    override: dict[str, object],
) -> None:
    captured, _ = _install_pipeline_measurement_stubs(monkeypatch, tmp_path)
    payload = _payload(dummy_video_file)
    payload.update(override)

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _post(dashboard_server, payload)

    assert exc_info.value.code == 400
    body = json.loads(exc_info.value.read().decode("utf-8"))
    assert body["success"] is False
    assert body["field"]
    assert captured == {}


def test_run_rejects_existing_non_media_input(
    dashboard_server: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured, _ = _install_pipeline_measurement_stubs(monkeypatch, tmp_path)
    text_file = tmp_path / "not-media.txt"
    text_file.write_text("not video", encoding="utf-8")
    payload = _payload(text_file)

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _post(dashboard_server, payload)

    assert exc_info.value.code == 400
    assert captured == {}
