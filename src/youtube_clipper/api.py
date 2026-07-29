"""FastAPI application and local workers for the intermediate dashboard."""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Literal, Optional

from fastapi import Body, FastAPI, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from cortes.preview import PreviewCancelledError, generate_clip_preview
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


class AnalysisJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str = Field(default="auto", pattern=r"^(auto|pt|en)$")
    max_clips: int = Field(default=5, ge=1, le=10)
    target_duration_seconds: int = Field(default=45, ge=15, le=59)
    aspect_ratio: str = Field(default="9:16", pattern=r"^(9:16|1:1|16:9)$")


class ClipReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clip_ids: list[str] = Field(min_length=1, max_length=20)
    decision: Literal["approve", "reject"]


class DriveExportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folder_id: Optional[str] = Field(default=None, max_length=200)
    folder_name: str = Field(default="YouTube_Clips", min_length=1, max_length=120)


class EditPlanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_plan_version: int = Field(ge=1)
    start_ms: Optional[int] = Field(default=None, ge=0)
    end_ms: Optional[int] = Field(default=None, ge=1)
    layout: Optional[dict[str, Any]] = None
    captions: Optional[dict[str, Any]] = None
    audio: Optional[dict[str, Any]] = None
    editorial: Optional[dict[str, Any]] = None
    output: Optional[dict[str, Any]] = None


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


class ClipReviewResponse(BaseModel):
    success: bool = True
    clips: list[dict[str, Any]]


class HealthResponse(BaseModel):
    success: bool = True
    service: str
    api_version: str


class JobEventBroker:
    """Persistent event history with in-process wakeups for SSE consumers."""

    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self._condition = threading.Condition()

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
            event = self.store.record_job_event(
                job_id,
                event_type=event_type,
                state=state,
                progress=progress,
                message=message,
                data=data,
                timestamp_ms=int(time.time() * 1000),
            )
            event["job_id"] = job_id
            self._condition.notify_all()
            return dict(event)

    def events_after(self, job_id: str, after_seq: int) -> list[dict[str, Any]]:
        with self._condition:
            return self.store.list_job_events(job_id, after_seq=after_seq)

    def wait_after(
        self,
        job_id: str,
        after_seq: int,
        timeout: float,
    ) -> list[dict[str, Any]]:
        with self._condition:
            events = self.store.list_job_events(job_id, after_seq=after_seq)
            if events:
                return events
            self._condition.wait(timeout=timeout)
            return self.store.list_job_events(job_id, after_seq=after_seq)


class JobCancelledError(RuntimeError):
    """A cooperative worker cancellation reached a safe boundary."""


def _failure_guidance(kind: str, error: str) -> dict[str, str]:
    lowered = error.lower()
    if kind == "drive_upload" or any(
        term in lowered for term in ("drive", "quota", "credential", "oauth")
    ):
        return {
            "cause": "O Google Drive recusou ou não autenticou o envio.",
            "action": (
                "Configure OAuth de usuário ou um Shared Drive com espaço "
                "disponível e tente novamente."
            ),
        }
    if any(term in lowered for term in ("nvenc", "cuda", "gpu")):
        return {
            "cause": "A aceleração de GPU não ficou disponível para o render.",
            "action": "Use o fallback libx264 de CPU e tente novamente.",
        }
    if any(term in lowered for term in ("youtube", "cookie", "sign in", "login")):
        return {
            "cause": "O YouTube exigiu autenticação ou bloqueou a fonte.",
            "action": (
                "Verifique a fonte, atualize os cookies e tente analisar novamente."
            ),
        }
    if any(term in lowered for term in ("ffmpeg", "render", "codec", "encoder")):
        return {
            "cause": "O FFmpeg não conseguiu produzir a mídia.",
            "action": "Confira a fonte, o encoder instalado e tente novamente.",
        }
    return {
        "cause": "O job foi interrompido por uma falha operacional.",
        "action": "Abra o relatório, confira os detalhes e tente novamente.",
    }


ACTIVE_JOB_STATES = {"queued", "running"}


