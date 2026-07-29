"""Recovery proof for persisted dashboard jobs."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from youtube_clipper.api import AnalysisJobCreate, JobEventBroker, create_app
from youtube_clipper.project_store import DomainConflictError, ProjectStore


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "panel_preview_identity"
    / "source_three_candidates.mp4"
).resolve()


def _orphaned_analysis(store: ProjectStore) -> dict:
    project = store.create_project(
        name="Recuperação de job",
        source_uri=str(FIXTURE),
        source_kind="local",
    )
    analysis = store.create_analysis(project_id=project["project_id"])
    settings = AnalysisJobCreate().model_dump()
    job = store.create_job(
        project_id=project["project_id"],
        analysis_id=analysis["analysis_id"],
        kind="analysis",
        payload=settings,
    )
    store.update_project_status(project["project_id"], "analyzing")
    store.update_job(job["job_id"], state="running", run_id="run_before_restart")
    JobEventBroker(store).publish(
        job["job_id"],
        "stage_start",
        state="running",
        progress=35,
        message="Análise em andamento antes do reinício",
        data={"stage": "analysis"},
    )
    return store.get_job(job["job_id"])


def _wait(client: TestClient, job_id: str, timeout: float = 10) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()["job"]
        if job["state"] in {"completed", "failed", "cancelled", "interrupted"}:
            return job
        time.sleep(0.02)
    raise AssertionError(f"Job did not settle: {job}")


def test_job_state_machine_rejects_terminal_reactivation(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects.sqlite3", tmp_path / "workspace")
    project = store.create_project(
        name="Máquina de estados",
        source_uri=str(FIXTURE),
        source_kind="local",
    )
    job = store.create_job(project_id=project["project_id"], kind="analysis")
    store.update_job(job["job_id"], state="running")
    store.update_job(job["job_id"], state="completed")

    with pytest.raises(DomainConflictError):
        store.update_job(job["job_id"], state="running")


def test_startup_interrupts_orphan_and_retry_uses_new_job_id(tmp_path: Path) -> None:
    database = tmp_path / "projects.sqlite3"
    workspace = tmp_path / "workspace"
    first_store = ProjectStore(database, workspace)
    original = _orphaned_analysis(first_store)

    restarted_store = ProjectStore(database, workspace)
    app = create_app(
        store=restarted_store,
        analyze=lambda *_args, **_kwargs: {
            "success": False,
            "error": "falha controlada da nova tentativa",
        },
    )
    with TestClient(app) as client:
        interrupted = client.get(
            f"/api/v1/jobs/{original['job_id']}"
        ).json()["job"]
        response = client.post(f"/api/v1/jobs/{original['job_id']}/retry")
        assert response.status_code == 202
        retried = _wait(client, response.json()["job"]["job_id"])

    assert interrupted["state"] == "interrupted"
    assert interrupted["events"][-1]["type"] == "job_interrupted"
    assert "reiniciado" in interrupted["events"][-1]["message"]
    assert retried["job_id"] != original["job_id"]
    assert retried["parent_job_id"] == original["job_id"]
    assert retried["attempt"] == 2
    assert retried["state"] == "failed"


def test_shutdown_interrupts_worker_that_misses_grace_period(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ProjectStore(tmp_path / "projects.sqlite3", tmp_path / "workspace")
    project = store.create_project(
        name="Shutdown cooperativo",
        source_uri=str(FIXTURE),
        source_kind="local",
    )
    entered = threading.Event()
    release = threading.Event()

    def slow_analysis(*_args, **_kwargs):
        entered.set()
        release.wait(timeout=5)
        return {"success": False, "error": "encerramento controlado"}

    monkeypatch.setenv("YOUTUBE_CLIPPER_SHUTDOWN_TIMEOUT_SECONDS", "0.05")
    app = create_app(store=store, analyze=slow_analysis)
    try:
        with TestClient(app) as client:
            submitted = client.post(
                f"/api/v1/projects/{project['project_id']}/analysis-jobs",
                json=AnalysisJobCreate().model_dump(),
            )
            job_id = submitted.json()["job"]["job_id"]
            assert entered.wait(timeout=2)
        interrupted = store.get_job(job_id)
    finally:
        release.set()

    assert interrupted["state"] == "interrupted"
    assert interrupted["events"][-1]["type"] == "job_interrupted"
