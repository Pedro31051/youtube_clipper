"""FastAPI application and local worker for the UI-3 dashboard foundation."""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import Body, FastAPI, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from cortes.preview import generate_clip_preview
from youtube_clipper.project_store import (
    DomainConflictError,
    DomainNotFoundError,
    DomainValidationError,
    ProjectStore,
)


class SourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    uri: str


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    source: SourceInput


class ProjectSummary(BaseModel):
    project_id: str
    name: str
    status: str
    created_at: str
    updated_at: str
    clip_count: int = 0
    job_count: int = 0


class ProjectsResponse(BaseModel):
    success: bool = True
    projects: list[ProjectSummary]


class ProjectResponse(BaseModel):
    success: bool = True
    project: dict[str, Any]


class ClipsResponse(BaseModel):
    success: bool = True
    project_id: str
    clips: list[dict[str, Any]]


class ClipResponse(BaseModel):
    success: bool = True
    clip: dict[str, Any]


class JobsResponse(BaseModel):
    success: bool = True
    jobs: list[dict[str, Any]]


class JobResponse(BaseModel):
    success: bool = True
    job: dict[str, Any]


class PreviewJobResponse(BaseModel):
    success: bool = True
    job: dict[str, Any]


class HealthResponse(BaseModel):
    success: bool = True
    service: str
    api_version: str


