"""UI-2 edit-plan versioning beyond timeline-only edits."""

from pathlib import Path

from youtube_clipper.project_store import ProjectStore


def test_visual_plan_change_versions_and_invalidates_preview(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects.sqlite3", tmp_path / "workspace")
    project = store.create_project(
        name="Plano visual",
        source_uri="source.mp4",
        source_kind="local",
    )
    analysis = store.create_analysis(project_id=project["project_id"])
    clip = store.finish_analysis(
        analysis_id=analysis["analysis_id"],
        result={
            "success": True,
            "clips": [
                {
                    "rank": 1,
                    "start_time": 0,
                    "end_time": 3,
                    "score": 90,
                    "title": "Plano",
                }
            ],
        },
    )[0]
    media = tmp_path / "preview.mp4"
    media.write_bytes(b"synthetic-preview" * 128)
    asset = store.add_asset(
        clip_id=clip["clip_id"],
        kind="preview",
        source_path=media,
        mime_type="video/mp4",
    )
    changes = {
        "layout": {
            "mode": "crop_center",
            "crop_focus": "right",
            "blur_sigma": 8,
            "overlay_position": "bottom",
        },
        "audio": {"include_source": False},
        "editorial": {
            "overlay_enabled": True,
            "overlay_text": "Plano persistido",
        },
    }

    updated = store.update_clip(clip["clip_id"], changes)

    assert updated["plan_version"] == 2
    assert updated["edit_plan"]["layout"]["crop_focus"] == "right"
    assert updated["edit_plan"]["audio"]["include_source"] is False
    assert updated["preview_status"] == "stale"
    assert store.get_asset(asset["asset_id"])["valid"] is False

    unchanged = store.update_clip(clip["clip_id"], changes)
    assert unchanged["plan_version"] == 2
