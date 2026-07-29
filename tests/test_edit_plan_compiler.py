"""Unit contracts for the canonical dashboard EditPlan compiler."""

from __future__ import annotations

import copy

import pytest

from youtube_clipper.edit_plan import EditPlanError, compile_edit_plan


def _plan() -> dict:
    return {
        "schema_version": "1.0.0",
        "plan_version": 7,
        "clip_id": "clp_11111111111111111111111111111111",
        "source_id": "src_22222222222222222222222222222222",
        "timeline": {"start_ms": 250, "end_ms": 2250, "duration_ms": 2000},
        "layout": {
            "mode": "crop_center",
            "crop_focus": "right",
            "blur_sigma": 8,
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
            "overlay_text": "PROVA CANÔNICA",
            "template_variant": "variant_default",
        },
        "output": {"aspect_ratio": "9:16", "resolution": "720x1280"},
    }


def test_profiles_only_change_encoding_quality() -> None:
    plan = _plan()
    preview = compile_edit_plan(plan, profile="preview")
    final = compile_edit_plan(plan, profile="final")

    invariant_fields = {
        "plan_version",
        "clip_id",
        "source_id",
        "start_ms",
        "end_ms",
        "duration_ms",
        "layout_mode",
        "crop_focus",
        "blur_sigma",
        "overlay_position",
        "overlay_text",
        "include_source_audio",
        "normalize_audio",
        "aspect_ratio",
        "requested_resolution",
        "applied_features",
    }
    preview_data = preview.model_dump()
    final_data = final.model_dump()
    for field in invariant_fields:
        assert preview_data[field] == final_data[field]
    assert (preview.width, preview.height) == (360, 640)
    assert (final.width, final.height) == (720, 1280)
    assert preview.video_crf != final.video_crf


@pytest.mark.parametrize(
    ("section", "changes"),
    [
        ("captions", {"enabled": True}),
        ("audio", {"narration_type": "external", "narration_path": "voice.wav"}),
        ("editorial", {"template_variant": "variant_impact"}),
    ],
)
def test_compiler_rejects_unsupported_visible_capabilities(
    section: str,
    changes: dict,
) -> None:
    plan = copy.deepcopy(_plan())
    plan[section].update(changes)
    with pytest.raises(EditPlanError):
        compile_edit_plan(plan, profile="preview")
