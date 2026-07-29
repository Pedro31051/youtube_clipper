"""UI-4 integration gates for async analysis and bounded clip review."""

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


def _wait_for_jobs(
    client: TestClient,
    project_id: str,
    *,
    timeout: float = 45.0,
) -> list[dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        jobs = client.get(
            "/api/v1/jobs",
            params={"project_id": project_id, "limit": 20},
        ).json()["jobs"]
        if jobs and all(job["state"] in {"completed", "failed"} for job in jobs):
            return jobs
        time.sleep(0.1)
    raise AssertionError(f"Jobs did not settle: {jobs}")


def test_source_analysis_preview_review_flow_never_blocks_http(
    tmp_path: Path,
) -> None:
    def deterministic_analysis(
        source: str,
        *,
        max_clips: int,
        language: str,
        target_duration_seconds: int,
    ) -> dict:
        assert source == str(FIXTURE)
        assert max_clips == 3
        assert language == "pt"
        assert target_duration_seconds == 45
        return {
            "success": True,
            "clips": [
                {
                    "rank": 1,
                    "title": "Vermelho",
                    "start_time": 0,
                    "end_time": 3,
                    "score": 98,
                    "summary": "Abertura em vermelho.",
                },
                {
                    "rank": 2,
                    "title": "Verde",
                    "start_time": 3,
                    "end_time": 6,
                    "score": 91,
                    "summary": "Trecho intermediário em verde.",
                },
                {
                    "rank": 3,
                    "title": "Azul",
                    "start_time": 6,
                    "end_time": 9,
                    "score": 87,
                    "summary": "Encerramento em azul.",
                },
            ],
        }

    store = ProjectStore(tmp_path / "projects.sqlite3", tmp_path / "workspace")
    app = create_app(store=store, analyze=deterministic_analysis)
    with TestClient(app) as client:
        project_response = client.post(
            "/api/v1/projects",
            json={
                "name": "Fluxo UI-4",
                "source": {"kind": "local", "uri": str(FIXTURE)},
            },
        )
        project_id = project_response.json()["project"]["project_id"]

        started = time.monotonic()
        submitted = client.post(
            f"/api/v1/projects/{project_id}/analysis-jobs",
            json={
                "language": "pt",
                "max_clips": 3,
                "target_duration_seconds": 45,
                "aspect_ratio": "9:16",
            },
        )
        elapsed = time.monotonic() - started

        assert submitted.status_code == 202
        assert elapsed < 1.5
        jobs = _wait_for_jobs(client, project_id)
        assert len(jobs) == 4
        assert {job["kind"] for job in jobs} == {"analysis", "preview"}
        assert all(job["state"] == "completed" for job in jobs)

        project = client.get(f"/api/v1/projects/{project_id}").json()["project"]
        clips = client.get(
            f"/api/v1/projects/{project_id}/clips"
        ).json()["clips"]
        assert project["status"] == "review"
        assert len(clips) == 3
        assert len({clip["clip_id"] for clip in clips}) == 3
        assert all(clip["status"] == "ready" for clip in clips)
        assert all(clip["poster_url"] for clip in clips)
        assert all(clip["preview_url"] for clip in clips)

        approved = client.post(
            "/api/v1/clips/review",
            json={
                "clip_ids": [clips[0]["clip_id"], clips[1]["clip_id"]],
                "decision": "approve",
            },
        )
        assert approved.status_code == 200
        assert {clip["status"] for clip in approved.json()["clips"]} == {
            "approved"
        }

        rejected = client.post(
            "/api/v1/clips/review",
            json={
                "clip_ids": [clips[0]["clip_id"], clips[2]["clip_id"]],
                "decision": "reject",
            },
        )
        assert rejected.status_code == 200
        assert {clip["status"] for clip in rejected.json()["clips"]} == {
            "rejected"
        }


def test_batch_review_rejects_impossible_group_without_partial_write(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "projects.sqlite3", tmp_path / "workspace")
    project = store.create_project(
        name="Atomic review",
        source_uri=str(FIXTURE),
        source_kind="local",
    )
    analysis = store.create_analysis(project_id=project["project_id"])
    clips = store.finish_analysis(
        analysis_id=analysis["analysis_id"],
        result={
            "success": True,
            "clips": [
                {"rank": 1, "title": "A", "start_time": 0, "end_time": 3},
                {"rank": 2, "title": "B", "start_time": 3, "end_time": 6},
            ],
        },
    )
    store.update_clip(clips[0]["clip_id"], {"status": "rejected"})
    app = create_app(store=store, analyze=lambda *_args, **_kwargs: {})

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/clips/review",
            json={
                "clip_ids": [clips[0]["clip_id"], clips[1]["clip_id"]],
                "decision": "approve",
            },
        )

    assert response.status_code == 409
    assert "requires a ready preview" in response.json()["error"]
    assert store.get_clip(clips[0]["clip_id"])["status"] == "rejected"
    assert store.get_clip(clips[1]["clip_id"])["status"] == "proposed"


def test_analysis_failure_is_persistent_and_actionable(tmp_path: Path) -> None:
    def failed_analysis(_source: str, **_settings) -> dict:
        return {
            "success": False,
            "error": "YouTube exigiu autenticação; forneça cookies válidos.",
            "clips": [],
        }

    store = ProjectStore(tmp_path / "projects.sqlite3", tmp_path / "workspace")
    project = store.create_project(
        name="Falha visível",
        source_uri="https://www.youtube.com/watch?v=blocked",
        source_kind="youtube",
    )
    app = create_app(store=store, analyze=failed_analysis)
    with TestClient(app) as client:
        submitted = client.post(
            f"/api/v1/projects/{project['project_id']}/analysis-jobs",
            json={},
        )
        assert submitted.status_code == 202
        jobs = _wait_for_jobs(client, project["project_id"])
        failed = jobs[0]
        events = client.get(f"/api/v1/jobs/{failed['job_id']}/events")

    assert failed["state"] == "failed"
    assert "cookies válidos" in failed["error"]
    assert store.get_project(project["project_id"])["status"] == "failed"
    assert "Verifique a fonte" in events.text
