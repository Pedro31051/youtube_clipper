"""UI-7 operational proof with persistent jobs and physical media."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

from youtube_clipper.api import JobEventBroker, create_app
from youtube_clipper.project_store import ProjectStore


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "panel_preview_identity"
    / "source_three_candidates.mp4"
).resolve()


def _renderable_clip(store: ProjectStore, tmp_path: Path) -> dict:
    project = store.create_project(
        name="Operação UI-7",
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
                    "title": "Entrega física",
                    "start_time": 0,
                    "end_time": 9,
                    "score": 96,
                }
            ],
        },
    )[0]
    preview = store.add_asset(
        clip_id=clip["clip_id"],
        kind="preview",
        source_path=FIXTURE,
        mime_type="video/mp4",
        duration_ms=9000,
        width=640,
        height=360,
    )
    assert preview["size_bytes"] > 1024
    store.update_clip(clip["clip_id"], {"status": "ready"})
    return store.update_clip(clip["clip_id"], {"status": "approved"})


def _wait(client: TestClient, job_id: str, timeout: float = 45) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()["job"]
        if job["state"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"Job did not settle: {job}")


def test_job_events_survive_process_reload(tmp_path: Path) -> None:
    database = tmp_path / "projects.sqlite3"
    workspace = tmp_path / "workspace"
    store = ProjectStore(database, workspace)
    project = store.create_project(
        name="Eventos persistentes",
        source_uri=str(FIXTURE),
        source_kind="local",
    )
    job = store.create_job(project_id=project["project_id"], kind="analysis")
    broker = JobEventBroker(store)
    broker.publish(
        job["job_id"],
        "stage_start",
        state="running",
        progress=35,
        message="Transcrição física em andamento",
        data={"stage": "transcribe"},
    )

    reloaded = ProjectStore(database, workspace)
    restored = reloaded.get_job(job["job_id"])

    assert restored["progress"] == 35
    assert restored["stage"] == "transcribe"
    assert restored["events"][0]["message"] == "Transcrição física em andamento"


def test_orphan_job_is_interrupted_on_startup_and_retry_gets_new_id(
    tmp_path: Path,
) -> None:
    database = tmp_path / "projects.sqlite3"
    workspace = tmp_path / "workspace"
    store = ProjectStore(database, workspace)
    clip = _renderable_clip(store, tmp_path)
    store.update_clip(clip["clip_id"], {"status": "ready"})
    store.update_clip(clip["clip_id"], {"status": "previewing"})
    orphan = store.create_job(
        project_id=clip["project_id"],
        clip_id=clip["clip_id"],
        kind="preview",
        state="running",
    )

    reloaded = ProjectStore(database, workspace)
    app = create_app(store=reloaded)
    with TestClient(app) as client:
        interrupted = client.get(f"/api/v1/jobs/{orphan['job_id']}").json()["job"]
        retried_response = client.post(
            f"/api/v1/jobs/{orphan['job_id']}/retry"
        )
        retried = retried_response.json()["job"]
        settled = _wait(client, retried["job_id"])

    assert interrupted["state"] == "interrupted"
    assert interrupted["events"][-1]["type"] == "job_interrupted"
    assert retried_response.status_code == 202
    assert retried["job_id"] != orphan["job_id"]
    assert retried["parent_job_id"] == orphan["job_id"]
    assert settled["state"] == "completed"


def test_download_and_drive_export_require_and_use_physical_render(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "projects.sqlite3", tmp_path / "workspace")
    clip = _renderable_clip(store, tmp_path)
    render = store.add_asset(
        clip_id=clip["clip_id"],
        kind="render",
        source_path=FIXTURE,
        mime_type="video/mp4",
        duration_ms=9000,
        width=640,
        height=360,
    )
    store.update_clip(clip["clip_id"], {"status": "rendering"})
    store.update_clip(clip["clip_id"], {"status": "rendered"})
    uploaded = tmp_path / "drive-target.mp4"

    def physical_drive_copy(file_path: str, **_settings) -> dict:
        shutil.copyfile(file_path, uploaded)
        return {
            "success": True,
            "file_id": "physical-copy",
            "web_view_link": "https://drive.google.com/file/d/physical-copy/view",
        }

    app = create_app(store=store, drive_upload=physical_drive_copy)
    with TestClient(app) as client:
        partial = client.get(
            f"/api/v1/clips/{clip['clip_id']}/export/download",
            headers={"Range": "bytes=0-255"},
        )
        submitted = client.post(
            f"/api/v1/clips/{clip['clip_id']}/drive-jobs",
            json={"folder_name": "Entregas UI-7"},
        )
        drive_job = _wait(client, submitted.json()["job"]["job_id"])
        report = client.get(f"/api/v1/jobs/{drive_job['job_id']}/report")

    assert partial.status_code == 206
    assert partial.headers["content-disposition"].endswith('.mp4"')
    assert partial.content == FIXTURE.read_bytes()[:256]
    assert submitted.status_code == 202
    assert drive_job["state"] == "completed"
    assert uploaded.read_bytes() == FIXTURE.read_bytes()
    assert report.status_code == 200
    assert report.json()["report"]["events"][-1]["state"] == "completed"
    assert store.get_asset(render["asset_id"])["valid"] is True
    assert store.get_clip(clip["clip_id"])["status"] == "exported"


def test_active_physical_render_can_be_cancelled_without_orphan_asset(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "projects.sqlite3", tmp_path / "workspace")
    clip = _renderable_clip(store, tmp_path)
    app = create_app(store=store)

    with TestClient(app) as client:
        submitted = client.post(
            f"/api/v1/clips/{clip['clip_id']}/render-jobs"
        )
        job_id = submitted.json()["job"]["job_id"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            running = client.get(f"/api/v1/jobs/{job_id}").json()["job"]
            if running["state"] == "running":
                break
            time.sleep(0.01)
        assert running["state"] == "running"
        cancelled = client.post(f"/api/v1/jobs/{job_id}/cancel")
        settled = _wait(client, job_id)

    assert submitted.status_code == 202
    assert cancelled.status_code == 200
    assert settled["state"] == "cancelled"
    final_clip = store.get_clip(clip["clip_id"])
    assert final_clip["status"] == "failed"
    assert not [
        asset
        for asset in final_clip["assets"]
        if asset["kind"] == "render" and asset["valid"]
    ]


def test_retry_links_attempts_and_failure_has_actionable_drive_guidance(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "projects.sqlite3", tmp_path / "workspace")
    clip = _renderable_clip(store, tmp_path)
    store.add_asset(
        clip_id=clip["clip_id"],
        kind="render",
        source_path=FIXTURE,
        mime_type="video/mp4",
    )
    store.update_clip(clip["clip_id"], {"status": "rendering"})
    store.update_clip(clip["clip_id"], {"status": "rendered"})

    def quota_failure(_file_path: str, **_settings) -> dict:
        return {
            "success": False,
            "error": "Google Drive quota exceeded: service account has 0 bytes",
        }

    app = create_app(store=store, drive_upload=quota_failure)
    with TestClient(app) as client:
        first = client.post(
            f"/api/v1/clips/{clip['clip_id']}/drive-jobs",
            json={},
        ).json()["job"]
        first = _wait(client, first["job_id"])
        retried_response = client.post(
            f"/api/v1/jobs/{first['job_id']}/retry"
        )
        retried = _wait(client, retried_response.json()["job"]["job_id"])

    assert first["state"] == "failed"
    assert "OAuth" in first["action"]
    assert retried_response.status_code == 202
    assert retried["attempt"] == 2
    assert retried["parent_job_id"] == first["job_id"]
    assert retried["state"] == "failed"
