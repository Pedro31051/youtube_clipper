"""Final physical race gates for analysis, persistence, and preview versioning."""

from __future__ import annotations

import threading
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


def _result(*, start: float = 0, end: float = 1) -> dict:
    return {
        "success": True,
        "clips": [
            {
                "rank": 1,
                "title": f"Corte {start:.1f}",
                "start_time": start,
                "end_time": end,
                "score": 99,
            }
        ],
    }


def _create_project(client: TestClient, name: str) -> str:
    response = client.post(
        "/api/v1/projects",
        json={
            "name": name,
            "source": {"kind": "local", "uri": str(FIXTURE)},
        },
    )
    assert response.status_code == 201
    return str(response.json()["project"]["project_id"])


def _submit_analysis(client: TestClient, project_id: str) -> str:
    response = client.post(
        f"/api/v1/projects/{project_id}/analysis-jobs",
        json={
            "language": "pt",
            "max_clips": 1,
            "target_duration_seconds": 30,
            "aspect_ratio": "9:16",
        },
    )
    assert response.status_code == 202
    return str(response.json()["job"]["job_id"])


def _wait_job(
    client: TestClient,
    job_id: str,
    *,
    timeout: float = 90,
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()["job"]
        if job["state"] in {"completed", "failed", "cancelled", "interrupted"}:
            return job
        time.sleep(0.03)
    raise AssertionError(f"Job did not settle: {job}")


def test_a_fast_analysis_to_preview_is_deterministic_for_50_repetitions(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "projects.sqlite3", tmp_path / "workspace")
    app = create_app(store=store, analyze=lambda *_args, **_kwargs: _result())

    with TestClient(app) as client:
        project_ids = []
        for repetition in range(50):
            project_id = _create_project(client, f"Stress {repetition:02d}")
            project_ids.append(project_id)
            _submit_analysis(client, project_id)

        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            jobs = client.get("/api/v1/jobs", params={"limit": 100}).json()["jobs"]
            if (
                len(jobs) == 100
                and all(job["state"] in {"completed", "failed"} for job in jobs)
            ):
                break
            time.sleep(0.1)

        assert len(jobs) == 100
        assert all(job["state"] == "completed" for job in jobs)
        assert sum(job["kind"] == "analysis" for job in jobs) == 50
        assert sum(job["kind"] == "preview" for job in jobs) == 50
        for project_id in project_ids:
            clips = client.get(
                f"/api/v1/projects/{project_id}/clips"
            ).json()["clips"]
            assert len(clips) == 1
            clip = clips[0]
            assert clip["clip_id"]
            assert clip["plan_version"] == 1
            assert clip["preview_status"] == "ready"
            valid_previews = [
                asset
                for asset in clip["assets"]
                if asset["kind"] == "preview" and asset["valid"]
            ]
            assert len(valid_previews) == 1
            assert valid_previews[0]["clip_id"] == clip["clip_id"]
            assert valid_previews[0]["version"] == 1


def test_b_slow_analysis_starts_zero_previews_before_persistence(
    tmp_path: Path,
) -> None:
    entered = threading.Event()
    release = threading.Event()

    def slow_analysis(*_args, **_kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return _result()

    store = ProjectStore(tmp_path / "projects.sqlite3", tmp_path / "workspace")
    app = create_app(store=store, analyze=slow_analysis)
    with TestClient(app) as client:
        project_id = _create_project(client, "Análise lenta")
        analysis_job_id = _submit_analysis(client, project_id)
        assert entered.wait(timeout=5)
        jobs_before = client.get(
            "/api/v1/jobs", params={"project_id": project_id, "limit": 20}
        ).json()["jobs"]
        assert len(jobs_before) == 1
        assert jobs_before[0]["kind"] == "analysis"
        assert client.get(
            f"/api/v1/projects/{project_id}/clips"
        ).json()["clips"] == []

        release.set()
        assert _wait_job(client, analysis_job_id)["state"] == "completed"
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            jobs_after = client.get(
                "/api/v1/jobs", params={"project_id": project_id, "limit": 20}
            ).json()["jobs"]
            if len(jobs_after) == 2 and all(
                job["state"] == "completed" for job in jobs_after
            ):
                break
            time.sleep(0.05)
        assert {job["kind"] for job in jobs_after} == {"analysis", "preview"}


def test_c_duplicate_preview_request_has_predictable_conflict(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "projects.sqlite3", tmp_path / "workspace")
    project = store.create_project(
        name="Concorrência", source_uri=str(FIXTURE), source_kind="local"
    )
    analysis = store.create_analysis(project_id=project["project_id"])
    clip = store.finish_analysis(
        analysis_id=analysis["analysis_id"], result=_result()
    )[0]
    app = create_app(store=store)
    with TestClient(app) as client:
        accepted = client.post(f"/api/v1/clips/{clip['clip_id']}/preview-jobs")
        duplicate = client.post(f"/api/v1/clips/{clip['clip_id']}/preview-jobs")
        settled = _wait_job(client, accepted.json()["job"]["job_id"])

    assert accepted.status_code == 202
    assert duplicate.status_code == 409
    assert "preview" in duplicate.json()["error"].lower()
    assert settled["state"] == "completed"
    previews = [
        asset
        for asset in store.get_clip(clip["clip_id"])["assets"]
        if asset["kind"] == "preview" and asset["valid"]
    ]
    assert len(previews) == 1


def test_d_plan_v1_result_cannot_replace_plan_v2_preview(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "projects.sqlite3", tmp_path / "workspace")
    project = store.create_project(
        name="Versões", source_uri=str(FIXTURE), source_kind="local"
    )
    analysis = store.create_analysis(project_id=project["project_id"])
    clip = store.finish_analysis(
        analysis_id=analysis["analysis_id"], result=_result(end=3)
    )[0]
    app = create_app(store=store)
    with TestClient(app) as client:
        first = client.post(
            f"/api/v1/clips/{clip['clip_id']}/preview-jobs"
        ).json()["job"]
        edited = client.put(
            f"/api/v1/clips/{clip['clip_id']}/edit-plan",
            json={
                "expected_plan_version": 1,
                "start_ms": 100,
                "end_ms": 2100,
            },
        )
        assert edited.status_code == 200
        assert edited.json()["clip"]["plan_version"] == 2
        assert _wait_job(client, first["job_id"])["state"] == "failed"

        second = client.post(
            f"/api/v1/clips/{clip['clip_id']}/preview-jobs"
        ).json()["job"]
        assert _wait_job(client, second["job_id"])["state"] == "completed"

    current = store.get_clip(clip["clip_id"])
    valid = [
        asset
        for asset in current["assets"]
        if asset["kind"] == "preview" and asset["valid"]
    ]
    assert current["plan_version"] == 2
    assert current["preview_status"] == "ready"
    assert len(valid) == 1
    assert valid[0]["version"] == 2