def _restore_interrupted_domain_state(store: ProjectStore, job: dict[str, Any]) -> None:
    kind = str(job.get("kind") or "")
    clip_id = job.get("clip_id")
    if clip_id and kind in {"preview", "render"}:
        clip = store.get_clip(str(clip_id))
        if clip["status"] in {"previewing", "rendering"}:
            store.update_clip(str(clip_id), {"status": "failed"})
    if kind == "analysis":
        analysis_id = job.get("analysis_id")
        if analysis_id:
            store.fail_analysis(
                str(analysis_id),
                {"success": False, "error": "Servidor reiniciado durante a análise"},
            )
        store.update_project_status(str(job["project_id"]), "failed")


def _interrupt_job(
    store: ProjectStore,
    broker: JobEventBroker,
    job: dict[str, Any],
    *,
    reason: str,
) -> None:
    current = store.get_job(str(job["job_id"]))
    if current["state"] not in ACTIVE_JOB_STATES:
        return
    store.update_job(
        str(job["job_id"]),
        state="interrupted",
        error=reason,
    )
    broker.publish(
        str(job["job_id"]),
        "job_interrupted",
        state="interrupted",
        progress=int(current.get("progress") or 0),
        message=reason,
        data={"action": "Tente novamente para criar um novo job."},
    )
    _restore_interrupted_domain_state(store, current)


def _reconcile_orphaned_jobs(store: ProjectStore, broker: JobEventBroker) -> int:
    jobs = store.list_active_jobs()
    for job in jobs:
        _interrupt_job(
            store,
            broker,
            job,
            reason="Servidor reiniciado; o worker anterior não está mais disponível.",
        )
    return len(jobs)


def _shutdown_worker(worker: Any, timeout_seconds: float) -> None:
    with worker._control_lock:
        controls = list(worker._controls.items())
    for _job_id, (cancellation, future) in controls:
        cancellation.set()
        future.cancel()
    worker._executor.shutdown(wait=False, cancel_futures=True)

    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while time.monotonic() < deadline and any(
        not future.done() for _job_id, (_cancellation, future) in controls
    ):
        time.sleep(0.02)
    for job_id, (_cancellation, _future) in controls:
        current = worker.store.get_job(job_id)
        if current["state"] in ACTIVE_JOB_STATES:
            _interrupt_job(
                worker.store,
                worker.broker,
                current,
                reason="Servidor desligado antes da conclusão segura do job.",
            )
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
        self._controls: dict[str, tuple[threading.Event, Any]] = {}
        self._control_lock = threading.Lock()

    def submit(
        self,
        clip_id: str,
        *,
        attempt: int = 1,
        parent_job_id: Optional[str] = None,
    ) -> dict[str, Any]:
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
            attempt=attempt,
            parent_job_id=parent_job_id,
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
        cancellation = threading.Event()
        with self._control_lock:
            future = self._executor.submit(
                self._run_preview,
                job["job_id"],
                clip_id,
                int(clip["plan_version"]),
                cancellation,
            )
            self._controls[job["job_id"]] = (cancellation, future)
        return self.store.get_job(job["job_id"])

    def cancel(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if job["kind"] != "preview":
            raise DomainConflictError("Job is not a preview job")
        if job["state"] not in {"queued", "running"}:
            raise DomainConflictError("Only an active job can be cancelled")
        with self._control_lock:
            control = self._controls.get(job_id)
        if control is None:
            raise DomainConflictError("Job is no longer attached to this worker")
        cancellation, future = control
        cancellation.set()
        cancelled_before_start = future.cancel()
        if cancelled_before_start:
            with self._control_lock:
                self._controls.pop(job_id, None)
        self.store.update_job(job_id, state="cancelled", error=None)
        self.store.update_clip(str(job["clip_id"]), {"status": "failed"})
        self.broker.publish(
            job_id,
            "job_cancelled",
            state="cancelled",
            progress=int(job.get("progress") or 0),
            message="Preview cancelado pelo usuário",
            data={"action": "Use Tentar novamente quando quiser retomar."},
        )
        return self.store.get_job(job_id)

    def _run_preview(
        self,
        job_id: str,
        clip_id: str,
        expected_plan_version: int,
        cancellation: threading.Event,
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
                cancel_event=cancellation,
            )
            if cancellation.is_set():
                raise JobCancelledError("Preview cancelled")
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
                plan_version=generated["plan_version"],
                metadata=generated["metadata"],
                duration_ms=generated["duration_ms"],
                width=generated["width"],
                height=generated["height"],
                version=expected_plan_version,
            )
            poster = self.store.add_asset(
                clip_id=clip_id,
                kind="poster",
                source_path=generated["poster_path"],
                mime_type="image/jpeg",
                plan_version=generated["plan_version"],
                metadata=generated["metadata"],
                width=generated["width"],
                height=generated["height"],
                version=expected_plan_version,
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
                    "render_metadata": generated["render_metadata"],
                },
            )
        except (JobCancelledError, PreviewCancelledError):
            current_state = self.store.get_job(job_id)["state"]
            if current_state not in {"cancelled", "interrupted"}:
                self.store.update_job(job_id, state="cancelled")
                self.broker.publish(
                    job_id,
                    "job_cancelled",
                    state="cancelled",
                    progress=0,
                    message="Preview cancelado",
                )
        except Exception as exc:
            if self.store.get_job(job_id)["state"] == "interrupted":
                return
            guidance = _failure_guidance("preview", str(exc))
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
                message=guidance["cause"],
                data={"action": guidance["action"], "detail": str(exc)[:500]},
            )
        finally:
            with self._control_lock:
                self._controls.pop(job_id, None)

    def shutdown(self, timeout_seconds: float = 2.0) -> None:
        _shutdown_worker(self, timeout_seconds)


