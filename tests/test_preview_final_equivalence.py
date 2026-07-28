"""Physical equivalence proof for preview and final render profiles."""

from __future__ import annotations

from pathlib import Path

from cortes.preview import generate_clip_preview


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "panel_preview_identity"
    / "source_three_candidates.mp4"
).resolve()
CLIP_ID = "clp_55555555555555555555555555555555"


def _plan() -> dict:
    return {
        "schema_version": "1.0.0",
        "plan_version": 4,
        "clip_id": CLIP_ID,
        "source_id": "src_66666666666666666666666666666666",
        "timeline": {"start_ms": 3000, "end_ms": 4500, "duration_ms": 1500},
        "layout": {
            "mode": "crop_center",
            "crop_focus": "right",
            "blur_sigma": 12,
            "overlay_position": "bottom",
        },
        "captions": {"enabled": False, "theme": "classic", "position": "bottom"},
        "audio": {
            "include_source": True,
            "normalize": False,
            "narration_type": "none",
            "narration_path": None,
        },
        "editorial": {
            "overlay_enabled": True,
            "overlay_text": "MESMO CONTEÚDO",
            "template_variant": "variant_default",
        },
        "output": {"aspect_ratio": "9:16", "resolution": "720x1280"},
    }


def test_preview_and_final_record_the_same_editorial_plan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    plan = _plan()
    preview = generate_clip_preview(
        input_source=str(FIXTURE),
        start_ms=3000,
        end_ms=4500,
        edit_plan=plan,
        clip_id=CLIP_ID,
        run_id="run_equivalence_preview",
        profile="preview",
    )
    final = generate_clip_preview(
        input_source=str(FIXTURE),
        start_ms=3000,
        end_ms=4500,
        edit_plan=plan,
        clip_id=CLIP_ID,
        run_id="run_equivalence_final",
        profile="final",
    )

    assert preview["plan_version"] == final["plan_version"] == 4
    assert preview["applied_features"] == final["applied_features"]
    assert preview["metadata"]["layout_mode"] == final["metadata"]["layout_mode"]
    assert preview["metadata"]["aspect_ratio"] == final["metadata"]["aspect_ratio"]
    assert preview["metadata"]["actual_resolution"] == "360x640"
    assert final["metadata"]["actual_resolution"] == "720x1280"
    assert abs(preview["duration_ms"] - final["duration_ms"]) <= 150
