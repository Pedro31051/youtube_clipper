"""UI-3 FastAPI, worker, SSE, OpenAPI, and static shell contracts."""

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


def _app_with_clip(tmp_path: Path):
    store = ProjectStore(
        tmp_path / "projects.sqlite3",
        tmp_path / "workspace",
    )
    project = store.create_project(
        name="FastAPI UI-3",
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
                    "title": "Vermelho",
                    "start_time": 0,
                    "end_time": 3,
                    "score": 98,
                }
            ],
        },
    )[0]
    web_dist = tmp_path / "dist"
    web_dist.mkdir()
    (web_dist / "index.html").write_text(
        "<!doctype html><title>UI-3 shell</title>",
        encoding="utf-8",
    )
    return create_app(store=store, web_dist=web_dist), store, project, clip


def test_openapi_drives_versioned_project_contract_and_static_shell(
    tmp_path: Path,
) -> None:
    app, _, project, _ = _app_with_clip(tmp_path)
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        projects = client.get("/api/v1/projects")
        schema = client.get("/openapi.json")
        shell = client.get("/")

    assert health.status_code == 200
    assert health.json()["api_version"] == "v1"
    assert projects.status_code == 200
    assert projects.json()["projects"][0]["project_id"] == project["project_id"]
    assert "/api/v1/jobs/{job_id}/events" in schema.json()["paths"]
    assert schema.json()["info"]["title"] == "YouTube Clipper API"
    assert shell.status_code == 200
    assert "UI-3 shell" in shell.text


def test_preview_job_leaves_http_thread_and_emits_real_sse_events(
    tmp_path: Path,
) -> None:
    app, store, _, clip = _app_with_clip(tmp_path)
    with TestClient(app) as client:
        started = time.monotonic()
        submitted = client.post(
            f"/api/v1/clips/{clip['clip_id']}/preview-jobs"
        )
        request_elapsed = time.monotonic() - started

        assert submitted.status_code == 202
        assert request_elapsed < 1.5
        job = submitted.json()["job"]
        assert job["state"] in {"queued", "running"}

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            current = client.get(f"/api/v1/jobs/{job['job_id']}").json()["job"]
            if current["state"] in {"completed", "failed"}:
                break
            time.sleep(0.1)
        assert current["state"] == "completed", current.get("error")

        events = client.get(
            f"/api/v1/jobs/{job['job_id']}/events"
        )
        clip_after = client.get(
            f"/api/v1/clips/{clip['clip_id']}"
        ).json()["clip"]

        assert events.status_code == 200
        assert events.headers["content-type"].startswith("text/event-stream")
        assert "event: stage_start" in events.text
        assert "event: progress" in events.text
        assert "event: stage_completed" in events.text
        assert '"progress":100' in events.text
        assert clip_after["preview_status"] == "ready"

        preview = clip_after["preview_asset"]
        partial = client.get(
            preview["url"],
            headers={"Range": "bytes=0-127"},
        )
        assert partial.status_code == 206
        assert partial.headers["content-range"].startswith("bytes 0-127/")
        assert len(partial.content) == 128
        assert store.get_job(job["job_id"])["run_id"].startswith(
            "run_ui3_preview_"
        )


def test_domain_errors_remain_actionable_json(tmp_path: Path) -> None:
    app, _, _, _ = _app_with_clip(tmp_path)
    with TestClient(app) as client:
        missing = client.get(
            "/api/v1/projects/prj_00000000000000000000000000000000"
        )
        unknown = client.get("/api/v1/not-a-route")

    assert missing.status_code == 404
    assert missing.json() == {"success": False, "error": "Project not found"}
    assert unknown.status_code == 404
    assert unknown.json() == {"success": False, "error": "API route not found"}
