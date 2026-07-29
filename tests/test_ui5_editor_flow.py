"""Physical UI-5 proof: one edit plan drives preview and final render."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from youtube_clipper.api import create_app
from youtube_clipper.project_store import ProjectStore


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "panel_preview_identity"
    / "source_three_candidates.mp4"
).resolve()


def _wait(client: TestClient, job_id: str, timeout: float = 45) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()["job"]
        if job["state"] in {"completed", "failed"}:
            return job
        time.sleep(0.1)
    raise AssertionError(f"Job did not settle: {job}")


def test_saved_plan_invalidates_preview_and_drives_physical_final_render(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "projects.sqlite3", tmp_path / "workspace")
    project = store.create_project(
        name="Editor UI-5",
        source_uri=str(FIXTURE),
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
                    "title": "Plano unificado",
                    "start_time": 0,
                    "end_time": 3,
                    "score": 99,
                }
            ],
        },
    )[0]
    app = create_app(store=store, analyze=lambda *_args, **_kwargs: {})

    with TestClient(app) as client:
        first_preview = client.post(
            f"/api/v1/clips/{clip['clip_id']}/preview-jobs"
        ).json()["job"]
        assert _wait(client, first_preview["job_id"])["state"] == "completed"

        saved = client.put(
            f"/api/v1/clips/{clip['clip_id']}/edit-plan",
            json={
                "expected_plan_version": 1,
                "start_ms": 200,
                "end_ms": 2200,
                "layout": {
                    "mode": "crop_center",
                    "crop_focus": "center",
                    "blur_sigma": 12,
                    "overlay_position": "top",
                },
                "audio": {
                    "include_source": True,
                    "normalize": True,
                    "narration_type": "none",
                },
                "editorial": {
                    "overlay_enabled": True,
                    "overlay_text": "CONTEXTO ORIGINAL",
                        "template_variant": "variant_default",
                },
                "output": {
                    "aspect_ratio": "9:16",
                    "resolution": "720x1280",
                },
            },
        )
        assert saved.status_code == 200
        edited = saved.json()["clip"]
        assert edited["plan_version"] == 2
        assert edited["preview_status"] == "stale"
        assert edited["edit_plan"]["timeline"]["start_ms"] == 200
        assert edited["edit_plan"]["layout"]["mode"] == "crop_center"
        assert edited["edit_plan"]["editorial"]["overlay_enabled"] is True

        stale_write = client.put(
            f"/api/v1/clips/{clip['clip_id']}/edit-plan",
            json={"expected_plan_version": 1, "start_ms": 300},
        )
        assert stale_write.status_code == 409

        regenerated = client.post(
            f"/api/v1/clips/{clip['clip_id']}/preview-jobs"
        ).json()["job"]
        assert _wait(client, regenerated["job_id"])["state"] == "completed"
        ready = client.get(f"/api/v1/clips/{clip['clip_id']}").json()["clip"]
        assert ready["preview_status"] == "ready"
        assert ready["preview_asset"]["version"] == 2

        approved = client.post(
            "/api/v1/clips/review",
            json={"clip_ids": [clip["clip_id"]], "decision": "approve"},
        )
        assert approved.status_code == 200
        rendered = client.post(
            f"/api/v1/clips/{clip['clip_id']}/render-jobs"
        )
        assert rendered.status_code == 202
        render_job = _wait(client, rendered.json()["job"]["job_id"], timeout=60)
        assert render_job["state"] == "completed", render_job.get("error")

        final_clip = client.get(
            f"/api/v1/clips/{clip['clip_id']}"
        ).json()["clip"]
        render_asset = next(
            asset
            for asset in final_clip["assets"]
            if asset["kind"] == "render" and asset["valid"]
        )
        assert final_clip["status"] == "rendered"
        assert render_asset["width"] == 720
        assert render_asset["height"] == 1280
        assert 1700 <= render_asset["duration_ms"] <= 2400
        _, path = store.resolve_asset_file(
            render_asset["asset_id"],
            version=render_asset["version"],
        )
        assert path.stat().st_size > 1024


def test_edit_plan_rejects_unsupported_fake_tts(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects.sqlite3", tmp_path / "workspace")
    project = store.create_project(
        name="No fake TTS",
        source_uri=str(FIXTURE),
        source_kind="local",
    )
    analysis = store.create_analysis(project_id=project["project_id"])
    clip = store.finish_analysis(
        analysis_id=analysis["analysis_id"],
        result={
            "success": True,
            "clips": [
                {"rank": 1, "title": "A", "start_time": 0, "end_time": 2}
            ],
        },
    )[0]
    app = create_app(store=store, analyze=lambda *_args, **_kwargs: {})
    with TestClient(app) as client:
        response = client.put(
            f"/api/v1/clips/{clip['clip_id']}/edit-plan",
            json={
                "expected_plan_version": 1,
                "audio": {
                    "include_source": True,
                    "normalize": True,
                    "narration_type": "tts",
                },
            },
        )
    assert response.status_code == 400
    assert "narration_type" in response.json()["error"]
