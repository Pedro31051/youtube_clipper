"""
Web Dashboard Server for YouTube Clipper & AI Analyzer with Google Drive Integration.
Provides a modern glassmorphism web panel interface for analyzing YouTube videos,
previewing AI recommended viral clips, generating vertical Shorts (9:16), and saving directly to Google Drive.
"""

import functools
import base64
import binascii
import hashlib
import os
import json
import math
import re
import shutil
import sys
import threading
import urllib.parse
import hmac
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from youtube_clipper.analyzer import extract_transcript_and_analyze
from cortes.dashboard_pipeline import run_dashboard_clip_pipeline as run_pipeline
from youtube_clipper.gdrive_uploader import upload_clip_to_gdrive
from youtube_clipper.exceptions import ClipperError, ValidationError, DownloadError
from youtube_clipper.validator import is_youtube_url, validate_input_source, validate_time_range
from youtube_clipper.gemini_editor import (
    GeminiConfigurationError,
    GeminiEditorError,
    GeminiInputError,
    request_gemini_edit,
)
from youtube_clipper.project_store import (
    DomainConflictError,
    DomainNotFoundError,
    DomainValidationError,
    ProjectStore,
)
from cortes.log import action_span, audited, run_context
from cortes.ingest import probe_video_metadata
from cortes.pipeline import run_full_pipeline
from cortes.preview import generate_clip_preview
from cortes.verify import verify_run


def observed_http_request(func):
    """Create an isolated and sealed audit run for each HTTP request."""
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        request_id = self._normalize_request_id(
            self.headers.get("X-Request-ID")
        )
        route = urllib.parse.urlsplit(self.path).path
        if route.startswith(self.STATUS_ROUTE_PREFIX):
            self._audit_request_id = request_id
            self._audit_run_id = None
            self._audit_response_status = None
            self._audit_authorized = None
            return func(self, *args, **kwargs)
        action = f"http.{self.command.lower()}.{route}"
        with run_context(
            request_id=request_id,
            actions=[{"action": action, "stage": "env"}],
            component="youtube_clipper.dashboard",
        ) as run_id:
            self._audit_request_id = request_id
            self._audit_run_id = run_id
            if not route.startswith(self.STATUS_ROUTE_PREFIX):
                self._register_request_run(request_id, run_id)
            with action_span(
                "env",
                action,
                component="youtube_clipper.dashboard",
                input_data={
                    "method": self.command,
                    "path": route,
                    "content_length": self.headers.get("Content-Length", "0"),
                    "remote_address": self.client_address[0] if self.client_address else None,
                },
            ) as span:
                self._audit_response_status = None
                self._audit_authorized = None
                result = func(self, *args, **kwargs)
                span.decision = {
                    "http_status": self._audit_response_status,
                    "authorized": self._audit_authorized,
                }
                if self._audit_response_status is not None and self._audit_response_status >= 400:
                    span.mark_failed(
                        f"HTTP request returned {self._audit_response_status}",
                        category="http",
                        retryable=self._audit_response_status >= 500,
                    )
                return result
    return wrapper


_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
HTML_TEMPLATE = (_TEMPLATE_DIR / "legacy_dashboard.html").read_text(encoding="utf-8")
TECHNICAL_HTML_TEMPLATE = (_TEMPLATE_DIR / "legacy_technical.html").read_text(encoding="utf-8")


TECHNICAL_VIDEO_EXTENSIONS = {
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".webm",
}
TECHNICAL_AUDIO_EXTENSIONS = {
    ".aac",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
}
TECHNICAL_WHISPER_MODELS = {
    "tiny",
    "tiny.en",
    "base",
    "base.en",
    "small",
    "small.en",
    "medium",
    "medium.en",
    "large-v1",
    "large-v2",
    "large-v3",
    "distil-small.en",
    "distil-medium.en",
    "distil-large-v2",
    "distil-large-v3",
    "turbo",
}
TECHNICAL_PAYLOAD_FIELDS = {
    "phase",
    "input_path",
    "whisper_model",
    "device",
    "language",
    "scene_threshold",
    "min_scene_len",
    "vertical_mode",
    "blur_sigma",
    "subtitle_font_name",
    "subtitle_font_size",
    "subtitle_margin_v",
    "analytical_overlay",
    "overlay_text",
    "narration_path",
    "template_variant",
}
TECHNICAL_TEMPLATE_VARIANT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")


def _technical_number(
    payload: dict,
    field: str,
    default: int | float,
    minimum: int | float,
    maximum: int | float,
    *,
    integer: bool = False,
) -> int | float:
    raw_value = payload.get(field, default)
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        kind = "an integer" if integer else "a number"
        raise ValidationError(f"{field} must be {kind}", field=field)
    value = float(raw_value)
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValidationError(
            f"{field} must be between {minimum} and {maximum}", field=field
        )
    if integer:
        if not value.is_integer():
            raise ValidationError(f"{field} must be an integer", field=field)
        return int(value)
    return value


def _technical_local_file(
    raw_value: object,
    *,
    field: str,
    extensions: set[str],
    required: bool,
) -> Path | None:
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
        if required:
            raise ValidationError(f"{field} is required", field=field)
        return None
    if not isinstance(raw_value, str):
        raise ValidationError(f"{field} must be a local file path", field=field)
    value = raw_value.strip()
    if len(value) > 4096 or "\x00" in value or "://" in value:
        raise ValidationError(f"{field} must be a local file path", field=field)
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme or parsed.netloc:
        raise ValidationError(f"{field} must be a local file path", field=field)
    path = Path(value).expanduser().resolve()
    if path.suffix.lower() not in extensions:
        supported = ", ".join(sorted(extensions))
        raise ValidationError(
            f"{field} must use a supported media extension: {supported}", field=field
        )
    if not path.exists() or not path.is_file():
        raise ValidationError(f"Local file does not exist: {path}", field=field)
    return path


def validate_technical_payload(payload: dict) -> dict:
    """Validate and normalize the separate local T2/T3 dashboard contract."""
    unknown_fields = sorted(set(payload) - TECHNICAL_PAYLOAD_FIELDS)
    if unknown_fields:
        raise ValidationError(
            f"Unsupported field(s): {', '.join(unknown_fields)}",
            field=unknown_fields[0],
        )

    phase = payload.get("phase")
    if not isinstance(phase, str) or phase not in {"t2", "t3"}:
        raise ValidationError("phase must be t2 or t3", field="phase")

    input_path = _technical_local_file(
        payload.get("input_path"),
        field="input_path",
        extensions=TECHNICAL_VIDEO_EXTENSIONS,
        required=True,
    )

    whisper_model = payload.get("whisper_model", "small")
    if not isinstance(whisper_model, str) or whisper_model not in TECHNICAL_WHISPER_MODELS:
        raise ValidationError("whisper_model is not supported", field="whisper_model")

    device = payload.get("device", "cpu")
    if not isinstance(device, str) or device not in {"cpu", "cuda"}:
        raise ValidationError("device must be cpu or cuda", field="device")

    language = payload.get("language")
    if language is None or language == "":
        language = None
    elif not isinstance(language, str) or not re.fullmatch(r"[A-Za-z]{2,5}", language):
        raise ValidationError(
            "language must be a 2-5 letter language code or null", field="language"
        )
    else:
        language = language.lower()

    scene_threshold = _technical_number(
        payload, "scene_threshold", 27.0, 0.1, 100.0
    )
    min_scene_len = _technical_number(payload, "min_scene_len", 0.6, 0.1, 60.0)

    vertical_mode = payload.get("vertical_mode", "blur_background")
    if (
        not isinstance(vertical_mode, str)
        or vertical_mode not in {"blur_background", "split_blur", "crop_center"}
    ):
        raise ValidationError(
            "vertical_mode must be blur_background, split_blur, or crop_center",
            field="vertical_mode",
        )
    raw_blur_sigma = payload.get("blur_sigma", 12.0)
    if vertical_mode == "crop_center":
        if "blur_sigma" in payload and raw_blur_sigma is not None:
            raise ValidationError(
                "blur_sigma must be null when vertical_mode is crop_center",
                field="blur_sigma",
            )
        blur_sigma = 12.0
    else:
        if raw_blur_sigma is None:
            raise ValidationError(
                "blur_sigma is required for a blurred vertical mode",
                field="blur_sigma",
            )
        blur_sigma = _technical_number(payload, "blur_sigma", 12.0, 0.0, 50.0)

    subtitle_font_name = payload.get("subtitle_font_name", "Roboto")
    if (
        not isinstance(subtitle_font_name, str)
        or not re.fullmatch(r"[\w .-]{1,64}", subtitle_font_name.strip())
    ):
        raise ValidationError(
            "subtitle_font_name contains unsupported characters",
            field="subtitle_font_name",
        )
    subtitle_font_name = subtitle_font_name.strip()
    subtitle_font_size = _technical_number(
        payload, "subtitle_font_size", 80, 16, 160, integer=True
    )
    subtitle_margin_v = _technical_number(
        payload, "subtitle_margin_v", 400, 0, 1600, integer=True
    )

    analytical_overlay = payload.get("analytical_overlay", False)
    if not isinstance(analytical_overlay, bool):
        raise ValidationError(
            "analytical_overlay must be a boolean", field="analytical_overlay"
        )
    raw_overlay_text = payload.get("overlay_text")
    if analytical_overlay:
        if not isinstance(raw_overlay_text, str):
            raise ValidationError(
                "overlay_text is required when analytical_overlay is enabled",
                field="overlay_text",
            )
        overlay_text = raw_overlay_text.strip()
        if not overlay_text or len(overlay_text) > 120:
            raise ValidationError(
                "overlay_text must contain 1-120 characters", field="overlay_text"
            )
        if re.search(r"[\x00-\x1f\x7f\\'\[\];%]", overlay_text):
            raise ValidationError(
                "overlay_text contains characters unsupported by the renderer",
                field="overlay_text",
            )
    else:
        if raw_overlay_text is not None and raw_overlay_text != "":
            raise ValidationError(
                "overlay_text must be null when analytical_overlay is disabled",
                field="overlay_text",
            )
        overlay_text = None

    narration_path = _technical_local_file(
        payload.get("narration_path"),
        field="narration_path",
        extensions=TECHNICAL_AUDIO_EXTENSIONS,
        required=False,
    )

    template_variant = payload.get(
        "template_variant", "variant_default" if phase == "t2" else None
    )
    if not isinstance(template_variant, str):
        raise ValidationError("template_variant is required", field="template_variant")
    template_variant = template_variant.strip().lower()
    if not TECHNICAL_TEMPLATE_VARIANT_PATTERN.fullmatch(template_variant):
        raise ValidationError(
            "template_variant must contain 3-64 lowercase letters, numbers, '_' or '-'",
            field="template_variant",
        )

    require_editorial_transformation = phase == "t3"
    if require_editorial_transformation:
        if template_variant == "variant_default":
            raise ValidationError(
                "T3 requires a non-default template_variant", field="template_variant"
            )
        if not analytical_overlay and narration_path is None:
            raise ValidationError(
                "T3 requires analytical_overlay and/or narration_path", field="phase"
            )

    return {
        "phase": phase,
        "input_path": input_path,
        "whisper_model": whisper_model,
        "device": device,
        "language": language,
        "scene_threshold": scene_threshold,
        "min_scene_len": min_scene_len,
        "vertical_mode": vertical_mode,
        "blur_sigma": blur_sigma,
        "subtitle_font_name": subtitle_font_name,
        "subtitle_font_size": subtitle_font_size,
        "subtitle_margin_v": subtitle_margin_v,
        "analytical_overlay": analytical_overlay,
        "overlay_text": overlay_text,
        "narration_path": narration_path,
        "template_variant": template_variant,
        "require_editorial_transformation": require_editorial_transformation,
    }


