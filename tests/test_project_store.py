"""Persistence and identity contracts for dashboard UI-1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from youtube_clipper.project_store import (
    DomainConflictError,
    ProjectStore,
)


def _store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(
        tmp_path / "state" / "projects.sqlite3",
        tmp_path / "workspace",
    )


def _analysis_result() -> dict:
    return {
        "success": True,
        "clips": [
            {
                "rank": 1,
                "start_time": 0.0,
                "end_time": 3.0,
                "score": 91,
                "title": "Vermelho",
            },
            {
                "rank": 2,
                "start_time": 3.0,
                "end_time": 6.0,
                "score": 82,
                "title": "Verde",
            },
        ],
    }


def _project_with_clips(store: ProjectStore) -> tuple[dict, list[dict]]:
    project = store.create_project(
        name="Fixture UI-1",
        source_uri="tests/fixtures/panel_preview_identity/source_three_candidates.mp4",
        source_kind="local",
    )
    analysis = store.create_analysis(project_id=project["project_id"])
    clips = store.finish_analysis(
        analysis_id=analysis["analysis_id"],
        result=_analysis_result(),
    )
    return project, clips


def test_project_and_clip_identity_survive_store_reload(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project, clips = _project_with_clips(store)

    reloaded = _store(tmp_path)
    restored_project = reloaded.get_project(project["project_id"])
    restored_clips = reloaded.list_clips(project["project_id"])

    assert restored_project["project_id"] == project["project_id"]
    assert [item["clip_id"] for item in restored_clips] == [
        item["clip_id"] for item in clips
    ]
    assert restored_project["clip_count"] == 2
    assert reloaded.database_user_version() == 3


def test_each_clip_gets_an_independent_versioned_asset(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _, clips = _project_with_clips(store)
    media = tmp_path / "preview.mp4"
    media.write_bytes(b"synthetic-preview" * 128)

    first = store.add_asset(
        clip_id=clips[0]["clip_id"],
        kind="preview",
        source_path=media,
        mime_type="video/mp4",
        duration_ms=3000,
        width=360,
        height=640,
    )
    second = store.add_asset(
        clip_id=clips[1]["clip_id"],
        kind="preview",
        source_path=media,
        mime_type="video/mp4",
        duration_ms=3000,
        width=360,
        height=640,
    )

    assert first["asset_id"] != second["asset_id"]
    assert first["clip_id"] != second["clip_id"]
    assert first["url"] != second["url"]
    assert first["version"] == second["version"] == 1


def test_timeline_change_invalidates_only_its_clip_assets(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _, clips = _project_with_clips(store)
    media = tmp_path / "preview.mp4"
    media.write_bytes(b"synthetic-preview" * 128)
    assets = [
        store.add_asset(
            clip_id=clip["clip_id"],
            kind="preview",
            source_path=media,
            mime_type="video/mp4",
        )
        for clip in clips
    ]

    updated = store.update_clip(
        clips[0]["clip_id"],
        {"start_ms": 100, "end_ms": 2900},
    )
    first_asset = store.get_asset(assets[0]["asset_id"])
    second_asset = store.get_asset(assets[1]["asset_id"])

    assert updated["plan_version"] == 2
    assert first_asset["valid"] is False
    assert second_asset["valid"] is True

    regenerated = store.add_asset(
        clip_id=clips[0]["clip_id"],
        kind="preview",
        source_path=media,
        mime_type="video/mp4",
    )
    assert regenerated["version"] == 2


def test_manifest_uses_clip_identity_and_omits_internal_paths(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _, clips = _project_with_clips(store)
    media = tmp_path / "preview.mp4"
    media.write_bytes(b"synthetic-preview" * 128)
    asset = store.add_asset(
        clip_id=clips[0]["clip_id"],
        kind="preview",
        source_path=media,
        mime_type="video/mp4",
    )

    manifest = json.loads(
        store.manifest_path(clips[0]["clip_id"]).read_text(encoding="utf-8")
    )

    assert manifest["clip_id"] == clips[0]["clip_id"]
    assert manifest["assets"][0]["asset_id"] == asset["asset_id"]
    assert "file_path" not in manifest["assets"][0]


def test_render_rejects_asset_from_another_clip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _, clips = _project_with_clips(store)
    media = tmp_path / "render.mp4"
    media.write_bytes(b"synthetic-render" * 128)
    foreign_asset = store.add_asset(
        clip_id=clips[1]["clip_id"],
        kind="render",
        source_path=media,
        mime_type="video/mp4",
    )

    with pytest.raises(DomainConflictError):
        store.create_render(
            clip_id=clips[0]["clip_id"],
            asset_id=foreign_asset["asset_id"],
        )
