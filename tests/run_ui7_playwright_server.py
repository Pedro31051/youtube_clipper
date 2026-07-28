"""Seed a physical local UI-7 workspace and serve it for Playwright."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import uvicorn

from youtube_clipper.api import JobEventBroker, create_app
from youtube_clipper.project_store import ProjectStore


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    ROOT
    / "tests"
    / "fixtures"
    / "panel_preview_identity"
    / "source_three_candidates.mp4"
).resolve()


def seeded_app():
    workspace = Path(tempfile.gettempdir()) / "youtube-clipper-ui7-playwright"
    if workspace.exists():
        shutil.rmtree(workspace)
    store = ProjectStore(workspace / "projects.sqlite3", workspace)
    project = store.create_project(
        name="Operação Playwright",
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
                    "title": "Render concluído sobre mídia física",
                    "start_time": 0,
                    "end_time": 9,
                    "score": 97,
                    "summary": "Fixture real pronta para download Range.",
                }
            ],
        },
    )[0]
    store.add_asset(
        clip_id=clip["clip_id"],
        kind="preview",
        source_path=FIXTURE,
        mime_type="video/mp4",
        duration_ms=9000,
        width=640,
        height=360,
    )
    store.add_asset(
        clip_id=clip["clip_id"],
        kind="render",
        source_path=FIXTURE,
        mime_type="video/mp4",
        duration_ms=9000,
        width=640,
        height=360,
    )
    store.update_clip(clip["clip_id"], {"status": "ready"})
    store.update_clip(clip["clip_id"], {"status": "approved"})
    store.update_clip(clip["clip_id"], {"status": "rendering"})
    store.update_clip(clip["clip_id"], {"status": "rendered"})
    job = store.create_job(
        project_id=project["project_id"],
        clip_id=clip["clip_id"],
        kind="render",
        state="completed",
    )
    broker = JobEventBroker(store)
    broker.publish(
        job["job_id"],
        "job_queued",
        state="queued",
        progress=0,
        message="Render adicionado à fila",
        data={"stage": "render"},
    )
    broker.publish(
        job["job_id"],
        "stage_completed",
        state="completed",
        progress=100,
        message="Render concluído sobre mídia física",
        data={"stage": "render"},
    )
    return create_app(
        store=store,
        web_dist=ROOT / "web" / "dist",
        analyze=lambda *_args, **_kwargs: {},
    )


if __name__ == "__main__":
    uvicorn.run(seeded_app(), host="127.0.0.1", port=8765, log_level="warning")