class JobEventBroker:
    """In-process event history with blocking wait support for SSE consumers."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._events: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def publish(
        self,
        job_id: str,
        event_type: str,
        *,
        state: str,
        progress: int,
        message: str,
        data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        with self._condition:
            event = {
                "seq": len(self._events[job_id]) + 1,
                "job_id": job_id,
                "type": event_type,
                "state": state,
                "progress": max(0, min(100, int(progress))),
                "message": str(message),
                "data": data or {},
                "timestamp_ms": int(time.time() * 1000),
            }
            self._events[job_id].append(event)
            self._condition.notify_all()
            return dict(event)

    def events_after(self, job_id: str, after_seq: int) -> list[dict[str, Any]]:
        with self._condition:
            return [
                dict(event)
                for event in self._events.get(job_id, [])
                if int(event["seq"]) > after_seq
            ]

    def wait_after(
        self,
        job_id: str,
        after_seq: int,
        timeout: float,
    ) -> list[dict[str, Any]]:
        with self._condition:
            events = [
                dict(event)
                for event in self._events.get(job_id, [])
                if int(event["seq"]) > after_seq
            ]
            if events:
                return events
            self._condition.wait(timeout=timeout)
            return [
                dict(event)
                for event in self._events.get(job_id, [])
                if int(event["seq"]) > after_seq
            ]


class PreviewWorker:
    """Run preview FFmpeg work outside request threads."""

    def __init__(
        self,
        store: ProjectStore,
        broker: JobEventBroker,
        *,
        max_workers: int = 2,
    ) -> None:
        self.store = store
        self.broker = broker
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="preview-worker",
        )

    def submit(self, clip_id: str) -> dict[str, Any]:
        clip = self.store.get_clip(clip_id)
        if clip["status"] not in {"proposed", "ready", "failed"}:
            raise DomainConflictError(
                f"Cannot preview clip while it is {clip['status']}"
            )
        job = self.store.create_job(
            project_id=clip["project_id"],
            clip_id=clip_id,
            kind="preview",
            state="queued",
        )
        self.broker.publish(
            job["job_id"],
            "job_queued",
            state="queued",
            progress=0,
            message="Preview queued",
            data={"clip_id": clip_id},
        )
        self.store.update_clip(clip_id, {"status": "previewing"})
        self._executor.submit(
            self._run_preview,
            job["job_id"],
            clip_id,
            int(clip["plan_version"]),
        )
        return self.store.get_job(job["job_id"])

    def _run_preview(
        self,
        job_id: str,
        clip_id: str,
        expected_plan_version: int,
    ) -> None:
        run_id = f"run_ui3_preview_{job_id}_{uuid.uuid4().hex}"
        try:
            self.store.update_job(job_id, state="running", run_id=run_id)
            self.broker.publish(
                job_id,
                "stage_start",
                state="running",
                progress=10,
                message="Rendering preview",
                data={"stage": "render"},
            )
            clip = self.store.get_clip(clip_id)
            source = self.store.get_source(clip["source_id"])
            generated = generate_clip_preview(
                input_source=source["uri"],
                start_ms=int(clip["start_ms"]),
                end_ms=int(clip["end_ms"]),
                edit_plan=clip["edit_plan"],
                clip_id=clip_id,
                run_id=run_id,
            )
            current = self.store.get_clip(clip_id)
            if int(current["plan_version"]) != expected_plan_version:
                raise DomainConflictError(
                    "Edit plan changed while preview was rendering"
                )
            self.broker.publish(
                job_id,
                "progress",
                state="running",
                progress=75,
                message="Registering immutable assets",
                data={"stage": "persist"},
            )
            preview = self.store.add_asset(
                clip_id=clip_id,
                kind="preview",
                source_path=generated["preview_path"],
                mime_type="video/mp4",
                duration_ms=generated["duration_ms"],
                width=generated["width"],
                height=generated["height"],
            )
            poster = self.store.add_asset(
                clip_id=clip_id,
                kind="poster",
                source_path=generated["poster_path"],
                mime_type="image/jpeg",
                width=generated["width"],
                height=generated["height"],
            )
            self.store.update_clip(clip_id, {"status": "ready"})
            self.store.update_job(job_id, state="completed", run_id=run_id)
            self.broker.publish(
                job_id,
                "stage_completed",
                state="completed",
                progress=100,
                message="Preview ready",
                data={
                    "stage": "preview",
                    "preview_url": preview["url"],
                    "poster_url": poster["url"],
                },
            )
        except Exception as exc:
            self.store.update_job(
                job_id,
                state="failed",
                run_id=run_id,
                error=str(exc)[:500],
            )
            try:
                self.store.update_clip(clip_id, {"status": "failed"})
            except (DomainConflictError, DomainValidationError):
                pass
            self.broker.publish(
                job_id,
                "job_failed",
                state="failed",
                progress=100,
                message=str(exc)[:240],
            )

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


def _parse_range(raw_range: Optional[str], size: int) -> tuple[int, int, int]:
    if not raw_range:
        return 0, size - 1, 200
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", raw_range.strip())
    if not match or (not match.group(1) and not match.group(2)):
        raise DomainValidationError("Invalid byte range")
    if match.group(1):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else size - 1
    else:
        suffix_length = int(match.group(2))
        if suffix_length <= 0:
            raise DomainValidationError("Invalid byte range")
        start = max(0, size - suffix_length)
        end = size - 1
    if start >= size or end < start:
        raise DomainValidationError("Byte range is outside the asset")
    return start, min(end, size - 1), 206


def _stream_file(path: Path, start: int, length: int):
    with path.open("rb") as stream:
        stream.seek(start)
        remaining = length
        while remaining:
            chunk = stream.read(min(65536, remaining))
            if not chunk:
                return
            remaining -= len(chunk)
            yield chunk


def _sse_message(event: dict[str, Any]) -> str:
    payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event['seq']}\nevent: {event['type']}\ndata: {payload}\n\n"


def create_app(
    *,
    store: Optional[ProjectStore] = None,
    workspace_dir: Optional[Path | str] = None,
    web_dist: Optional[Path | str] = None,
) -> FastAPI:
    workspace = Path(
        workspace_dir
        or os.environ.get("YOUTUBE_CLIPPER_WORKSPACE")
        or Path.cwd() / "panel_workspace"
    ).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    domain_store = store or ProjectStore(
        workspace / "projects.sqlite3",
        workspace,
    )
    broker = JobEventBroker()
    worker = PreviewWorker(domain_store, broker)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        worker.shutdown()

    app = FastAPI(
        title="YouTube Clipper API",
        version="1.0.0",
        description="Versioned project, clip, asset, and job API.",
        lifespan=lifespan,
    )
    app.state.store = domain_store
    app.state.job_events = broker
    app.state.preview_worker = worker
    app.state.web_dist = Path(
        web_dist or Path.cwd() / "web" / "dist"
    ).expanduser().resolve()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DomainNotFoundError)
    async def domain_not_found(_: Request, exc: DomainNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": str(exc)},
        )

    @app.exception_handler(DomainConflictError)
    async def domain_conflict(_: Request, exc: DomainConflictError):
        return JSONResponse(
            status_code=409,
            content={"success": False, "error": str(exc)},
        )

    @app.exception_handler(DomainValidationError)
    async def domain_validation(_: Request, exc: DomainValidationError):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(exc)},
        )

    @app.get("/api/v1/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            service="youtube-clipper",
            api_version="v1",
        )

    @app.get("/api/v1/projects", response_model=ProjectsResponse)
    async def list_projects() -> ProjectsResponse:
        return ProjectsResponse(projects=domain_store.list_projects())

    @app.post(
        "/api/v1/projects",
        response_model=ProjectResponse,
        status_code=201,
    )
    async def create_project(payload: ProjectCreate) -> ProjectResponse:
        project = domain_store.create_project(
            name=payload.name,
            source_uri=payload.source.uri,
            source_kind=payload.source.kind,
        )
        return ProjectResponse(project=project)

    @app.get("/api/v1/projects/{project_id}", response_model=ProjectResponse)
    async def get_project(project_id: str) -> ProjectResponse:
        return ProjectResponse(project=domain_store.get_project(project_id))

    @app.get(
        "/api/v1/projects/{project_id}/clips",
        response_model=ClipsResponse,
    )
    async def list_clips(project_id: str) -> ClipsResponse:
        return ClipsResponse(
            project_id=project_id,
            clips=domain_store.list_clips(project_id),
        )

    @app.get("/api/v1/clips/{clip_id}", response_model=ClipResponse)
    async def get_clip(clip_id: str) -> ClipResponse:
        return ClipResponse(clip=domain_store.get_clip(clip_id))

    @app.patch("/api/v1/clips/{clip_id}", response_model=ClipResponse)
    async def update_clip(
        clip_id: str,
        changes: dict[str, Any] = Body(...),
    ) -> ClipResponse:
        return ClipResponse(clip=domain_store.update_clip(clip_id, changes))

    @app.get("/api/v1/jobs", response_model=JobsResponse)
    async def list_jobs(
        project_id: Optional[str] = Query(default=None),
        limit: int = Query(default=25, ge=1, le=100),
    ) -> JobsResponse:
        return JobsResponse(
            jobs=domain_store.list_jobs(project_id=project_id, limit=limit)
        )

    @app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
    async def get_job(job_id: str) -> JobResponse:
        return JobResponse(job=domain_store.get_job(job_id))

    @app.post(
        "/api/v1/clips/{clip_id}/preview-jobs",
        response_model=PreviewJobResponse,
        status_code=202,
    )
    async def create_preview_job(clip_id: str) -> PreviewJobResponse:
        return PreviewJobResponse(job=worker.submit(clip_id))

    @app.get("/api/v1/jobs/{job_id}/events")
    async def job_events(
        job_id: str,
        request: Request,
        last_event_id: Optional[str] = Header(
            default=None,
            alias="Last-Event-ID",
        ),
    ) -> StreamingResponse:
        domain_store.get_job(job_id)
        try:
            starting_seq = max(0, int(last_event_id or "0"))
        except ValueError as exc:
            raise DomainValidationError("Last-Event-ID must be numeric") from exc

        async def event_stream() -> AsyncIterator[str]:
            cursor = starting_seq
            while True:
                if await request.is_disconnected():
                    return
                events = await asyncio.to_thread(
                    broker.wait_after,
                    job_id,
                    cursor,
                    10.0,
                )
                if not events:
                    yield ": keep-alive\n\n"
                    continue
                for event in events:
                    cursor = int(event["seq"])
                    yield _sse_message(event)
                    if event["state"] in {"completed", "failed", "cancelled"}:
                        return

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.get("/api/v1/assets/{asset_id}")
    async def get_asset(
        asset_id: str,
        request: Request,
        version: int = Query(alias="v", ge=1),
    ) -> Response:
        asset, path = domain_store.resolve_asset_file(
            asset_id,
            version=version,
        )
        size = path.stat().st_size
        try:
            start, end, status_code = _parse_range(
                request.headers.get("range"),
                size,
            )
        except DomainValidationError:
            return Response(
                status_code=416,
                headers={"Content-Range": f"bytes */{size}"},
            )
        content_length = end - start + 1
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": f'"{asset["sha256"]}"',
        }
        if status_code == 206:
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        return StreamingResponse(
            _stream_file(path, start, content_length),
            status_code=status_code,
            media_type=asset["mime_type"],
            headers=headers,
        )

    @app.get("/", include_in_schema=False)
    async def frontend_index() -> Response:
        index = app.state.web_dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "Frontend build not found. Run npm run build in web/.",
            },
        )

    @app.get("/{frontend_path:path}", include_in_schema=False)
    async def frontend_files(frontend_path: str) -> Response:
        if frontend_path == "openapi.json" or frontend_path.startswith("api/"):
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "API route not found"},
            )
        root = app.state.web_dist.resolve()
        candidate = (root / frontend_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return Response(status_code=404)
        if candidate.is_file():
            return FileResponse(candidate)
        index = root / "index.html"
        if index.is_file():
            return FileResponse(index)
        return Response(status_code=404)

    return app


def main() -> None:
    import uvicorn

    uvicorn.run(
        "youtube_clipper.api:create_app",
        host="127.0.0.1",
        port=8080,
        reload=False,
        factory=True,
    )


if __name__ == "__main__":
    main()
