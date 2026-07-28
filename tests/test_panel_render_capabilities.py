"""Physical CPU/GPU-agnostic proofs for supported dashboard controls."""

from __future__ import annotations

from pathlib import Path

from cortes.log import run_cmd
from cortes.preview import generate_clip_preview


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "panel_preview_identity"
    / "source_three_candidates.mp4"
).resolve()
CLIP_ID = "clp_33333333333333333333333333333333"
SOURCE_ID = "src_44444444444444444444444444444444"


def _plan(*, mode: str, overlay_text: str | None) -> dict:
    return {
        "schema_version": "1.0.0",
        "plan_version": 1,
        "clip_id": CLIP_ID,
        "source_id": SOURCE_ID,
        "timeline": {"start_ms": 0, "end_ms": 1500, "duration_ms": 1500},
        "layout": {
            "mode": mode,
            "crop_focus": "center",
            "blur_sigma": 12,
            "overlay_position": "top",
        },
        "captions": {"enabled": False, "theme": "classic", "position": "bottom"},
        "audio": {
            "include_source": False,
            "normalize": False,
            "narration_type": "none",
            "narration_path": None,
        },
        "editorial": {
            "overlay_enabled": overlay_text is not None,
            "overlay_text": overlay_text,
            "template_variant": "variant_default",
        },
        "output": {"aspect_ratio": "9:16", "resolution": "720x1280"},
    }


def _render(tmp_path: Path, run_id: str, *, mode: str, overlay: str | None) -> dict:
    return generate_clip_preview(
        input_source=str(FIXTURE),
        start_ms=0,
        end_ms=1500,
        edit_plan=_plan(mode=mode, overlay_text=overlay),
        clip_id=CLIP_ID,
        run_id=run_id,
        profile="preview",
    )


def _frame_md5(path: str) -> str:
    result = run_cmd(
        [
            "ffmpeg", "-v", "error", "-ss", "0.5", "-i", path,
            "-frames:v", "1", "-f", "md5", "-",
        ],
        audit=False,
    )
    assert result.returncode == 0
    return result.stdout.strip()


def test_layout_overlay_and_audio_controls_change_physical_media(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    crop = _render(tmp_path, "run_cap_crop", mode="crop_center", overlay=None)
    overlay = _render(
        tmp_path,
        "run_cap_overlay",
        mode="crop_center",
        overlay="OVERLAY FÍSICO",
    )
    blur = _render(tmp_path, "run_cap_blur", mode="blur_background", overlay=None)

    assert _frame_md5(crop["media_path"]) != _frame_md5(overlay["media_path"])
    assert _frame_md5(crop["media_path"]) != _frame_md5(blur["media_path"])
    audio_probe = run_cmd(
        [
            "ffprobe", "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=index", "-of", "csv=p=0",
            crop["media_path"],
        ],
        audit=False,
    )
    assert audio_probe.returncode == 0
    assert audio_probe.stdout.strip() == ""
    assert overlay["applied_features"]["overlay"] is True
    assert blur["applied_features"]["layout"] == "blur_background"
