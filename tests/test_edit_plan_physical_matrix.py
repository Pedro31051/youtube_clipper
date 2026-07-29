"""Physical proof that every enabled editor control changes rendered media."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import cortes.preview as preview_module
from cortes.ingest import probe_video_metadata
from cortes.log import compute_sha256, run_cmd
from cortes.preview import generate_clip_preview


def _source(path: Path) -> Path:
    result = run_cmd(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=30:duration=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=3",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        stage="test-fixture",
        audit=False,
    )
    assert result.returncode == 0, result.stderr
    return path


def _plan() -> dict:
    return {
        "schema_version": "1.0.0",
        "plan_version": 1,
        "timeline": {"start_ms": 0, "end_ms": 1000, "duration_ms": 1000},
        "layout": {
            "mode": "blur_background",
            "crop_focus": "center",
            "blur_sigma": 4,
            "overlay_position": "top",
        },
        "captions": {"enabled": False, "theme": "classic", "position": "bottom"},
        "audio": {
            "include_source": True,
            "normalize": False,
            "narration_type": "none",
        },
        "editorial": {
            "overlay_enabled": False,
            "overlay_text": None,
            "template_variant": "variant_default",
        },
        "output": {"aspect_ratio": "9:16", "resolution": "720x1280"},
    }


def _render(
    source: Path,
    plan: dict,
    name: str,
    *,
    start_ms: int = 0,
    end_ms: int = 1000,
    profile: str = "preview",
) -> dict:
    return generate_clip_preview(
        input_source=str(source),
        start_ms=start_ms,
        end_ms=end_ms,
        edit_plan=plan,
        clip_id=f"clp_{name}",
        run_id=f"run_final_matrix_{name}",
        profile=profile,
    )


def test_enabled_controls_produce_detectable_physical_differences(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    source = _source(tmp_path / "control-source.mp4")
    baseline_plan = _plan()
    baseline = _render(source, baseline_plan, "baseline")
    baseline_hash = compute_sha256(Path(baseline["media_path"]))

    timeline = _render(
        source, deepcopy(baseline_plan), "timeline", start_ms=1000, end_ms=2000
    )

    square_plan = deepcopy(baseline_plan)
    square_plan["output"]["aspect_ratio"] = "1:1"
    square_plan["output"]["resolution"] = "1080x1080"
    square = _render(source, square_plan, "square")

    crop_plan = deepcopy(baseline_plan)
    crop_plan["layout"]["mode"] = "crop_center"
    crop_plan["layout"]["crop_focus"] = "left"
    crop = _render(source, crop_plan, "crop")

    blur_plan = deepcopy(baseline_plan)
    blur_plan["layout"]["blur_sigma"] = 20
    blur = _render(source, blur_plan, "blur")

    overlay_top_plan = deepcopy(baseline_plan)
    overlay_top_plan["editorial"].update(
        {"overlay_enabled": True, "overlay_text": "PROVA FÍSICA"}
    )
    overlay_top = _render(source, overlay_top_plan, "overlay_top")
    overlay_bottom_plan = deepcopy(overlay_top_plan)
    overlay_bottom_plan["layout"]["overlay_position"] = "bottom"
    overlay_bottom = _render(source, overlay_bottom_plan, "overlay_bottom")

    muted_plan = deepcopy(baseline_plan)
    muted_plan["audio"]["include_source"] = False
    muted = _render(source, muted_plan, "muted")

    normalized_plan = deepcopy(baseline_plan)
    normalized_plan["audio"]["normalize"] = True
    normalized = _render(source, normalized_plan, "normalized")

    full_hd_plan = deepcopy(baseline_plan)
    full_hd_plan["output"]["resolution"] = "1080x1920"
    full_hd = _render(source, full_hd_plan, "full_hd", profile="final")
    hd = _render(source, baseline_plan, "hd", profile="final")

    outputs = {
        "timeline": timeline,
        "aspect": square,
        "layout_crop": crop,
        "blur": blur,
        "overlay_top": overlay_top,
        "overlay_bottom": overlay_bottom,
        "audio_muted": muted,
        "normalization": normalized,
        "resolution": full_hd,
    }
    assert all(
        compute_sha256(Path(result["media_path"])) != baseline_hash
        for result in outputs.values()
    )
    assert compute_sha256(Path(overlay_top["media_path"])) != compute_sha256(
        Path(overlay_bottom["media_path"])
    )
    assert probe_video_metadata(Path(square["media_path"]))["width"] == 480
    assert probe_video_metadata(Path(muted["media_path"]))["audio_codec"] == "none"
    assert probe_video_metadata(Path(baseline["media_path"]))["audio_codec"] == "aac"
    assert (hd["width"], hd["height"]) == (720, 1280)
    assert (full_hd["width"], full_hd["height"]) == (1080, 1920)

    for result in [baseline, *outputs.values(), hd]:
        metadata = result["render_metadata"]
        assert metadata["encoder_used"] in {"h264_nvenc", "libx264"}
        assert metadata["frame_count"] > 0
        assert metadata["processing_seconds"] > 0
        assert metadata["processing_ratio"] is not None
        assert metadata["applied_plan"]


def test_cpu_path_executes_physical_ffmpeg_with_the_same_plan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(preview_module, "detect_h264_encoder", lambda: "libx264")
    source = _source(tmp_path / "cpu-source.mp4")

    result = _render(source, _plan(), "cpu_physical")
    metadata = result["render_metadata"]

    assert Path(result["media_path"]).stat().st_size > 1_000
    assert probe_video_metadata(Path(result["media_path"]))["video_codec"] == "h264"
    assert metadata["encoder_detected"] == "libx264"
    assert metadata["encoder_used"] == "libx264"
    assert metadata["fallback_reason"] is None


def test_nvenc_first_frame_failure_has_one_physical_cpu_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "")
    monkeypatch.setattr(
        preview_module,
        "detect_h264_encoder",
        lambda: "h264_nvenc",
    )
    source = _source(tmp_path / "fallback-source.mp4")

    result = _render(source, _plan(), "nvenc_fallback")
    metadata = result["render_metadata"]
    commands = (
        tmp_path
        / "runs"
        / "run_final_matrix_nvenc_fallback"
        / "commands.log"
    ).read_text(encoding="utf-8")

    assert metadata["encoder_detected"] == "h264_nvenc"
    assert metadata["encoder_used"] == "libx264"
    assert metadata["fallback_reason"]
    assert commands.count("h264_nvenc") == 1
    assert commands.count("libx264") == 1