class ClipperDashboardHandler(BaseHTTPRequestHandler):
    """Multi-threaded HTTP Request Handler for YouTube Clipper Dashboard & REST API."""

    GET_ROUTES = {"/", "/index.html"}
    TECHNICAL_GET_ROUTES = {"/technical", "/cortes"}
    POST_ROUTES = {
        "/api/analyze",
        "/api/editor-chat",
        "/api/editor-assets",
        "/api/generate-clip",
        "/api/gdrive-upload",
        "/api/cortes/run",
    }
    STATUS_ROUTE_PREFIX = "/api/status/"
    REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
    ASSET_ID_PATTERN = re.compile(r"^asset_[a-f0-9]{32}\.(?:aac|flac|jpe?g|m4a|mp3|ogg|png|wav|webp)$")
    MAX_REQUEST_BODY_BYTES = 36 * 1024 * 1024
    MAX_EDITOR_ASSET_FILES = 200
    MAX_EDITOR_ASSET_STORAGE_BYTES = 512 * 1024 * 1024
    EDITOR_ASSET_POLICIES = {
        "music": {
            "extensions": {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"},
            "mime_types": {
                "audio/aac",
                "audio/flac",
                "audio/m4a",
                "audio/mp4",
                "audio/mpeg",
                "audio/ogg",
                "audio/wav",
                "audio/x-wav",
            },
            "max_bytes": 25 * 1024 * 1024,
        },
        "intro_image": {
            "extensions": {".jpeg", ".jpg", ".png", ".webp"},
            "mime_types": {"image/jpeg", "image/png", "image/webp"},
            "max_bytes": 8 * 1024 * 1024,
        },
    }
    REQUEST_REGISTRY_LOCK = threading.Lock()
    ASSET_STORAGE_LOCK = threading.Lock()
    DOMAIN_STORE_LOCK = threading.Lock()
    API_V1_PREFIX = "/api/v1/"
    PROJECT_ID_ROUTE = re.compile(
        r"\A/api/v1/projects/(prj_[0-9a-f]{32})\Z"
    )
    PROJECT_CLIPS_ROUTE = re.compile(
        r"\A/api/v1/projects/(prj_[0-9a-f]{32})/clips\Z"
    )
    PROJECT_ANALYSIS_ROUTE = re.compile(
        r"\A/api/v1/projects/(prj_[0-9a-f]{32})/analysis-jobs\Z"
    )
    CLIP_ID_ROUTE = re.compile(
        r"\A/api/v1/clips/(clp_[0-9a-f]{32})\Z"
    )
    JOB_ID_ROUTE = re.compile(
        r"\A/api/v1/jobs/(job_[0-9a-f]{32})\Z"
    )
    CLIP_PREVIEW_ROUTE = re.compile(
        r"\A/api/v1/clips/(clp_[0-9a-f]{32})/preview-jobs\Z"
    )
    DOMAIN_ASSET_ROUTE = re.compile(
        r"\A/api/v1/assets/(ast_[0-9a-f]{32})\Z"
    )

    def _domain_store(self) -> ProjectStore:
        store = vars(self.server).get("project_store")
        if isinstance(store, ProjectStore):
            return store
        with self.DOMAIN_STORE_LOCK:
            store = vars(self.server).get("project_store")
            if isinstance(store, ProjectStore):
                return store
            workspace = Path(
                vars(self.server).get(
                    "panel_workspace", Path.cwd() / "panel_workspace"
                )
            ).resolve()
            workspace.mkdir(parents=True, exist_ok=True)
            store = ProjectStore(
                database_path=workspace / "projects.sqlite3",
                workspace_dir=workspace,
            )
            self.server.project_store = store
            return store

    def _send_domain_error(self, error: Exception) -> None:
        if isinstance(error, DomainNotFoundError):
            status_code = 404
        elif isinstance(error, DomainConflictError):
            status_code = 409
        else:
            status_code = 400
        self.send_json(
            status_code,
            {"success": False, "error": str(error)},
            no_store=True,
        )


    @classmethod
    def _normalize_request_id(cls, raw_request_id: str | None) -> str:
        candidate = str(raw_request_id or "").strip()
        if cls.REQUEST_ID_PATTERN.fullmatch(candidate):
            return candidate
        return uuid.uuid4().hex

    def _register_request_run(self, request_id: str, run_id: str) -> None:
        """Associate an audited run with the browser operation that created it."""
        with self.REQUEST_REGISTRY_LOCK:
            registry = vars(self.server).get("request_runs")
            if registry is None:
                registry = {}
                self.server.request_runs = registry
            run_ids = registry.setdefault(request_id, [])
            if run_id not in run_ids:
                run_ids.append(run_id)
            while len(registry) > 256:
                registry.pop(next(iter(registry)))

    def _registered_request_runs(self, request_id: str) -> list[str]:
        with self.REQUEST_REGISTRY_LOCK:
            registry = vars(self.server).get("request_runs", {})
            return list(registry.get(request_id, []))

    def _new_child_run(self, label: str) -> str:
        safe_label = re.sub(r"[^a-z0-9_-]+", "-", label.lower()).strip("-")
        run_id = f"run_dashboard_{safe_label}_{uuid.uuid4().hex}"
        self._register_request_run(self._audit_request_id, run_id)
        return run_id

    def _request_status_payload(self, request_id: str) -> dict | None:
        run_ids = self._registered_request_runs(request_id)
        if not run_ids:
            return None

        runs_root = Path.cwd() / "runs"
        public_events = []
        drive_events = []
        all_sealed = True
        failed = False

        for run_id in run_ids:
            run_dir = runs_root / run_id
            events_file = run_dir / "events.jsonl"
            seal_file = run_dir / "seal.json"
            all_sealed = all_sealed and seal_file.exists()

            if seal_file.exists():
                try:
                    seal_data = json.loads(seal_file.read_text(encoding="utf-8"))
                    failed = failed or seal_data.get("status") == "failed"
                except (OSError, ValueError, TypeError):
                    failed = True

            if not events_file.exists():
                continue

            try:
                lines = events_file.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue

            for line in lines:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if event.get("request_id") != request_id:
                    continue

                status = str(event.get("status") or "")
                if event.get("component") != "subprocess":
                    failed = failed or status == "failed"
                error_data = event.get("error")
                error_message = None
                if isinstance(error_data, dict):
                    category = str(error_data.get("category") or "application")
                    exit_code = error_data.get("exit_code")
                    error_type = str(error_data.get("type") or "error")
                    if exit_code is not None:
                        error_message = f"{category} ({error_type}), código {exit_code}"
                    else:
                        error_message = f"{category} ({error_type})"
                elif error_data:
                    error_message = "application (error)"

                public_events.append(
                    {
                        "event_id": event.get("event_id"),
                        "run_id": event.get("run_id"),
                        "seq": event.get("seq"),
                        "ts": event.get("ts"),
                        "stage": event.get("stage"),
                        "status": status,
                        "component": event.get("component"),
                        "action": event.get("action"),
                        "duration_ms": event.get("duration_ms"),
                        "error": error_message,
                    }
                )

                if event.get("component") == "youtube_clipper.gdrive":
                    raw_decision = event.get("decision")
                    safe_decision = {}
                    if isinstance(raw_decision, dict):
                        for key in (
                            "progress_percent",
                            "uploaded_bytes",
                            "total_bytes",
                            "chunk_number",
                            "indeterminate",
                        ):
                            value = raw_decision.get(key)
                            if key == "indeterminate":
                                if isinstance(value, bool):
                                    safe_decision[key] = value
                            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                                numeric = float(value)
                                if math.isfinite(numeric):
                                    safe_decision[key] = numeric
                    attempt = event.get("attempt")
                    drive_events.append(
                        {
                            "run_id": event.get("run_id"),
                            "seq": event.get("seq"),
                            "ts": event.get("ts"),
                            "status": status,
                            "action": str(event.get("action") or ""),
                            "attempt": (
                                int(attempt)
                                if isinstance(attempt, (int, float)) and not isinstance(attempt, bool)
                                else None
                            ),
                            "progress": safe_decision,
                        }
                    )

        public_events.sort(
            key=lambda item: (
                str(item.get("ts") or ""),
                str(item.get("run_id") or ""),
                int(item.get("seq") or 0),
            )
        )
        drive_events.sort(
            key=lambda item: (
                str(item.get("ts") or ""),
                str(item.get("run_id") or ""),
                int(item.get("seq") or 0),
            )
        )
        drive_upload = None
        for drive_event in drive_events:
            action = drive_event["action"]
            event_status = drive_event["status"]
            progress = drive_event["progress"]
            if drive_upload is None:
                drive_upload = {
                    "state": "pending",
                    "determinate": False,
                    "progress_percent": None,
                    "uploaded_bytes": None,
                    "total_bytes": None,
                    "chunk_number": None,
                    "attempt": None,
                    "updated_at": drive_event.get("ts"),
                }
            drive_upload["updated_at"] = drive_event.get("ts")

            if event_status == "started" and (
                action.startswith("gdrive.auth.") or action == "gdrive.build_client"
            ):
                drive_upload["state"] = "authenticating"
                drive_upload["determinate"] = False
            elif event_status == "started" and action == "gdrive.resolve_folder":
                drive_upload["state"] = "preparing"
                drive_upload["determinate"] = False
            elif event_status == "failed" and (
                action.startswith("gdrive.auth.")
                or action in {"gdrive.build_client", "gdrive.resolve_folder"}
            ):
                drive_upload["state"] = "failed"
                drive_upload["determinate"] = False
            elif action.startswith("gdrive.upload.progress."):
                indeterminate = progress.get("indeterminate") is True
                percent = progress.get("progress_percent")
                uploaded = progress.get("uploaded_bytes")
                total = progress.get("total_bytes")
                chunk = progress.get("chunk_number")
                if total is not None:
                    drive_upload["total_bytes"] = max(0, int(total))
                if indeterminate:
                    drive_upload["state"] = "uploading"
                    drive_upload["determinate"] = False
                    drive_upload["progress_percent"] = None
                    drive_upload["uploaded_bytes"] = None
                else:
                    previous_percent = drive_upload.get("progress_percent")
                    normalized_percent = max(0.0, min(100.0, float(percent or 0.0)))
                    if isinstance(previous_percent, (int, float)):
                        normalized_percent = max(float(previous_percent), normalized_percent)
                    previous_uploaded = drive_upload.get("uploaded_bytes")
                    normalized_uploaded = max(0, int(uploaded or 0))
                    if isinstance(previous_uploaded, int):
                        normalized_uploaded = max(previous_uploaded, normalized_uploaded)
                    if isinstance(drive_upload.get("total_bytes"), int):
                        normalized_uploaded = min(
                            normalized_uploaded, drive_upload["total_bytes"]
                        )
                    drive_upload["state"] = (
                        "uploaded" if normalized_percent >= 100.0 else "uploading"
                    )
                    drive_upload["determinate"] = True
                    drive_upload["progress_percent"] = round(normalized_percent, 2)
                    drive_upload["uploaded_bytes"] = normalized_uploaded
                    drive_upload["chunk_number"] = (
                        max(0, int(chunk)) if chunk is not None else None
                    )
            elif action == "gdrive.upload" and event_status == "retrying":
                drive_upload["state"] = "retrying"
                drive_upload["attempt"] = drive_event.get("attempt")
            elif action == "gdrive.upload" and event_status == "failed":
                drive_upload["state"] = "failed"
            elif action == "gdrive.upload" and event_status == "succeeded":
                drive_upload["state"] = "uploaded"
                drive_upload["determinate"] = True
                drive_upload["progress_percent"] = 100.0
                if isinstance(drive_upload.get("total_bytes"), int):
                    drive_upload["uploaded_bytes"] = drive_upload["total_bytes"]
            elif action == "gdrive.set_permission" and event_status == "started":
                drive_upload["state"] = "finalizing"
            elif action == "gdrive.set_permission" and event_status == "succeeded":
                drive_upload["state"] = "succeeded"
            elif action == "gdrive.set_permission" and event_status == "failed":
                drive_upload["state"] = "link_warning"

        state = "failed" if failed else ("completed" if all_sealed else "running")
        return {
            "success": True,
            "request_id": request_id,
            "state": state,
            "completed": all_sealed,
            "run_ids": run_ids,
            "events": public_events[-250:],
            "drive_upload": drive_upload,
        }

    def _output_dir(self) -> Path:
        configured = vars(self.server).get("output_dir", Path.cwd() / "output")
        return Path(configured).resolve()

    def _asset_dir(self) -> Path:
        output_dir = self._output_dir()
        asset_dir = (output_dir / "_editor_assets").resolve()
        asset_dir.relative_to(output_dir)
        asset_dir.mkdir(parents=True, exist_ok=True)
        return asset_dir

    @staticmethod
    def _asset_signature_matches(kind: str, extension: str, data: bytes) -> bool:
        """Apply a small allow-list signature check before FFmpeg sees an upload."""
        if kind == "intro_image":
            if extension in {".jpg", ".jpeg"}:
                return len(data) >= 3 and data.startswith(b"\xff\xd8\xff")
            if extension == ".png":
                return data.startswith(b"\x89PNG\r\n\x1a\n")
            if extension == ".webp":
                return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
            return False
        if extension in {".aac", ".mp3"}:
            return data.startswith(b"ID3") or (
                len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0
            )
        if extension == ".wav":
            return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"
        if extension == ".flac":
            return data.startswith(b"fLaC")
        if extension == ".ogg":
            return data.startswith(b"OggS")
        if extension == ".m4a":
            return len(data) >= 12 and data[4:8] == b"ftyp"
        return False

    @audited(
        stage="ingest",
        action="editor.store_asset",
        component="youtube_clipper.dashboard",
        redact_args=["payload"],
    )
    def _store_editor_asset(self, *, payload: dict) -> dict:
        kind = payload.get("kind")
        if kind not in self.EDITOR_ASSET_POLICIES:
            raise ValidationError(
                "kind must be music or intro_image", field="kind"
            )
        if payload.get("rights_confirmed") is not True:
            raise ValidationError(
                "Confirm that you have rights to use this asset",
                field="rights_confirmed",
            )

        file_name = payload.get("file_name")
        if not isinstance(file_name, str):
            raise ValidationError("file_name is required", field="file_name")
        file_name = re.sub(r"[\x00-\x1f\x7f]+", " ", file_name).strip()
        if (
            not file_name
            or len(file_name) > 180
            or Path(file_name).name != file_name
            or "/" in file_name
            or "\\" in file_name
        ):
            raise ValidationError("Invalid asset filename", field="file_name")

        mime_type = payload.get("mime_type")
        if not isinstance(mime_type, str):
            raise ValidationError("mime_type is required", field="mime_type")
        mime_type = mime_type.split(";", 1)[0].strip().lower()
        policy = self.EDITOR_ASSET_POLICIES[kind]
        extension = Path(file_name).suffix.lower()
        if extension not in policy["extensions"]:
            raise ValidationError(
                "Unsupported file extension for this asset", field="file_name"
            )
        if mime_type not in policy["mime_types"]:
            raise ValidationError(
                "Unsupported media type for this asset", field="mime_type"
            )

        raw_data = payload.get("data_base64")
        if not isinstance(raw_data, str) or not raw_data:
            raise ValidationError("data_base64 is required", field="data_base64")
        encoded = raw_data
        if raw_data.startswith("data:"):
            header, separator, encoded = raw_data.partition(",")
            if not separator or not header.lower().endswith(";base64"):
                raise ValidationError("Invalid base64 data URL", field="data_base64")
            declared_mime = header[5:-7].strip().lower()
            if declared_mime != mime_type:
                raise ValidationError(
                    "The data URL media type does not match mime_type",
                    field="mime_type",
                )
        if len(encoded) > ((int(policy["max_bytes"]) + 2) // 3) * 4 + 4:
            raise ValidationError("Asset exceeds the size limit", field="data_base64")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            raise ValidationError("Invalid base64 asset data", field="data_base64") from None
        if not decoded:
            raise ValidationError("Asset file is empty", field="data_base64")
        if len(decoded) > int(policy["max_bytes"]):
            raise ValidationError("Asset exceeds the size limit", field="data_base64")
        if not self._asset_signature_matches(kind, extension, decoded):
            raise ValidationError(
                "File content does not match its declared media type",
                field="data_base64",
            )

        asset_dir = self._asset_dir()
        asset_id = f"asset_{uuid.uuid4().hex}{extension}"
        asset_path = asset_dir / asset_id
        digest = hashlib.sha256(decoded).hexdigest()
        metadata = {
            "asset_id": asset_id,
            "kind": kind,
            "original_file_name": file_name,
            "mime_type": mime_type,
            "size_bytes": len(decoded),
            "sha256": digest,
            "rights_confirmed": True,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.ASSET_STORAGE_LOCK:
            stored_assets = [
                candidate
                for candidate in asset_dir.iterdir()
                if self.ASSET_ID_PATTERN.fullmatch(candidate.name)
                and candidate.is_file()
            ]
            stored_bytes = sum(candidate.stat().st_size for candidate in stored_assets)
            if len(stored_assets) >= self.MAX_EDITOR_ASSET_FILES:
                raise ValidationError(
                    "Editor asset file quota reached", field="data_base64"
                )
            if stored_bytes + len(decoded) > self.MAX_EDITOR_ASSET_STORAGE_BYTES:
                raise ValidationError(
                    "Editor asset storage quota reached", field="data_base64"
                )
            with asset_path.open("xb") as asset_file:
                asset_file.write(decoded)
            try:
                metadata_path = asset_dir / f"{asset_id}.json"
                with metadata_path.open("x", encoding="utf-8") as metadata_file:
                    json.dump(metadata, metadata_file, ensure_ascii=False, sort_keys=True)
            except Exception:
                asset_path.unlink(missing_ok=True)
                raise
        return {
            "asset_id": asset_id,
            "file_name": file_name,
            "mime_type": mime_type,
            "size_bytes": len(decoded),
            "sha256": digest,
        }

    @audited(
        stage="ingest",
        action="editor.resolve_asset",
        component="youtube_clipper.dashboard",
    )
    def _resolve_editor_asset(self, asset_id: object, *, expected_kind: str) -> Path:
        field = (
            "background_music_asset_id"
            if expected_kind == "music"
            else "intro_image_asset_id"
        )
        if expected_kind not in self.EDITOR_ASSET_POLICIES:
            raise ValidationError("Unsupported editor asset kind", field=field)
        if not isinstance(asset_id, str) or not self.ASSET_ID_PATTERN.fullmatch(asset_id):
            raise ValidationError("Invalid editor asset ID", field=field)
        extension = Path(asset_id).suffix.lower()
        if extension not in self.EDITOR_ASSET_POLICIES[expected_kind]["extensions"]:
            raise ValidationError("Editor asset type mismatch", field=field)

        asset_dir = self._asset_dir()
        unresolved = asset_dir / asset_id
        if unresolved.is_symlink():
            raise ValidationError("Invalid editor asset", field=field)
        try:
            asset_path = unresolved.resolve(strict=True)
            asset_path.relative_to(asset_dir)
        except (FileNotFoundError, OSError, ValueError):
            raise ValidationError("Editor asset was not found", field=field) from None
        if not asset_path.is_file() or asset_path.name != asset_id:
            raise ValidationError("Editor asset was not found", field=field)

        metadata_path = asset_dir / f"{asset_id}.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise ValidationError("Editor asset metadata is invalid", field=field) from None
        if (
            not isinstance(metadata, dict)
            or metadata.get("asset_id") != asset_id
            or metadata.get("kind") != expected_kind
            or metadata.get("rights_confirmed") is not True
            or metadata.get("size_bytes") != asset_path.stat().st_size
        ):
            raise ValidationError("Editor asset metadata is invalid", field=field)
        digest = hashlib.sha256(asset_path.read_bytes()).hexdigest()
        if not hmac.compare_digest(str(metadata.get("sha256", "")), digest):
            raise ValidationError("Editor asset integrity check failed", field=field)
        return asset_path

    def _is_authorized(self) -> bool:
        expected = vars(self.server).get("api_token", None)
        bound_host = str(self.server.server_address[0])
        loopback = bound_host in {"127.0.0.1", "::1", "localhost"}
        if not expected:
            return loopback
        supplied = self.headers.get("Authorization", "")
        prefix = "Bearer "
        return supplied.startswith(prefix) and hmac.compare_digest(
            supplied[len(prefix):], str(expected)
        )

    def _post_origin_allowed(self) -> bool:
        if self.headers.get("Sec-Fetch-Site", "").strip().lower() == "cross-site":
            return False
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        try:
            parsed = urllib.parse.urlsplit(origin)
        except ValueError:
            return False
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return False
        request_host = self.headers.get("Host", "").strip().lower()
        if not request_host or parsed.netloc.lower() != request_host:
            return False
        if not vars(self.server).get("api_token", None):
            return parsed.hostname.lower() in {"127.0.0.1", "::1", "localhost"}
        return True

    @audited(
        stage="env",
        action="http.validate_post_context",
        component="youtube_clipper.dashboard",
    )
    def _require_safe_post_context(self) -> bool:
        content_type = self.headers.get("Content-Type", "")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            self.send_json(
                415,
                {"success": False, "error": "Content-Type must be application/json"},
                no_store=True,
            )
            return False
        if not self._post_origin_allowed():
            self.send_json(
                403,
                {"success": False, "error": "Cross-origin POST requests are not allowed"},
                no_store=True,
            )
            return False
        return True

    @audited(
        stage="env",
        action="http.authorize",
        component="youtube_clipper.dashboard",
    )
    def _require_authorization(self) -> bool:
        authorized = self._is_authorized()
        self._audit_authorized = authorized
        if authorized:
            return True
        self.send_json(401, {"success": False, "error": "Unauthorized"})
        return False

    @audited(
        stage="env",
        action="http.resolve_output_file",
        component="youtube_clipper.dashboard",
    )
    def _resolve_output_file(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser().resolve()
        candidate.relative_to(self._output_dir())
        return candidate

    def log_message(self, format, *args):
        if urllib.parse.urlsplit(self.path).path.startswith(self.STATUS_ROUTE_PREFIX):
            return
        entry = {
            "component": "youtube_clipper.dashboard",
            "request_id": vars(self).get("_audit_request_id"),
            "message": format % args,
        }
        sys.stderr.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def send_response(self, code, message=None):
        self._audit_response_status = int(code)
        return super().send_response(code, message)

    def end_headers(self):
        request_id = vars(self).get("_audit_request_id")
        if request_id:
            self.send_header("X-Request-ID", request_id)
        return super().end_headers()

    def _send_status_json(self, status_code: int, data: dict) -> None:
        payload = dict(data)
        payload.setdefault("request_id", vars(self).get("_audit_request_id"))
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def send_json(self, status_code: int, data: dict, *, no_store: bool = False):
        payload = dict(data)
        request_id = vars(self).get("_audit_request_id")
        if request_id:
            payload.setdefault("request_id", request_id)
        with action_span(
            "report",
            "http.send_json",
            component="youtube_clipper.dashboard",
            input_data={
                "http_status": status_code,
                "success": bool(payload.get("success")),
                "keys": sorted(payload.keys()),
            },
        ) as span:
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            if no_store:
                self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            span.decision = {
                "http_status": status_code,
                "success": bool(payload.get("success")),
            }
            if status_code >= 400 or payload.get("success") is False:
                span.mark_failed(
                    f"JSON response reported failure ({status_code})",
                    category="http",
                    retryable=status_code >= 500,
                )

    def _persist_legacy_analysis(
        self,
        *,
        clean_url: str,
        result: dict,
        requested_project_id: object = None,
    ) -> dict[str, Any]:
        store = self._domain_store()
        if requested_project_id is None:
            video_id_match = re.search(r"([A-Za-z0-9_-]{11})(?:[?&/#]|$)", clean_url)
            label = video_id_match.group(1) if video_id_match else "YouTube"
            project = store.create_project(
                name=f"Projeto {label}",
                source_uri=clean_url,
                source_kind="youtube",
            )
        else:
            project = store.get_project(str(requested_project_id))
            source = store.get_primary_source(project["project_id"])
            if source["kind"] != "youtube" or source["uri"] != clean_url:
                raise DomainConflictError(
                    "The requested project belongs to a different source"
                )
        source = store.get_primary_source(project["project_id"])
        analysis = store.create_analysis(project_id=project["project_id"])
        if result.get("success") is False:
            store.fail_analysis(analysis["analysis_id"], result)
            clips = []
        else:
            clips = store.finish_analysis(
                analysis_id=analysis["analysis_id"],
                result=result,
            )
        return {
            "project_id": project["project_id"],
            "source_id": source["source_id"],
            "analysis_id": analysis["analysis_id"],
            "clips": clips,
        }

    def _send_domain_asset(self, asset_id: str) -> None:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        raw_version = query.get("v", [None])[0]
        if raw_version is None or not str(raw_version).isdigit():
            raise DomainValidationError("A numeric asset version is required")
        asset, path = self._domain_store().resolve_asset_file(
            asset_id, version=int(raw_version)
        )
        size = path.stat().st_size
        start = 0
        end = size - 1
        status = 200
        raw_range = self.headers.get("Range")
        if raw_range:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", raw_range.strip())
            if not match or (not match.group(1) and not match.group(2)):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if match.group(1):
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else size - 1
            else:
                suffix_length = int(match.group(2))
                start = max(0, size - suffix_length)
                end = size - 1
            if start >= size or end < start:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            end = min(end, size - 1)
            status = 206

        content_length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", asset["mime_type"])
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.send_header("ETag", chr(34) + asset["sha256"] + chr(34))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as stream:
            stream.seek(start)
            remaining = content_length
            while remaining:
                chunk = stream.read(min(65536, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _handle_api_v1_get(self, route_path: str) -> None:
        store = self._domain_store()
        try:
            match = self.DOMAIN_ASSET_ROUTE.fullmatch(route_path)
            if match:
                self._send_domain_asset(match.group(1))
                return
            if route_path == "/api/v1/projects":
                self.send_json(
                    200,
                    {"success": True, "projects": store.list_projects()},
                    no_store=True,
                )
                return
            match = self.PROJECT_ID_ROUTE.fullmatch(route_path)
            if match:
                self.send_json(
                    200,
                    {"success": True, "project": store.get_project(match.group(1))},
                    no_store=True,
                )
                return
            match = self.PROJECT_CLIPS_ROUTE.fullmatch(route_path)
            if match:
                self.send_json(
                    200,
                    {
                        "success": True,
                        "project_id": match.group(1),
                        "clips": store.list_clips(match.group(1)),
                    },
                    no_store=True,
                )
                return
            match = self.CLIP_ID_ROUTE.fullmatch(route_path)
            if match:
                self.send_json(
                    200,
                    {"success": True, "clip": store.get_clip(match.group(1))},
                    no_store=True,
                )
                return
            match = self.JOB_ID_ROUTE.fullmatch(route_path)
            if match:
                self.send_json(
                    200,
                    {"success": True, "job": store.get_job(match.group(1))},
                    no_store=True,
                )
                return
            self.send_json(
                404,
                {"success": False, "error": "API v1 route not found"},
                no_store=True,
            )
        except (DomainNotFoundError, DomainConflictError, DomainValidationError) as exc:
            self._send_domain_error(exc)
        except Exception:
            self.send_json(
                500,
                {"success": False, "error": "Persistent API operation failed"},
                no_store=True,
            )

    def _create_preview_job(self, clip_id: str) -> dict[str, Any]:
        store = self._domain_store()
        clip = store.get_clip(clip_id)
        source = store.get_source(clip["source_id"])
        job = store.create_job(
            project_id=clip["project_id"],
            clip_id=clip_id,
            kind="preview",
            state="running",
        )
        run_id = self._new_child_run("preview-" + job["job_id"])
        try:
            clip = store.update_clip(clip_id, {"status": "previewing"})
            generated = generate_clip_preview(
                input_source=source["uri"],
                start_ms=clip["start_ms"],
                end_ms=clip["end_ms"],
                edit_plan=clip["edit_plan"],
                clip_id=clip_id,
                run_id=run_id,
                request_id=self._audit_request_id,
            )
            preview = store.add_asset(
                clip_id=clip_id,
                kind="preview",
                source_path=generated["preview_path"],
                mime_type="video/mp4",
                duration_ms=generated["duration_ms"],
                width=generated["width"],
                height=generated["height"],
            )
            poster = store.add_asset(
                clip_id=clip_id,
                kind="poster",
                source_path=generated["poster_path"],
                mime_type="image/jpeg",
                width=generated["width"],
                height=generated["height"],
            )
            completed_job = store.update_job(
                job["job_id"], state="completed", run_id=run_id
            )
            completed_clip = store.update_clip(clip_id, {"status": "ready"})
            return {
                "job": completed_job,
                "clip": completed_clip,
                "preview": preview,
                "poster": poster,
            }
        except Exception as exc:
            store.update_job(
                job["job_id"],
                state="failed",
                run_id=run_id,
                error=str(exc)[:500],
            )
            try:
                store.update_clip(clip_id, {"status": "failed"})
            except (DomainConflictError, DomainValidationError):
                pass
            raise

    def _handle_api_v1_post(self, route_path: str, payload: dict) -> bool:
        store = self._domain_store()
        try:
            match = self.CLIP_PREVIEW_ROUTE.fullmatch(route_path)
            if match:
                result = self._create_preview_job(match.group(1))
                self.send_json(201, {"success": True, **result}, no_store=True)
                return True
            if route_path == "/api/v1/projects":
                source = payload.get("source")
                if not isinstance(source, dict):
                    raise DomainValidationError("Project source must be an object")
                project = store.create_project(
                    name=payload.get("name", ""),
                    source_uri=source.get("uri", ""),
                    source_kind=source.get("kind", ""),
                )
                self.send_json(
                    201,
                    {"success": True, "project": project},
                    no_store=True,
                )
                return True

            match = self.PROJECT_ANALYSIS_ROUTE.fullmatch(route_path)
            if match:
                project_id = match.group(1)
                project = store.get_project(project_id)
                source = store.get_primary_source(project_id)
                analysis = store.create_analysis(project_id=project_id)
                job = store.create_job(
                    project_id=project_id,
                    analysis_id=analysis["analysis_id"],
                    kind="analysis",
                    state="running",
                )
                try:
                    result = extract_transcript_and_analyze(
                        source["uri"],
                        cookies_file=payload.get("cookies"),
                    )
                    if result.get("success") is False:
                        store.fail_analysis(analysis["analysis_id"], result)
                        store.update_job(
                            job["job_id"],
                            state="failed",
                            error=str(result.get("error") or "Analysis failed"),
                        )
                        self.send_json(
                            422,
                            {
                                "success": False,
                                "project_id": project["project_id"],
                                "analysis_id": analysis["analysis_id"],
                                "job_id": job["job_id"],
                                "error": result.get("error") or "Analysis failed",
                            },
                            no_store=True,
                        )
                        return True
                    clips = store.finish_analysis(
                        analysis_id=analysis["analysis_id"],
                        result=result,
                    )
                    completed_job = store.update_job(
                        job["job_id"],
                        state="completed",
                    )
                    self.send_json(
                        201,
                        {
                            "success": True,
                            "project_id": project["project_id"],
                            "source_id": source["source_id"],
                            "analysis_id": analysis["analysis_id"],
                            "job": completed_job,
                            "clips": clips,
                        },
                        no_store=True,
                    )
                    return True
                except Exception as exc:
                    store.fail_analysis(
                        analysis["analysis_id"],
                        {"success": False, "error": str(exc)},
                    )
                    store.update_job(
                        job["job_id"],
                        state="failed",
                        error=str(exc)[:500],
                    )
                    raise

            return False
        except (DomainNotFoundError, DomainConflictError, DomainValidationError) as exc:
            self._send_domain_error(exc)
            return True
        except Exception:
            self.send_json(
                500,
                {"success": False, "error": "Persistent API operation failed"},
                no_store=True,
            )
            return True

    def _handle_api_v1_patch(self, route_path: str, payload: dict) -> bool:
        match = self.CLIP_ID_ROUTE.fullmatch(route_path)
        if not match:
            return False
        try:
            clip = self._domain_store().update_clip(match.group(1), payload)
            self.send_json(
                200,
                {"success": True, "clip": clip},
                no_store=True,
            )
        except (DomainNotFoundError, DomainConflictError, DomainValidationError) as exc:
            self._send_domain_error(exc)
        except Exception:
            self.send_json(
                500,
                {"success": False, "error": "Persistent API operation failed"},
                no_store=True,
            )
        return True

    @observed_http_request
    def do_GET(self):
        route_path = urllib.parse.urlsplit(self.path).path
        if route_path.startswith(self.STATUS_ROUTE_PREFIX):
            self._audit_authorized = self._is_authorized()
            if not self._audit_authorized:
                self._send_status_json(
                    401, {"success": False, "error": "Unauthorized"}
                )
                return
            raw_request_id = urllib.parse.unquote(
                route_path[len(self.STATUS_ROUTE_PREFIX):]
            )
            if not self.REQUEST_ID_PATTERN.fullmatch(raw_request_id):
                self._send_status_json(
                    400, {"success": False, "error": "Invalid request ID"}
                )
                return
            status_payload = self._request_status_payload(raw_request_id)
            if status_payload is None:
                status_payload = {
                    "success": True,
                    "request_id": raw_request_id,
                    "state": "pending",
                    "completed": False,
                    "run_ids": [],
                    "events": [],
                    "drive_upload": None,
                }
            self._send_status_json(200, status_payload)
            return

        if not self._require_authorization():
            return
        if route_path.startswith(self.API_V1_PREFIX):
            self._handle_api_v1_get(route_path)
            return
        if route_path in self.GET_ROUTES:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
        elif route_path in self.TECHNICAL_GET_ROUTES:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(TECHNICAL_HTML_TEMPLATE.encode("utf-8"))
        elif route_path.startswith("/api/download/"):
            raw_param = urllib.parse.unquote(route_path[len("/api/download/"):])

            if ".." in raw_param or raw_param.startswith("/") or "\\" in raw_param:
                self.send_json(400, {"success": False, "error": "Invalid filename or path traversal detected"})
                return

            filename = os.path.basename(raw_param)
            if not filename or filename != raw_param or ".." in filename or "/" in filename or "\\" in filename:
                self.send_json(400, {"success": False, "error": "Invalid filename"})
                return

            base_dir = self._output_dir()
            candidate = (base_dir / filename).resolve()
            target_path = None
            try:
                candidate.relative_to(base_dir)
                if candidate.exists() and candidate.is_file():
                    target_path = candidate
            except ValueError:
                target_path = None

            if target_path and target_path.exists():
                file_size = target_path.stat().st_size
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(file_size))
                self.end_headers()
                with open(target_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_json(404, {"success": False, "error": "File not found"})
        elif route_path in self.POST_ROUTES:
            self.send_error(405, "Method Not Allowed")
        else:
            self.send_error(404, "File Not Found")

    @observed_http_request
    def do_POST(self):
        if not self._require_authorization():
            return
        if not self._require_safe_post_context():
            return
        route_path = urllib.parse.urlsplit(self.path).path
        if (
            route_path in self.GET_ROUTES
            or route_path in self.TECHNICAL_GET_ROUTES
            or route_path.startswith("/api/download/")
            or route_path.startswith(self.STATUS_ROUTE_PREFIX)
        ):
            self.send_error(405, "Method Not Allowed")
            return
        elif route_path not in self.POST_ROUTES and not route_path.startswith(self.API_V1_PREFIX):
            self.send_error(404, "Endpoint not found")
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self.send_json(400, {"success": False, "error": "Invalid Content-Length"})
            return
        if content_length < 0:
            self.send_json(400, {"success": False, "error": "Invalid Content-Length"})
            return
        if content_length > self.MAX_REQUEST_BODY_BYTES:
            self.send_json(413, {"success": False, "error": "Request body is too large"})
            return
        post_data = self.rfile.read(content_length)

        if not post_data:
            self.send_json(400, {"success": False, "error": "Missing request body"})
            return

        try:
            payload = json.loads(post_data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, AttributeError, TypeError):
            self.send_json(400, {"success": False, "error": "Invalid JSON format"})
            return

        if not isinstance(payload, dict):
            self.send_json(400, {"success": False, "error": "JSON payload must be an object"})
            return

        if route_path.startswith(self.API_V1_PREFIX):
            if self._handle_api_v1_post(route_path, payload):
                return
            self.send_json(
                404,
                {"success": False, "error": "API v1 route not found"},
                no_store=True,
            )
            return

        if self.path == "/api/editor-chat":
            try:
                result = request_gemini_edit(
                    message=payload.get("message"),
                    clip=payload.get("clip", {}),
                    config=payload.get("config", {}),
                    history=payload.get("history", []),
                )
                self.send_json(200, {"success": True, **result}, no_store=True)
            except GeminiConfigurationError:
                self.send_json(
                    503,
                    {
                        "success": False,
                        "error": "Editor Gemini não configurado. Defina GEMINI_API_KEY no servidor.",
                    },
                    no_store=True,
                )
            except GeminiInputError as exc:
                self.send_json(
                    400, {"success": False, "error": str(exc)}, no_store=True
                )
            except GeminiEditorError as exc:
                self.send_json(
                    502, {"success": False, "error": str(exc)}, no_store=True
                )

        elif self.path == "/api/editor-assets":
            try:
                asset = self._store_editor_asset(payload=payload)
                self.send_json(201, {"success": True, **asset}, no_store=True)
            except ValidationError as exc:
                self.send_json(
                    400,
                    {"success": False, "error": str(exc), "field": exc.field},
                    no_store=True,
                )
            except OSError:
                self.send_json(
                    500,
                    {
                        "success": False,
                        "error": "Não foi possível armazenar o anexo.",
                    },
                    no_store=True,
                )

        elif self.path == "/api/cortes/run":
            try:
                settings = validate_technical_payload(payload)
                pipeline_run_id = self._new_child_run("cortes")
                pipeline_result = run_full_pipeline(
                    input_source=settings["input_path"],
                    run_id=pipeline_run_id,
                    request_id=self._audit_request_id,
                    whisper_model=settings["whisper_model"],
                    device=settings["device"],
                    language=settings["language"],
                    scene_threshold=settings["scene_threshold"],
                    min_scene_len=settings["min_scene_len"],
                    vertical_mode=settings["vertical_mode"],
                    blur_sigma=settings["blur_sigma"],
                    subtitle_font_name=settings["subtitle_font_name"],
                    subtitle_font_size=settings["subtitle_font_size"],
                    subtitle_margin_v=settings["subtitle_margin_v"],
                    analytical_overlay=settings["analytical_overlay"],
                    overlay_text=settings["overlay_text"],
                    narration_path=settings["narration_path"],
                    template_variant=settings["template_variant"],
                    require_editorial_transformation=settings[
                        "require_editorial_transformation"
                    ],
                )

                returned_run_id = str(
                    pipeline_result.get("run_id") or pipeline_run_id
                )
                run_dir = (Path.cwd() / "runs" / returned_run_id).resolve()
                with action_span(
                    "verify",
                    "pipeline.verify",
                    component="youtube_clipper.dashboard",
                    input_data={"run_id": returned_run_id},
                ) as verify_span:
                    measured = verify_run(run_dir)
                    verification = {
                        "overall_passed": bool(measured.get("overall_passed")),
                        "total_checks": int(measured.get("total_checks", 0)),
                        "passed_checks": int(measured.get("passed_checks", 0)),
                        "failed_checks": int(measured.get("failed_checks", 0)),
                    }
                    verify_span.decision = dict(verification)

                render_path_raw = pipeline_result.get("render_path")
                if not isinstance(render_path_raw, (str, os.PathLike)):
                    raise RuntimeError("Technical pipeline did not return render_path")
                render_path = Path(render_path_raw).resolve()
                if (
                    not render_path.exists()
                    or not render_path.is_file()
                    or render_path.suffix.lower() != ".mp4"
                ):
                    raise RuntimeError(
                        "Technical pipeline render_path is not a readable MP4 file"
                    )

                output_dir = self._output_dir()
                output_dir.mkdir(parents=True, exist_ok=True)
                request_token = re.sub(
                    r"[^A-Za-z0-9_-]", "", self._audit_request_id or ""
                )[-12:] or uuid.uuid4().hex[:12]
                generated_at = datetime.now(timezone.utc)
                filename = (
                    f"cortes_{settings['phase']}_"
                    f"{generated_at.strftime('%Y%m%d_%H%M%S_%f')}_"
                    f"{request_token}_{uuid.uuid4().hex[:8]}.mp4"
                )
                output_path = output_dir / filename
                shutil.copy2(render_path, output_path)
                download_url = f"/api/download/{urllib.parse.quote(filename)}"

                applied_settings = {
                    "phase": settings["phase"],
                    "input_path": str(settings["input_path"]),
                    "whisper_model": settings["whisper_model"],
                    "device": settings["device"],
                    "language": settings["language"],
                    "scene_threshold": settings["scene_threshold"],
                    "min_scene_len": settings["min_scene_len"],
                    "vertical_mode": settings["vertical_mode"],
                    "blur_sigma": (
                        settings["blur_sigma"]
                        if settings["vertical_mode"] != "crop_center"
                        else None
                    ),
                    "subtitles": {
                        "font_name": settings["subtitle_font_name"],
                        "font_size": settings["subtitle_font_size"],
                        "margin_v": settings["subtitle_margin_v"],
                        "burned_in": True,
                    },
                    "editorial": {
                        "required": settings["require_editorial_transformation"],
                        "analytical_overlay": settings["analytical_overlay"],
                        "overlay_text": settings["overlay_text"],
                        "narration_path": (
                            str(settings["narration_path"])
                            if settings["narration_path"] is not None
                            else None
                        ),
                        "template_variant": settings["template_variant"],
                    },
                }
                report_path = pipeline_result.get("report_path")
                subtitles_path = pipeline_result.get("subtitles_path")
                render_receipt = {
                    "request_id": self._audit_request_id,
                    "generated_at": generated_at.isoformat(),
                    "status": "measured",
                    "status_label": "Medição pós-run; não é declaração de fase",
                    "run_id": returned_run_id,
                    "file": {
                        "name": filename,
                        "size_bytes": output_path.stat().st_size,
                        "download_url": download_url,
                    },
                    "subtitles": {
                        "path": str(subtitles_path) if subtitles_path else None,
                        "label": "Arquivo ASS gerado e aplicado no render",
                    },
                    "report_snapshot": {
                        "path": str(report_path) if report_path else None,
                        "label": "Snapshot interno não verificado",
                    },
                    "verification": verification,
                    "applied_settings": applied_settings,
                }
                self.send_json(
                    200,
                    {
                        "success": True,
                        "overall_status": "measured",
                        "pipeline_run_id": returned_run_id,
                        "output_path": str(output_path),
                        "download_url": download_url,
                        "verification": verification,
                        "applied_settings": applied_settings,
                        "render_receipt": render_receipt,
                    },
                    no_store=True,
                )
            except ValidationError as e:
                self.send_json(
                    400,
                    {
                        "success": False,
                        "error": str(e),
                        "field": e.field,
                    },
                    no_store=True,
                )
            except FileNotFoundError as e:
                self.send_json(
                    404, {"success": False, "error": str(e)}, no_store=True
                )
            except Exception as e:
                self.send_json(
                    500, {"success": False, "error": str(e)}, no_store=True
                )

        elif self.path == "/api/analyze":
            url = payload.get("url", "")
            cookies = payload.get("cookies", None)
            if not url or not isinstance(url, str) or not url.strip():
                self.send_json(400, {"success": False, "error": "URL parameter required"})
                return
            try:
                clean_url = validate_input_source(url)
                if not is_youtube_url(clean_url):
                    raise ValidationError("Dashboard analysis accepts only YouTube URLs")
                analysis_result = extract_transcript_and_analyze(
                    clean_url, cookies_file=cookies
                )
                domain_result = self._persist_legacy_analysis(
                    clean_url=clean_url,
                    result=analysis_result,
                    requested_project_id=payload.get("project_id"),
                )
                stored_by_rank = {
                    int(clip["rank"]): clip
                    for clip in domain_result["clips"]
                }
                for candidate in analysis_result.get("clips", []):
                    stored = stored_by_rank.get(int(candidate.get("rank", 0)))
                    if stored:
                        candidate["clip_id"] = stored["clip_id"]
                        candidate["project_id"] = stored["project_id"]
                        candidate["analysis_id"] = stored["analysis_id"]
                        candidate["plan_version"] = stored["plan_version"]
                        candidate["preview_status"] = "not_created"
                        candidate["render_status"] = "not_started"
                analysis_result.update(
                    {
                        "project_id": domain_result["project_id"],
                        "source_id": domain_result["source_id"],
                        "analysis_id": domain_result["analysis_id"],
                    }
                )
                if isinstance(analysis_result, dict):
                    clips = analysis_result.get("clips", [])
                    all_transcripts = " ".join(c.get("transcript", "") for c in clips)
                    all_tags = list({tag for c in clips for tag in c.get("hashtags", [])})
                    analysis_result.setdefault("transcript", all_transcripts)
                    analysis_result.setdefault("hashtags", all_tags)
                if analysis_result.get("success") is False:
                    self.send_json(422, analysis_result)
                else:
                    self.send_json(200, analysis_result)
            except (DomainNotFoundError, DomainConflictError, DomainValidationError) as e:
                self._send_domain_error(e)
            except (ValidationError, ValueError) as e:
                self.send_json(400, {"success": False, "error": str(e)})
            except FileNotFoundError as e:
                self.send_json(404, {"success": False, "error": str(e)})
            except ClipperError as e:
                if isinstance(e, (ValidationError, DownloadError)):
                    self.send_json(400, {"success": False, "error": str(e)})
                else:
                    self.send_json(500, {"success": False, "error": str(e)})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})

        elif self.path == "/api/generate-clip":
            url = payload.get("url", "")
            if not url or not isinstance(url, str) or not url.strip():
                self.send_json(400, {"success": False, "error": "URL parameter required"})
                return

            if payload.get("confirmed_configuration") is not True:
                self.send_json(400, {
                    "success": False,
                    "error": "Review and explicitly confirm the clip configuration before rendering",
                    "field": "confirmed_configuration",
                })
                return

            start = payload.get("start", "0")
            end = payload.get("end", "10")
            fmt_mode = payload.get("format", payload.get("mode", "blur_background"))
            upload_gdrive = payload.get("gdrive", False)
            include_audio = payload.get("include_audio", True)
            folder_id = payload.get("folder_id", None)
            cookies = payload.get("cookies", None)
            crop_focus = payload.get("crop_focus", "center")
            overlay_position = payload.get("overlay_position", "top")
            overlay_text = payload.get("overlay_text", "")
            blur_sigma_raw = payload.get("blur_sigma", 12.0)
            music_asset_id = payload.get("background_music_asset_id") or None
            music_volume_raw = payload.get("background_music_volume", 0.2)
            intro_asset_id = payload.get("intro_image_asset_id") or None
            intro_duration_raw = payload.get("intro_duration", 0.0)
            background_music_path = None
            intro_image_path = None

            valid_modes = {"blur_background", "split_blur", "crop_center"}
            if fmt_mode not in valid_modes:
                self.send_json(400, {"success": False, "error": f"Invalid format mode: {fmt_mode}. Must be one of {sorted(list(valid_modes))}"})
                return
            if not isinstance(upload_gdrive, bool):
                self.send_json(400, {"success": False, "error": "gdrive must be a boolean"})
                return
            if not isinstance(include_audio, bool):
                self.send_json(400, {"success": False, "error": "include_audio must be a boolean"})
                return
            if crop_focus not in {"left", "center", "right"}:
                self.send_json(400, {"success": False, "error": "crop_focus must be left, center, or right"})
                return
            if overlay_position not in {"top", "bottom"}:
                self.send_json(400, {"success": False, "error": "overlay_position must be top or bottom"})
                return
            if not isinstance(overlay_text, str):
                self.send_json(400, {"success": False, "error": "overlay_text must be text"})
                return
            overlay_text = re.sub(r"[\x00-\x1f\x7f]+", " ", overlay_text).strip()
            if not overlay_text:
                self.send_json(400, {
                    "success": False,
                    "error": "An editorial overlay text is required for this render",
                    "field": "overlay_text",
                })
                return
            if len(overlay_text) > 90:
                self.send_json(400, {"success": False, "error": "overlay_text must contain at most 90 characters"})
                return
            if isinstance(blur_sigma_raw, bool):
                self.send_json(400, {"success": False, "error": "blur_sigma must be a number between 0 and 50"})
                return

            try:
                blur_sigma = float(blur_sigma_raw)
                if not 0.0 <= blur_sigma <= 50.0:
                    raise ValueError("blur_sigma must be between 0 and 50")
                if isinstance(music_volume_raw, bool):
                    raise ValidationError(
                        "background_music_volume must be between 0 and 1",
                        field="background_music_volume",
                    )
                music_volume = float(music_volume_raw)
                if not math.isfinite(music_volume) or not 0.0 <= music_volume <= 1.0:
                    raise ValidationError(
                        "background_music_volume must be between 0 and 1",
                        field="background_music_volume",
                    )
                if isinstance(intro_duration_raw, bool):
                    raise ValidationError(
                        "intro_duration must be between 0 and 5", field="intro_duration"
                    )
                intro_duration = float(intro_duration_raw)
                if not math.isfinite(intro_duration) or not 0.0 <= intro_duration <= 5.0:
                    raise ValidationError(
                        "intro_duration must be between 0 and 5", field="intro_duration"
                    )
                if music_asset_id and not include_audio:
                    raise ValidationError(
                        "Enable audio before adding a soundtrack", field="include_audio"
                    )
                if music_asset_id:
                    background_music_path = self._resolve_editor_asset(
                        music_asset_id, expected_kind="music"
                    )
                if intro_asset_id:
                    if intro_duration < 0.5:
                        raise ValidationError(
                            "intro_duration must be between 0.5 and 5",
                            field="intro_duration",
                        )
                    intro_image_path = self._resolve_editor_asset(
                        intro_asset_id, expected_kind="intro_image"
                    )
                elif intro_duration != 0.0:
                    raise ValidationError(
                        "intro_duration requires an intro image", field="intro_image_asset_id"
                    )
                start_seconds, end_seconds = validate_time_range(start, end, None)
                duration_seconds = end_seconds - start_seconds
                final_duration_seconds = duration_seconds + intro_duration
                if final_duration_seconds > 59.9:
                    raise ValidationError("The clip plus intro must be at most 59.9 seconds", field="time_range")

                clean_url = validate_input_source(url)
                if not is_youtube_url(clean_url):
                    raise ValidationError("Dashboard generation accepts only YouTube URLs")

                store = None
                persisted_clip = None
                requested_clip_id = payload.get("clip_id")
                if requested_clip_id:
                    store = self._domain_store()
                    persisted_clip = store.get_clip(str(requested_clip_id))
                    requested_project_id = payload.get("project_id")
                    if (
                        requested_project_id
                        and persisted_clip["project_id"] != requested_project_id
                    ):
                        raise DomainConflictError("Clip belongs to a different project")
                    source = store.get_source(persisted_clip["source_id"])
                    if source["uri"] != clean_url:
                        raise DomainConflictError("Clip belongs to a different source")
                    expected_start = int(round(start_seconds * 1000))
                    expected_end = int(round(end_seconds * 1000))
                    if (
                        persisted_clip["start_ms"] != expected_start
                        or persisted_clip["end_ms"] != expected_end
                    ):
                        raise DomainConflictError(
                            "Render interval differs from the persisted edit plan"
                        )
                    persisted_clip = store.update_clip(
                        persisted_clip["clip_id"],
                        {
                            "layout": {
                                "mode": fmt_mode,
                                "crop_focus": crop_focus,
                                "blur_sigma": blur_sigma,
                                "overlay_position": overlay_position,
                            },
                            "audio": {"include_source": include_audio},
                            "editorial": {
                                "overlay_enabled": True,
                                "overlay_text": overlay_text,
                                "template_variant": "variant_default",
                            },
                        },
                    )
                    render_plan = persisted_clip["edit_plan"]
                    render_layout = render_plan["layout"]
                    fmt_mode = render_layout.get("mode", "blur_background")
                    crop_focus = render_layout.get("crop_focus", "center")
                    blur_sigma = float(render_layout.get("blur_sigma", 12.0))
                    overlay_position = render_layout.get("overlay_position", "top")
                    include_audio = bool(
                        (render_plan.get("audio") or {}).get("include_source", True)
                    )
                    overlay_text = (
                        (render_plan.get("editorial") or {}).get("overlay_text")
                        or overlay_text
                    )

                output_dir = self._output_dir()
                output_dir.mkdir(parents=True, exist_ok=True)
                request_token = re.sub(r"[^A-Za-z0-9_-]", "", self._audit_request_id or "")[-12:]
                if not request_token:
                    request_token = uuid.uuid4().hex[:12]
                output_target = output_dir / (
                    f"clip_{int(start_seconds * 1000)}_{int(end_seconds * 1000)}_{request_token}.mp4"
                )
                pipeline_run_id = self._new_child_run("pipeline")
                output_path = run_pipeline(
                    input_source=clean_url,
                    start=start_seconds,
                    end=end_seconds,
                    output=str(output_target),
                    vertical=True,
                    mode=fmt_mode,
                    blur_sigma=blur_sigma,
                    crop_focus=crop_focus,
                    include_audio=include_audio,
                    background_music_path=background_music_path,
                    background_music_volume=music_volume,
                    intro_image_path=intro_image_path,
                    intro_duration=intro_duration,
                    overlay_text=overlay_text,
                    overlay_position=overlay_position,
                    cookies=cookies,
                    run_id=pipeline_run_id,
                    request_id=self._audit_request_id,
                    clip_id=(
                        persisted_clip["clip_id"]
                        if persisted_clip is not None
                        else None
                    ),
                )

                try:
                    probed = probe_video_metadata(Path(output_path))
                    media_probe = {
                        "verified": bool(
                            probed.get("duration", 0) > 0
                            and probed.get("width", 0) > 0
                            and probed.get("height", 0) > 0
                            and probed.get("video_codec") not in {None, "", "unknown"}
                        ),
                        "duration_seconds": probed.get("duration"),
                        "width": probed.get("width"),
                        "height": probed.get("height"),
                        "fps": probed.get("fps"),
                        "video_codec": probed.get("video_codec"),
                        "audio_codec": probed.get("audio_codec"),
                        "audio_channels": probed.get("audio_channels"),
                        "file_size_bytes": probed.get("file_size"),
                        "sha256": probed.get("sha256"),
                        "error": None,
                    }
                except Exception as probe_error:
                    media_probe = {
                        "verified": False,
                        "duration_seconds": None,
                        "width": None,
                        "height": None,
                        "fps": None,
                        "video_codec": None,
                        "audio_codec": None,
                        "audio_channels": None,
                        "file_size_bytes": os.path.getsize(output_path),
                        "sha256": None,
                        "error": str(probe_error)[:240],
                    }

                domain_render = None
                if persisted_clip is not None and store is not None:
                    render_asset = store.add_asset(
                        clip_id=persisted_clip["clip_id"],
                        kind="render",
                        source_path=output_path,
                        mime_type="video/mp4",
                        duration_ms=(
                            int(round(float(media_probe["duration_seconds"]) * 1000))
                            if media_probe.get("duration_seconds") is not None
                            else None
                        ),
                        width=media_probe.get("width"),
                        height=media_probe.get("height"),
                    )
                    current_status = persisted_clip["status"]
                    if current_status in {"proposed", "previewing", "rejected"}:
                        persisted_clip = store.update_clip(
                            persisted_clip["clip_id"], {"status": "ready"}
                        )
                        current_status = persisted_clip["status"]
                    if current_status == "ready":
                        persisted_clip = store.update_clip(
                            persisted_clip["clip_id"], {"status": "approved"}
                        )
                        current_status = persisted_clip["status"]
                    if current_status in {
                        "approved", "failed", "rendered", "exported"
                    }:
                        persisted_clip = store.update_clip(
                            persisted_clip["clip_id"], {"status": "rendering"}
                        )
                        current_status = persisted_clip["status"]
                    if current_status == "rendering":
                        persisted_clip = store.update_clip(
                            persisted_clip["clip_id"], {"status": "rendered"}
                        )
                    domain_render = store.create_render(
                        clip_id=persisted_clip["clip_id"],
                        asset_id=render_asset["asset_id"],
                        status="rendered",
                    )
                    domain_render["asset"] = render_asset

                gdrive_link = None
                gdrive_result = {
                    "requested": upload_gdrive,
                    "success": None,
                    "error": None,
                    "web_view_link": None,
                    "permission_configured": None,
                }
                if upload_gdrive:
                    gdrive_run_id = self._new_child_run("gdrive")
                    res = upload_clip_to_gdrive(
                        output_path,
                        folder_id=folder_id,
                        run_id=gdrive_run_id,
                        request_id=self._audit_request_id,
                    )
                    gdrive_result["success"] = bool(res.get("success"))
                    gdrive_result["error"] = res.get("error")
                    gdrive_result["permission_configured"] = res.get("permission_configured")
                    progress_result = res.get("upload_progress") or {}
                    gdrive_result["progress_percent"] = progress_result.get("progress_percent")
                    gdrive_result["uploaded_bytes"] = progress_result.get("uploaded_bytes")
                    gdrive_result["total_bytes"] = progress_result.get("total_bytes")
                    gdrive_result["chunk_number"] = progress_result.get("chunk_number")
                    if res.get("success"):
                        gdrive_link = res.get("web_view_link")
                        gdrive_result["web_view_link"] = gdrive_link

                filename = os.path.basename(output_path)
                download_url = f"/api/download/{filename}"
                partial_success = upload_gdrive and (
                    not gdrive_result["success"]
                    or gdrive_result["permission_configured"] is False
                )
                overall_status = "partial_success" if partial_success else "success"
                format_labels = {
                    "blur_background": "Fundo desfocado",
                    "split_blur": "Fundo desfocado",
                    "crop_center": "Crop vertical",
                }
                applied_settings = {
                    "start_seconds": start_seconds,
                    "end_seconds": end_seconds,
                    "duration_seconds": round(duration_seconds, 3),
                    "final_duration_seconds": round(final_duration_seconds, 3),
                    "format": fmt_mode,
                    "format_label": format_labels[fmt_mode],
                    "crop_focus": crop_focus,
                    "blur_sigma": blur_sigma if fmt_mode in {"blur_background", "split_blur"} else None,
                    "audio_included": include_audio,
                    "background_music": {
                        "included": background_music_path is not None,
                        "asset_id": music_asset_id,
                        "volume": music_volume if background_music_path is not None else None,
                    },
                    "intro_image": {
                        "included": intro_image_path is not None,
                        "asset_id": intro_asset_id,
                        "duration_seconds": intro_duration if intro_image_path is not None else 0.0,
                    },
                    "editorial_overlay": {
                        "included": True,
                        "text": overlay_text,
                        "position": overlay_position,
                    },
                    "captions_included": False,
                    "narration_included": False,
                    "hashtags_burned_in": False,
                    "resolution": {"width": 1080, "height": 1920, "aspect_ratio": "9:16"},
                    "destination": {
                        "local": True,
                        "gdrive_requested": upload_gdrive,
                        "gdrive_completed": gdrive_result["success"] is True,
                    },
                }
                included = ["Vídeo no intervalo selecionado", "Selo editorial sobreposto"]
                if include_audio:
                    included.append("Áudio original em AAC")
                if background_music_path is not None:
                    included.append("Trilha sonora mixada")
                if intro_image_path is not None:
                    included.append("Imagem inicial")
                not_included = ["Legendas queimadas", "Narração", "Hashtags visuais"]
                if not include_audio:
                    not_included.insert(0, "Áudio original")
                if background_music_path is None:
                    not_included.append("Trilha sonora")
                if intro_image_path is None:
                    not_included.append("Imagem inicial")
                render_receipt = {
                    "request_id": self._audit_request_id,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "status": overall_status,
                    "file": {
                        "name": filename,
                        "size_bytes": media_probe.get("file_size_bytes") or os.path.getsize(output_path),
                        "download_url": download_url,
                        "video_codec": media_probe.get("video_codec") or "h264",
                        "audio_codec": media_probe.get("audio_codec") if include_audio else None,
                        "sha256": media_probe.get("sha256"),
                    },
                    "measured_media": media_probe,
                    "included": included,
                    "not_included": not_included,
                    "applied_settings": applied_settings,
                }
                resp_data = {
                    "success": True,
                    "project_id": domain_render.get("project_id") if domain_render else None,
                    "clip_id": domain_render.get("clip_id") if domain_render else None,
                    "render_id": domain_render.get("render_id") if domain_render else None,
                    "asset": domain_render.get("asset") if domain_render else None,
                    "overall_status": overall_status,
                    "output_path": output_path,
                    "clip_path": output_path,
                    "download_url": download_url,
                    "gdrive_link": gdrive_link,
                    "upload": gdrive_result,
                    "applied_settings": applied_settings,
                    "render_receipt": render_receipt,
                }
                self.send_json(200, resp_data)
            except (DomainNotFoundError, DomainConflictError, DomainValidationError) as e:
                self._send_domain_error(e)
            except (ValidationError, ValueError) as e:
                self.send_json(400, {"success": False, "error": str(e)})
            except FileNotFoundError as e:
                self.send_json(404, {"success": False, "error": str(e)})
            except ClipperError as e:
                if isinstance(e, (ValidationError, DownloadError)):
                    self.send_json(400, {"success": False, "error": str(e)})
                else:
                    self.send_json(500, {"success": False, "error": str(e)})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})

        elif self.path == "/api/gdrive-upload":
            file_path = payload.get("file_path", "")
            folder_id = payload.get("folder_id", None)
            if not file_path or not isinstance(file_path, str) or not file_path.strip():
                self.send_json(400, {"success": False, "error": "file_path parameter required"})
                return

            try:
                allowed_file = self._resolve_output_file(file_path)
            except (ValueError, OSError):
                self.send_json(
                    403,
                    {
                        "status": "error",
                        "success": False,
                        "error": "file_path must be inside the dashboard output directory",
                    },
                )
                return

            if not allowed_file.exists() or not allowed_file.is_file():
                self.send_json(404, {"status": "error", "success": False, "error": f"File not found: {file_path}"})
                return

            try:
                gdrive_run_id = self._new_child_run("gdrive")
                res = upload_clip_to_gdrive(
                    str(allowed_file),
                    folder_id=folder_id,
                    run_id=gdrive_run_id,
                    request_id=self._audit_request_id,
                )
                if res.get("success"):
                    res["status"] = "success"
                    res["link"] = res.get("web_view_link")
                    self.send_json(200, res)
                else:
                    res["status"] = "error"
                    err_msg = str(res.get("error", ""))
                    if "not found" in err_msg.lower():
                        self.send_json(404, res)
                    else:
                        self.send_json(500, res)
            except FileNotFoundError as e:
                self.send_json(404, {"status": "error", "success": False, "error": str(e)})
            except Exception as e:
                self.send_json(500, {"status": "error", "success": False, "error": str(e)})

    @observed_http_request
    def do_PUT(self):
        self._handle_unsupported_method()

    @observed_http_request
    def do_DELETE(self):
        self._handle_unsupported_method()

    @observed_http_request
    def do_PATCH(self):
        if not self._require_authorization():
            return
        if not self._require_safe_post_context():
            return
        route_path = urllib.parse.urlsplit(self.path).path
        if not route_path.startswith(self.API_V1_PREFIX):
            self._handle_unsupported_method()
            return
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self.send_json(400, {"success": False, "error": "Invalid Content-Length"})
            return
        if content_length <= 0 or content_length > self.MAX_REQUEST_BODY_BYTES:
            status = 413 if content_length > self.MAX_REQUEST_BODY_BYTES else 400
            self.send_json(status, {"success": False, "error": "Invalid request body size"})
            return
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            self.send_json(400, {"success": False, "error": "Invalid JSON format"})
            return
        if not isinstance(payload, dict):
            self.send_json(400, {"success": False, "error": "JSON payload must be an object"})
            return
        if self._handle_api_v1_patch(route_path, payload):
            return
        self.send_json(
            404,
            {"success": False, "error": "API v1 route not found"},
            no_store=True,
        )


    @observed_http_request
    def do_HEAD(self):
        self._handle_unsupported_method()

    @observed_http_request
    def do_OPTIONS(self):
        self._handle_unsupported_method()

    def _handle_unsupported_method(self):
        if not self._require_authorization():
            return
        all_routes = self.GET_ROUTES | self.TECHNICAL_GET_ROUTES | self.POST_ROUTES
        is_api = self.path.startswith("/api/")
        if (
            self.path in all_routes
            or self.path.startswith("/api/download/")
            or self.path.startswith(self.STATUS_ROUTE_PREFIX)
        ):
            if is_api:
                self.send_json(405, {"success": False, "error": "Method Not Allowed"}, no_store=True)
            else:
                self.send_error(405, "Method Not Allowed")
        else:
            if is_api:
                self.send_json(404, {"success": False, "error": "Not Found"}, no_store=True)
            else:
                self.send_error(404, "Not Found")


def start_dashboard_server(
    port: int = 8080,
    host: str = "127.0.0.1",
    api_token: str | None = None,
    output_dir: str | Path | None = None,
):
    """Start the dashboard with explicit exposure and a dedicated output root."""
    normalized_host = host.strip() or "127.0.0.1"
    if normalized_host not in {"127.0.0.1", "::1", "localhost"} and not api_token:
        raise ValueError("A bearer API token is required when binding beyond loopback")
    server_address = (normalized_host, port)
    httpd = ThreadingHTTPServer(server_address, ClipperDashboardHandler)
    httpd.api_token = api_token
    httpd.output_dir = Path(output_dir or (Path.cwd() / "output")).resolve()
    httpd.output_dir.mkdir(parents=True, exist_ok=True)
    httpd.panel_workspace = (httpd.output_dir.parent / "panel_workspace").resolve()
    httpd.panel_workspace.mkdir(parents=True, exist_ok=True)
    print(
        "🚀 Dashboard Server do YouTube Clipper rodando em: "
        f"http://{normalized_host}:{port}"
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor finalizado.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="YouTube Clipper Web Dashboard Server")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind to")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--api-token", type=str, default=None, help="Bearer token for auth")
    parser.add_argument("--output-dir", type=str, default=None, help="Dedicated output directory")
    args = parser.parse_args()

    start_dashboard_server(
        port=args.port,
        host=args.host,
        api_token=args.api_token,
        output_dir=args.output_dir,
    )