class AnalysisWorker:
    """Run transcript analysis outside request threads, then queue previews."""

    def __init__(
        self,
        store: ProjectStore,
        broker: JobEventBroker,
        preview_worker: PreviewWorker,
        *,
        analyze: Optional[Callable[..., dict[str, Any]]] = None,
    ) -> None:
        self.store = store
        self.broker = broker
        self.preview_worker = preview_worker
        if analyze is None:
            from youtube_clipper.analyzer import extract_transcript_and_analyze

            analyze = extract_transcript_and_analyze
        self.analyze = analyze
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="analysis-worker",
        )
        self._controls: dict[str, tuple[threading.Event, Any]] = {}
        self._control_lock = threading.Lock()

    def submit(
        self,
        project_id: str,
        settings: AnalysisJobCreate,
        *,
        attempt: int = 1,
        parent_job_id: Optional[str] = None,
    ) -> dict[str, Any]:
        active = [
            job
            for job in self.store.list_jobs(project_id=project_id, limit=100)
            if job["kind"] == "analysis" and job["state"] in {"queued", "running"}
        ]
        if active:
            raise DomainConflictError("An analysis is already running for this project")
        source = self.store.get_primary_source(project_id)
        analysis = self.store.create_analysis(
            project_id=project_id,
            source_id=source["source_id"],
            status="queued",
        )
        job = self.store.create_job(
            project_id=project_id,
            analysis_id=analysis["analysis_id"],
            kind="analysis",
            state="queued",
            attempt=attempt,
            parent_job_id=parent_job_id,
            payload=settings.model_dump(),
        )
        self.store.update_project_status(project_id, "analyzing")
        self.broker.publish(
            job["job_id"],
            "job_queued",
            state="queued",
            progress=0,
            message="Análise adicionada à fila",
            data={"analysis_id": analysis["analysis_id"]},
        )
        cancellation = threading.Event()
        with self._control_lock:
            future = self._executor.submit(
                self._run_analysis,
                job["job_id"],
                analysis["analysis_id"],
                source["uri"],
                settings.model_dump(),
                cancellation,
            )
            self._controls[job["job_id"]] = (cancellation, future)
        return self.store.get_job(job["job_id"])

    def cancel(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if job["kind"] != "analysis":
            raise DomainConflictError("Job is not an analysis job")
        if job["state"] not in {"queued", "running"}:
            raise DomainConflictError("Only an active job can be cancelled")
        with self._control_lock:
            control = self._controls.get(job_id)
        if control is None:
            raise DomainConflictError("Job is no longer attached to this worker")
        cancellation, future = control
        cancellation.set()
        cancelled_before_start = future.cancel()
        if cancelled_before_start:
            with self._control_lock:
                self._controls.pop(job_id, None)
        self.store.update_job(job_id, state="cancelled", error=None)
        self.store.update_project_status(str(job["project_id"]), "failed")
        if job.get("analysis_id"):
            self.store.fail_analysis(
                str(job["analysis_id"]),
                {"success": False, "error": "Análise cancelada pelo usuário"},
            )
        self.broker.publish(
            job_id,
            "job_cancelled",
            state="cancelled",
            progress=int(job.get("progress") or 0),
            message="Análise cancelada pelo usuário",
            data={"action": "Use Tentar novamente para iniciar outra análise."},
        )
        return self.store.get_job(job_id)

    def _run_analysis(
        self,
        job_id: str,
        analysis_id: str,
        source_uri: str,
        settings: dict[str, Any],
        cancellation: threading.Event,
    ) -> None:
        run_id = f"run_ui4_analysis_{job_id}_{uuid.uuid4().hex}"
        project_id = self.store.get_job(job_id)["project_id"]
        try:
            self.store.update_job(job_id, state="running", run_id=run_id)
            self.broker.publish(
                job_id,
                "stage_start",
                state="running",
                progress=10,
                message="Obtendo transcrição e selecionando cortes",
                data={"stage": "analysis"},
            )
            result = self.analyze(
                source_uri,
                max_clips=int(settings["max_clips"]),
                language=str(settings["language"]),
                target_duration_seconds=int(settings["target_duration_seconds"]),
            )
            if cancellation.is_set():
                raise JobCancelledError("Analysis cancelled")
            if not isinstance(result, dict) or not result.get("success"):
                error = (
                    result.get("error", "A análise não retornou cortes")
                    if isinstance(result, dict)
                    else "A análise retornou uma resposta inválida"
                )
                raise DomainValidationError(str(error))
            self.broker.publish(
                job_id,
                "progress",
                state="running",
                progress=70,
                message="Persistindo candidatos por clip_id",
                data={"stage": "persist"},
            )
            clips = self.store.finish_analysis(
                analysis_id=analysis_id,
                result={
                    **result,
                    "ui_settings": settings,
                },
            )
            self.store.update_project_status(project_id, "review")
            preview_jobs = [
                self.preview_worker.submit(clip["clip_id"])
                for clip in clips
            ]
            self.store.update_job(job_id, state="completed", run_id=run_id)
            self.broker.publish(
                job_id,
                "stage_completed",
                state="completed",
                progress=100,
                message=f"{len(clips)} corte(s) prontos para gerar previews",
                data={
                    "stage": "analysis",
                    "clip_count": len(clips),
                    "preview_job_ids": [item["job_id"] for item in preview_jobs],
                },
            )
        except JobCancelledError:
            current_state = self.store.get_job(job_id)["state"]
            if current_state not in {"cancelled", "interrupted"}:
                self.store.update_job(job_id, state="cancelled")
                self.broker.publish(
                    job_id,
                    "job_cancelled",
                    state="cancelled",
                    progress=0,
                    message="Análise cancelada",
                )
        except Exception as exc:
            if self.store.get_job(job_id)["state"] == "interrupted":
                return
            guidance = _failure_guidance("analysis", str(exc))
            self.store.fail_analysis(analysis_id, {"success": False, "error": str(exc)})
            self.store.update_project_status(project_id, "failed")
            self.store.update_job(
                job_id,
                state="failed",
                run_id=run_id,
                error=str(exc)[:500],
            )
            self.broker.publish(
                job_id,
                "job_failed",
                state="failed",
                progress=100,
                message=guidance["cause"],
                data={"action": guidance["action"], "detail": str(exc)[:500]},
            )
        finally:
            with self._control_lock:
                self._controls.pop(job_id, None)

    def shutdown(self, timeout_seconds: float = 2.0) -> None:
        _shutdown_worker(self, timeout_seconds)


class RenderWorker:
    """Render final media on a queue independent from interactive previews."""

    def __init__(self, store: ProjectStore, broker: JobEventBroker) -> None:
        self.store = store
        self.broker = broker
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="render-worker",
        )
        self._controls: dict[str, tuple[threading.Event, Any]] = {}
        self._control_lock = threading.Lock()

    def submit(
        self,
        clip_id: str,
        *,
        attempt: int = 1,
        parent_job_id: Optional[str] = None,
    ) -> dict[str, Any]:
        clip = self.store.get_clip(clip_id)
        if clip["status"] not in {"approved", "failed"}:
            raise DomainConflictError("Only an approved clip can be rendered")
        if clip["preview_status"] != "ready":
            raise DomainConflictError("Regenerate the preview before final render")
        active = [
            job
            for job in self.store.list_jobs(project_id=clip["project_id"], limit=100)
            if job["clip_id"] == clip_id
            and job["kind"] == "render"
            and job["state"] in {"queued", "running"}
        ]
        if active:
            raise DomainConflictError("A final render is already active for this clip")
        job = self.store.create_job(
            project_id=clip["project_id"],
            clip_id=clip_id,
            kind="render",
            state="queued",
            attempt=attempt,
            parent_job_id=parent_job_id,
        )
        self.broker.publish(
            job["job_id"],
            "job_queued",
            state="queued",
            progress=0,
            message="Render final adicionado à fila",
            data={"clip_id": clip_id},
        )
        self.store.update_clip(clip_id, {"status": "rendering"})
        cancellation = threading.Event()
        with self._control_lock:
            future = self._executor.submit(
                self._run,
                job["job_id"],
                clip_id,
                int(clip["plan_version"]),
                cancellation,
            )
            self._controls[job["job_id"]] = (cancellation, future)
        return self.store.get_job(job["job_id"])

    def cancel(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if job["kind"] != "render":
            raise DomainConflictError("Job is not a render job")
        if job["state"] not in {"queued", "running"}:
            raise DomainConflictError("Only an active job can be cancelled")
        with self._control_lock:
            control = self._controls.get(job_id)
        if control is None:
            raise DomainConflictError("Job is no longer attached to this worker")
        cancellation, future = control
        cancellation.set()
        cancelled_before_start = future.cancel()
        if cancelled_before_start:
            with self._control_lock:
                self._controls.pop(job_id, None)
        self.store.update_job(job_id, state="cancelled", error=None)
        self.store.update_clip(str(job["clip_id"]), {"status": "failed"})
        self.broker.publish(
            job_id,
            "job_cancelled",
            state="cancelled",
            progress=int(job.get("progress") or 0),
            message="Render final cancelado pelo usuário",
            data={"action": "Use Tentar novamente para criar uma nova tentativa."},
        )
        return self.store.get_job(job_id)

    def _run(
        self,
        job_id: str,
        clip_id: str,
        expected_version: int,
        cancellation: threading.Event,
    ) -> None:
        run_id = f"run_ui5_render_{job_id}_{uuid.uuid4().hex}"
        try:
            self.store.update_job(job_id, state="running", run_id=run_id)
            self.broker.publish(
                job_id,
                "stage_start",
                state="running",
                progress=10,
                message="Renderizando mídia final com o plano salvo",
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
                profile="final",
                cancel_event=cancellation,
            )
            if cancellation.is_set():
                raise JobCancelledError("Final render cancelled")
            current = self.store.get_clip(clip_id)
            if int(current["plan_version"]) != expected_version:
                raise DomainConflictError("Edit plan changed during final render")
            asset = self.store.add_asset(
                clip_id=clip_id,
                kind="render",
                source_path=generated["media_path"],
                mime_type="video/mp4",
                plan_version=generated["plan_version"],
                metadata=generated["metadata"],
                duration_ms=generated["duration_ms"],
                width=generated["width"],
                height=generated["height"],
                version=expected_version,
            )
            self.store.create_render(
                clip_id=clip_id,
                asset_id=asset["asset_id"],
                status="rendered",
            )
            self.store.update_clip(clip_id, {"status": "rendered"})
            self.store.update_job(job_id, state="completed", run_id=run_id)
            self.broker.publish(
                job_id,
                "stage_completed",
                state="completed",
                progress=100,
                message="Render final pronto",
                data={
                    "stage": "render",
                    "render_url": asset["url"],
                    "render_metadata": generated["render_metadata"],
                },
            )
        except (JobCancelledError, PreviewCancelledError):
            current_state = self.store.get_job(job_id)["state"]
            if current_state not in {"cancelled", "interrupted"}:
                self.store.update_job(job_id, state="cancelled")
                self.broker.publish(
                    job_id,
                    "job_cancelled",
                    state="cancelled",
                    progress=0,
                    message="Render final cancelado",
                )
        except Exception as exc:
            if self.store.get_job(job_id)["state"] == "interrupted":
                return
            guidance = _failure_guidance("render", str(exc))
            self.store.update_job(
                job_id, state="failed", run_id=run_id, error=str(exc)[:500]
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
                message=guidance["cause"],
                data={"action": guidance["action"], "detail": str(exc)[:500]},
            )
        finally:
            with self._control_lock:
                self._controls.pop(job_id, None)

    def shutdown(self, timeout_seconds: float = 2.0) -> None:
        _shutdown_worker(self, timeout_seconds)


class DriveExportWorker:
    """Upload a validated final render without blocking an API request."""

    def __init__(
        self,
        store: ProjectStore,
        broker: JobEventBroker,
        upload: Optional[Callable[..., dict[str, Any]]] = None,
    ) -> None:
        self.store = store
        self.broker = broker
        if upload is None:
            from youtube_clipper.gdrive_uploader import upload_clip_to_gdrive

            upload = upload_clip_to_gdrive
        self.upload = upload
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="drive-export-worker",
        )
        self._controls: dict[str, tuple[threading.Event, Any]] = {}
        self._control_lock = threading.Lock()

    def submit(
        self,
        clip_id: str,
        payload: DriveExportCreate,
        *,
        attempt: int = 1,
        parent_job_id: Optional[str] = None,
    ) -> dict[str, Any]:
        clip = self.store.get_clip(clip_id)
        asset = self.store.get_latest_asset(clip_id, "render")
        if clip["status"] not in {"rendered", "exported"}:
            raise DomainConflictError("Only a completed final render can be exported")
        active = [
            job
            for job in self.store.list_jobs(project_id=clip["project_id"], limit=100)
            if job["clip_id"] == clip_id
            and job["kind"] == "drive_upload"
            and job["state"] in {"queued", "running"}
        ]
        if active:
            raise DomainConflictError("A Drive export is already active for this clip")
        job = self.store.create_job(
            project_id=clip["project_id"],
            clip_id=clip_id,
            kind="drive_upload",
            state="queued",
            attempt=attempt,
            parent_job_id=parent_job_id,
            payload=payload.model_dump(),
        )
        self.broker.publish(
            job["job_id"],
            "job_queued",
            state="queued",
            progress=0,
            message="Envio ao Drive adicionado à fila",
            data={"stage": "export", "asset_id": asset["asset_id"]},
        )
        cancellation = threading.Event()
        with self._control_lock:
            future = self._executor.submit(
                self._run,
                job["job_id"],
                clip_id,
                asset["asset_id"],
                int(asset["version"]),
                payload,
                cancellation,
            )
            self._controls[job["job_id"]] = (cancellation, future)
        return self.store.get_job(job["job_id"])

    def cancel(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if job["kind"] != "drive_upload":
            raise DomainConflictError("Job is not a Drive export")
        if job["state"] not in {"queued", "running"}:
            raise DomainConflictError("Only an active job can be cancelled")
        with self._control_lock:
            control = self._controls.get(job_id)
        if control is None:
            raise DomainConflictError("Job is no longer attached to this worker")
        cancellation, future = control
        cancellation.set()
        cancelled_before_start = future.cancel()
        if cancelled_before_start:
            with self._control_lock:
                self._controls.pop(job_id, None)
        self.store.update_job(job_id, state="cancelled", error=None)
        self.broker.publish(
            job_id,
            "job_cancelled",
            state="cancelled",
            progress=int(job.get("progress") or 0),
            message="Envio ao Drive cancelado",
            data={"action": "Confirme o destino antes de tentar novamente."},
        )
        return self.store.get_job(job_id)

    def _run(
        self,
        job_id: str,
        clip_id: str,
        asset_id: str,
        version: int,
        payload: DriveExportCreate,
        cancellation: threading.Event,
    ) -> None:
        run_id = f"run_ui7_drive_{job_id}_{uuid.uuid4().hex}"
        try:
            if cancellation.is_set():
                raise JobCancelledError("Drive export cancelled")
            self.store.update_job(job_id, state="running", run_id=run_id)
            self.broker.publish(
                job_id,
                "stage_start",
                state="running",
                progress=10,
                message="Autenticando e preparando envio ao Drive",
                data={"stage": "export"},
            )
            _, path = self.store.resolve_asset_file(asset_id, version=version)
            result = self.upload(
                str(path),
                folder_id=payload.folder_id,
                folder_name=payload.folder_name,
                run_id=run_id,
            )
            if cancellation.is_set():
                raise JobCancelledError("Drive export cancelled")
            if not isinstance(result, dict) or not result.get("success"):
                detail = (
                    result.get("error", "O Drive não confirmou o upload")
                    if isinstance(result, dict)
                    else "Resposta inválida do Google Drive"
                )
                raise DomainValidationError(str(detail))
            self.store.update_clip(clip_id, {"status": "exported"})
            self.store.update_job(job_id, state="completed", run_id=run_id)
            self.broker.publish(
                job_id,
                "stage_completed",
                state="completed",
                progress=100,
                message="Arquivo enviado ao Google Drive",
                data={
                    "stage": "export",
                    "web_view_link": result.get("web_view_link"),
                    "file_id": result.get("file_id"),
                },
            )
        except JobCancelledError:
            current_state = self.store.get_job(job_id)["state"]
            if current_state not in {"cancelled", "interrupted"}:
                self.store.update_job(job_id, state="cancelled")
                self.broker.publish(
                    job_id,
                    "job_cancelled",
                    state="cancelled",
                    progress=0,
                    message="Envio ao Drive cancelado",
                )
        except Exception as exc:
            if self.store.get_job(job_id)["state"] == "interrupted":
                return
            guidance = _failure_guidance("drive_upload", str(exc))
            self.store.update_job(
                job_id,
                state="failed",
                run_id=run_id,
                error=str(exc)[:500],
            )
            self.broker.publish(
                job_id,
                "job_failed",
                state="failed",
                progress=100,
                message=guidance["cause"],
                data={"action": guidance["action"], "detail": str(exc)[:500]},
            )
        finally:
            with self._control_lock:
                self._controls.pop(job_id, None)

    def shutdown(self, timeout_seconds: float = 2.0) -> None:
        _shutdown_worker(self, timeout_seconds)


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
    analyze: Optional[Callable[..., dict[str, Any]]] = None,
    drive_upload: Optional[Callable[..., dict[str, Any]]] = None,
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
    broker = JobEventBroker(domain_store)
    preview_worker = PreviewWorker(domain_store, broker)
    analysis_worker = AnalysisWorker(
        domain_store,
        broker,
        preview_worker,
        analyze=analyze,
    )
    render_worker = RenderWorker(domain_store, broker)
    drive_worker = DriveExportWorker(
        domain_store,
        broker,
        upload=drive_upload,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        _reconcile_orphaned_jobs(domain_store, broker)
        yield
        try:
            shutdown_timeout = float(
                os.environ.get("YOUTUBE_CLIPPER_SHUTDOWN_TIMEOUT_SECONDS", "2")
            )
        except ValueError:
            shutdown_timeout = 2.0
        shutdown_timeout = max(0.0, min(10.0, shutdown_timeout))
        analysis_worker.shutdown(shutdown_timeout)
        preview_worker.shutdown(shutdown_timeout)
        render_worker.shutdown(shutdown_timeout)
        drive_worker.shutdown(shutdown_timeout)

    app = FastAPI(
        title="YouTube Clipper API",
        version="1.0.0",
        description="Versioned project, clip, asset, and job API.",
        lifespan=lifespan,
    )
    app.state.store = domain_store
    app.state.job_events = broker
    app.state.preview_worker = preview_worker
    app.state.analysis_worker = analysis_worker
    app.state.render_worker = render_worker
    app.state.drive_worker = drive_worker
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

    @app.post(
        "/api/v1/projects/{project_id}/analysis-jobs",
        response_model=PreviewJobResponse,
        status_code=202,
    )
    async def create_analysis_job(
        project_id: str,
        payload: AnalysisJobCreate,
    ) -> PreviewJobResponse:
        return PreviewJobResponse(job=analysis_worker.submit(project_id, payload))

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

    @app.put(
        "/api/v1/clips/{clip_id}/edit-plan",
        response_model=ClipResponse,
    )
    async def update_edit_plan(
        clip_id: str,
        payload: EditPlanUpdate,
    ) -> ClipResponse:
        clip = domain_store.get_clip(clip_id)
        active_render = any(
            job["kind"] == "render"
            and job["clip_id"] == clip_id
            and job["state"] in {"queued", "running"}
            for job in domain_store.list_jobs(
                project_id=clip["project_id"],
                limit=100,
            )
        )
        if active_render:
            raise DomainConflictError("Clip is locked while final render is active")
        changes = payload.model_dump(
            exclude={"expected_plan_version"},
            exclude_none=True,
        )
        return ClipResponse(
            clip=domain_store.update_clip(
                clip_id,
                changes,
                expected_plan_version=payload.expected_plan_version,
            )
        )

    @app.post(
        "/api/v1/clips/review",
        response_model=ClipReviewResponse,
    )
    async def review_clips(payload: ClipReviewCreate) -> ClipReviewResponse:
        return ClipReviewResponse(
            clips=domain_store.review_clips(payload.clip_ids, payload.decision)
        )

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
        return PreviewJobResponse(job=preview_worker.submit(clip_id))

    @app.post(
        "/api/v1/clips/{clip_id}/render-jobs",
        response_model=PreviewJobResponse,
        status_code=202,
    )
    async def create_render_job(clip_id: str) -> PreviewJobResponse:
        return PreviewJobResponse(job=render_worker.submit(clip_id))

    @app.post(
        "/api/v1/clips/{clip_id}/drive-jobs",
        response_model=PreviewJobResponse,
        status_code=202,
    )
    async def create_drive_job(
        clip_id: str,
        payload: DriveExportCreate,
    ) -> PreviewJobResponse:
        return PreviewJobResponse(job=drive_worker.submit(clip_id, payload))

    @app.post(
        "/api/v1/jobs/{job_id}/cancel",
        response_model=JobResponse,
    )
    async def cancel_job(job_id: str) -> JobResponse:
        job = domain_store.get_job(job_id)
        workers = {
            "analysis": analysis_worker,
            "preview": preview_worker,
            "render": render_worker,
            "drive_upload": drive_worker,
        }
        worker = workers.get(str(job["kind"]))
        if worker is None:
            raise DomainConflictError("This job type cannot be cancelled")
        return JobResponse(job=worker.cancel(job_id))

    @app.post(
        "/api/v1/jobs/{job_id}/retry",
        response_model=PreviewJobResponse,
        status_code=202,
    )
    async def retry_job(job_id: str) -> PreviewJobResponse:
        job = domain_store.get_job(job_id)
        if job["state"] not in {"failed", "cancelled", "interrupted"}:
            raise DomainConflictError("Only a failed, cancelled, or interrupted job can be retried")
        attempt = int(job["attempt"]) + 1
        kind = str(job["kind"])
        if kind == "analysis":
            settings = AnalysisJobCreate.model_validate(job.get("payload") or {})
            retried = analysis_worker.submit(
                str(job["project_id"]),
                settings,
                attempt=attempt,
                parent_job_id=job_id,
            )
        elif kind == "preview":
            retried = preview_worker.submit(
                str(job["clip_id"]),
                attempt=attempt,
                parent_job_id=job_id,
            )
        elif kind == "render":
            retried = render_worker.submit(
                str(job["clip_id"]),
                attempt=attempt,
                parent_job_id=job_id,
            )
        elif kind == "drive_upload":
            payload = DriveExportCreate.model_validate(job.get("payload") or {})
            retried = drive_worker.submit(
                str(job["clip_id"]),
                payload,
                attempt=attempt,
                parent_job_id=job_id,
            )
        else:
            raise DomainConflictError("This job type cannot be retried")
        return PreviewJobResponse(job=retried)

    @app.get("/api/v1/jobs/{job_id}/report")
    async def job_report(job_id: str) -> JSONResponse:
        job = domain_store.get_job(job_id)
        clip = (
            domain_store.get_clip(str(job["clip_id"]))
            if job.get("clip_id")
            else None
        )
        return JSONResponse(
            {
                "success": True,
                "report": {
                    "schema_version": "1.0.0",
                    "job": job,
                    "events": domain_store.list_job_events(job_id),
                    "clip": clip,
                    "generated_at_ms": int(time.time() * 1000),
                },
            },
            headers={
                "Content-Disposition": f'attachment; filename="{job_id}.json"'
            },
        )

    @app.get("/api/v1/clips/{clip_id}/export/download")
    async def download_final_render(
        clip_id: str,
        request: Request,
    ) -> Response:
        clip = domain_store.get_clip(clip_id)
        if clip["status"] not in {"rendered", "exported"}:
            raise DomainConflictError("A final render is required before download")
        render_asset = domain_store.get_latest_asset(clip_id, "render")
        asset, path = domain_store.resolve_asset_file(
            render_asset["asset_id"],
            version=int(render_asset["version"]),
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
        safe_title = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(clip["title"])).strip("-")
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Disposition": f'attachment; filename="{safe_title or clip_id}.mp4"',
            "Cache-Control": "private, no-store",
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
