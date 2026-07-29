"""Focused unit tests for the dashboard-to-cortes pipeline contract."""

from __future__ import annotations

import contextlib
import inspect
import pathlib
from typing import Any, Dict

import cortes.pipeline as pipeline_module
import cortes.render as render_module


def _stage_stub(
    calls: Dict[str, Dict[str, Any]],
    name: str,
    result: Dict[str, Any],
):
    def stub(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        calls[name] = {"args": args, "kwargs": kwargs}
        return result

    return stub


def test_run_full_pipeline_exposes_dashboard_option_names() -> None:
    parameters = inspect.signature(pipeline_module.run_full_pipeline).parameters

    expected_names = {
        "request_id",
        "language",
        "scene_threshold",
        "min_scene_len",
        "subtitle_font_name",
        "subtitle_font_size",
        "subtitle_margin_v",
        "blur_sigma",
        "analytical_overlay",
        "overlay_text",
        "narration_path",
        "template_variant",
    }

    assert expected_names <= parameters.keys()


def test_run_full_pipeline_forwards_dashboard_options(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    calls: Dict[str, Dict[str, Any]] = {}
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(
        '{"start_ms": 1000, "end_ms": 9000}\n',
        encoding="utf-8",
    )

    @contextlib.contextmanager
    def fake_run_context(**kwargs: Any):
        calls["run_context"] = {"args": (), "kwargs": kwargs}
        yield "run_contract_active"

    monkeypatch.setattr(pipeline_module, "run_context", fake_run_context)
    monkeypatch.setattr(
        pipeline_module,
        "action_span",
        lambda *args, **kwargs: contextlib.nullcontext(),
    )
    monkeypatch.setattr(
        pipeline_module,
        "get_run_dir",
        lambda run_id: tmp_path / "runs" / run_id,
    )
    monkeypatch.setattr(
        pipeline_module,
        "run_ingest",
        _stage_stub(calls, "ingest", {"video_path": "video.mp4"}),
    )
    monkeypatch.setattr(
        pipeline_module,
        "run_transcribe",
        _stage_stub(calls, "transcribe", {"transcript_path": "transcript.json"}),
    )
    monkeypatch.setattr(
        pipeline_module,
        "detect_scenes_stage",
        _stage_stub(calls, "scenes", {"scenes_path": "scenes.json"}),
    )
    monkeypatch.setattr(
        pipeline_module,
        "select_clip_stage",
        _stage_stub(
            calls,
            "select",
            {"selection_path": str(selection_path)},
        ),
    )
    monkeypatch.setattr(
        pipeline_module,
        "run_cut",
        _stage_stub(calls, "cut", {"cut_path": "cut.mp4"}),
    )
    monkeypatch.setattr(
        pipeline_module,
        "run_subtitles",
        _stage_stub(calls, "subtitles", {"subtitles_path": "subtitles.ass"}),
    )
    monkeypatch.setattr(
        pipeline_module,
        "run_audio",
        _stage_stub(calls, "audio", {"audio_path": "audio.mp4"}),
    )
    monkeypatch.setattr(
        pipeline_module,
        "run_render",
        _stage_stub(calls, "render", {"render_path": "short.mp4"}),
    )
    monkeypatch.setattr(
        pipeline_module,
        "run_report",
        _stage_stub(calls, "report", {"report_path": "report.md"}),
    )

    narration_path = tmp_path / "narration.wav"
    result = pipeline_module.run_full_pipeline(
        "source.mp4",
        run_id="run_contract_requested",
        request_id="request-contract-123",
        whisper_model="medium",
        device="cpu",
        vertical_mode="blur_background",
        language="pt",
        scene_threshold=19.5,
        min_scene_len=1.25,
        subtitle_font_name="Montserrat",
        subtitle_font_size=92,
        subtitle_margin_v=360,
        blur_sigma=7.5,
        analytical_overlay=True,
        overlay_text="CONTEXTO",
        narration_path=narration_path,
        template_variant="variant_contract",
    )

    assert result["run_id"] == "run_contract_active"
    assert calls["run_context"]["kwargs"]["request_id"] == "request-contract-123"
    assert calls["transcribe"]["kwargs"] == {
        "run_id": "run_contract_active",
        "model_size": "medium",
        "device": "cpu",
        "language": "pt",
    }
    assert calls["scenes"]["kwargs"] == {
        "run_id": "run_contract_active",
        "threshold": 19.5,
        "min_scene_len": 1.25,
    }
    assert calls["subtitles"]["kwargs"]["font_name"] == "Montserrat"
    assert calls["subtitles"]["kwargs"]["font_size"] == 92
    assert calls["subtitles"]["kwargs"]["margin_v"] == 360
    assert calls["render"]["kwargs"]["mode"] == "blur_background"
    assert calls["render"]["kwargs"]["blur_sigma"] == 7.5
    assert calls["render"]["kwargs"]["analytical_overlay"] is True
    assert calls["render"]["kwargs"]["overlay_text"] == "CONTEXTO"
    assert calls["render"]["kwargs"]["narration_path"] == narration_path
    assert calls["render"]["kwargs"]["template_variant"] == "variant_contract"


def test_run_render_forwards_blur_sigma_to_vertical_renderer(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    input_media = tmp_path / "input.mp4"
    input_media.write_bytes(b"unit-test-media")
    captured: Dict[str, Any] = {}

    def fake_process_vertical_render(**kwargs: Any) -> Dict[str, Any]:
        captured.update(kwargs)
        return {
            "status": "ok",
            "render_path": str(kwargs["output_media"]),
            "metadata_path": str(kwargs["metadata_json"]),
            "evidence_paths": [],
        }

    monkeypatch.setattr(render_module, "process_vertical_render", fake_process_vertical_render)
    monkeypatch.setattr(
        render_module,
        "get_run_dir",
        lambda run_id: tmp_path / "runs" / str(run_id),
    )

    result = render_module.run_render.__wrapped__(
        input_media,
        run_id="run_render_contract",
        blur_sigma=6.25,
    )

    assert result["status"] == "ok"
    assert captured["blur_sigma"] == 6.25
    filtergraph = render_module.build_render_filtergraph.__wrapped__(
        mode="blur_background",
        sigma=captured["blur_sigma"],
    )
    assert "gblur=sigma=6.25" in filtergraph
