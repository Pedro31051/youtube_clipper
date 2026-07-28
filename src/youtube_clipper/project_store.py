"""Persistent project domain for the intermediate dashboard.

SQLite stores product identity and state.  Media remains on the filesystem and
is referenced by immutable, versioned asset records.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from youtube_clipper.validator import parse_timestamp


SCHEMA_VERSION = 1
ID_PATTERN = re.compile(
    r"^(?:prj|src|anl|clp|ast|job|rnd|prv)_[0-9a-f]{32}$"
)
CLIP_STATES = {
    "proposed",
    "previewing",
    "ready",
    "approved",
    "rejected",
    "rendering",
    "rendered",
    "failed",
    "exported",
}
CLIP_TRANSITIONS = {
    "proposed": {"previewing", "ready", "rejected"},
    "previewing": {"ready", "failed"},
    "ready": {"approved", "rejected", "previewing"},
    "approved": {"rendering", "ready"},
    "rejected": {"ready"},
    "rendering": {"rendered", "failed"},
    "failed": {"previewing", "rendering"},
    "rendered": {"exported", "rendering"},
    "exported": {"rendering"},
}


class ProjectStoreError(RuntimeError):
    """Base error for persistent dashboard domain operations."""


class DomainNotFoundError(ProjectStoreError):
    """A requested persistent entity does not exist."""


class DomainConflictError(ProjectStoreError):
    """A requested state change violates a domain invariant."""


class DomainValidationError(ProjectStoreError):
    """Input cannot be represented by the persistent domain."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_load(value: Optional[str], default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class ProjectStore:
    """Thread-safe SQLite repository with filesystem clip manifests."""

    def __init__(self, database_path: Path | str, workspace_dir: Path | str):
        self.database_path = Path(database_path).expanduser().resolve()
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=10.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sources (
            source_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            uri TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS analyses (
            analysis_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            result_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS clips (
            clip_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
            analysis_id TEXT NOT NULL REFERENCES analyses(analysis_id) ON DELETE CASCADE,
            rank INTEGER NOT NULL,
            title TEXT NOT NULL,
            start_ms INTEGER NOT NULL,
            end_ms INTEGER NOT NULL,
            score REAL NOT NULL,
            status TEXT NOT NULL,
            plan_version INTEGER NOT NULL,
            edit_plan_json TEXT NOT NULL,
            suggestion_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (end_ms > start_ms),
            UNIQUE (analysis_id, rank)
        );
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            clip_id TEXT REFERENCES clips(clip_id) ON DELETE CASCADE,
            analysis_id TEXT REFERENCES analyses(analysis_id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            state TEXT NOT NULL,
            attempt INTEGER NOT NULL,
            run_id TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS assets (
            asset_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            clip_id TEXT NOT NULL REFERENCES clips(clip_id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            version INTEGER NOT NULL,
            file_path TEXT NOT NULL UNIQUE,
            sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            duration_ms INTEGER,
            width INTEGER,
            height INTEGER,
            mime_type TEXT NOT NULL,
            valid INTEGER NOT NULL DEFAULT 1,
            invalidated_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE (clip_id, kind, version)
        );
        CREATE TABLE IF NOT EXISTS renders (
            render_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            clip_id TEXT NOT NULL REFERENCES clips(clip_id) ON DELETE CASCADE,
            asset_id TEXT REFERENCES assets(asset_id) ON DELETE SET NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sources_project ON sources(project_id);
        CREATE INDEX IF NOT EXISTS idx_analyses_project ON analyses(project_id);
        CREATE INDEX IF NOT EXISTS idx_clips_project ON clips(project_id);
        CREATE INDEX IF NOT EXISTS idx_clips_analysis ON clips(analysis_id);
        CREATE INDEX IF NOT EXISTS idx_assets_clip ON assets(clip_id);
        CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id);
        """
        with self._write_lock:
            connection = self._connect()
            try:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(schema)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            finally:
                connection.close()

    @staticmethod
    def _require_id(value: str, prefix: str) -> str:
        if not isinstance(value, str) or not value.startswith(f"{prefix}_"):
            raise DomainValidationError(f"Invalid {prefix} identifier")
        if not ID_PATTERN.fullmatch(value):
            raise DomainValidationError(f"Invalid {prefix} identifier")
        return value

    @staticmethod
    def _row(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
        if row is None:
            return None
        result = dict(row)
        for key in ("edit_plan_json", "suggestion_json", "result_json"):
            if key in result:
                result[key.removesuffix("_json")] = _json_load(result.pop(key), {})
        return result

    def create_project(
        self,
        *,
        name: str,
        source_uri: str,
        source_kind: str,
    ) -> dict[str, Any]:
        clean_name = str(name or "").strip()
        clean_uri = str(source_uri or "").strip()
        clean_kind = str(source_kind or "").strip().lower()
        if not clean_name or len(clean_name) > 160:
            raise DomainValidationError("Project name must contain 1 to 160 characters")
        if not clean_uri:
            raise DomainValidationError("Project source URI is required")
        if clean_kind not in {"youtube", "local"}:
            raise DomainValidationError("Project source kind must be youtube or local")

        project_id = _new_id("prj")
        source_id = _new_id("src")
        timestamp = _now()
        with self._write_lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO projects(project_id, name, status, created_at, updated_at)
                    VALUES (?, ?, 'active', ?, ?)
                    """,
                    (project_id, clean_name, timestamp, timestamp),
                )
                connection.execute(
                    """
                    INSERT INTO sources(source_id, project_id, kind, uri, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (source_id, project_id, clean_kind, clean_uri, timestamp),
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.close()
        return self.get_project(project_id)

    def list_projects(self) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT p.*,
                       (SELECT COUNT(*) FROM clips c WHERE c.project_id = p.project_id)
                           AS clip_count,
                       (SELECT COUNT(*) FROM jobs j WHERE j.project_id = p.project_id)
                           AS job_count
                FROM projects p
                ORDER BY p.updated_at DESC, p.project_id DESC
                """
            ).fetchall()
            return [self._row(row) or {} for row in rows]
        finally:
            connection.close()

    def get_project(self, project_id: str) -> dict[str, Any]:
        self._require_id(project_id, "prj")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if row is None:
                raise DomainNotFoundError("Project not found")
            project = self._row(row) or {}
            sources = connection.execute(
                "SELECT * FROM sources WHERE project_id = ? ORDER BY created_at",
                (project_id,),
            ).fetchall()
            project["sources"] = [self._row(item) for item in sources]
            project["clip_count"] = int(
                connection.execute(
                    "SELECT COUNT(*) FROM clips WHERE project_id = ?",
                    (project_id,),
                ).fetchone()[0]
            )
            return project
        finally:
            connection.close()

    def update_project_status(self, project_id: str, status: str) -> dict[str, Any]:
        self.get_project(project_id)
        clean_status = str(status or "").strip().lower()
        if clean_status not in {"active", "analyzing", "review", "failed"}:
            raise DomainValidationError("Project status is invalid")
        with self._write_lock:
            connection = self._connect()
            try:
                connection.execute(
                    """
                    UPDATE projects SET status = ?, updated_at = ?
                    WHERE project_id = ?
                    """,
                    (clean_status, _now(), project_id),
                )
            finally:
                connection.close()
        return self.get_project(project_id)

    def get_primary_source(self, project_id: str) -> dict[str, Any]:
        self._require_id(project_id, "prj")
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM sources
                WHERE project_id = ?
                ORDER BY created_at, source_id
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            if row is None:
                raise DomainNotFoundError("Project source not found")
            return self._row(row) or {}
        finally:
            connection.close()

    def get_source(self, source_id: str) -> dict[str, Any]:
        self._require_id(source_id, "src")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM sources WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            if row is None:
                raise DomainNotFoundError("Source not found")
            return self._row(row) or {}
        finally:
            connection.close()

    def create_analysis(
        self,
        *,
        project_id: str,
        source_id: Optional[str] = None,
        status: str = "running",
    ) -> dict[str, Any]:
        project = self.get_project(project_id)
        source = (
            self.get_primary_source(project_id)
            if source_id is None
            else next(
                (
                    item
                    for item in project["sources"]
                    if item and item["source_id"] == source_id
                ),
                None,
            )
        )
        if source is None:
            raise DomainNotFoundError("Source not found in project")
        analysis_id = _new_id("anl")
        timestamp = _now()
        with self._write_lock:
            connection = self._connect()
            try:
                connection.execute(
                    """
                    INSERT INTO analyses(
                        analysis_id, project_id, source_id, status,
                        result_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, NULL, ?, ?)
                    """,
                    (
                        analysis_id,
                        project_id,
                        source["source_id"],
                        status,
                        timestamp,
                        timestamp,
                    ),
                )
            finally:
                connection.close()
        return {
            "analysis_id": analysis_id,
            "project_id": project_id,
            "source_id": source["source_id"],
            "status": status,
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    @staticmethod
    def _clip_bounds(candidate: dict[str, Any]) -> tuple[int, int]:
        start_value = candidate.get("start_time", candidate.get("start_timestamp"))
        end_value = candidate.get("end_time", candidate.get("end_timestamp"))
        try:
            start_ms = int(round(parse_timestamp(start_value) * 1000))
            end_ms = int(round(parse_timestamp(end_value) * 1000))
        except Exception as exc:
            raise DomainValidationError(
                "Analysis candidate contains invalid timestamps"
            ) from exc
        if start_ms < 0 or end_ms <= start_ms:
            raise DomainValidationError("Analysis candidate interval is invalid")
        return start_ms, end_ms

    def finish_analysis(
        self,
        *,
        analysis_id: str,
        result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        self._require_id(analysis_id, "anl")
        candidates = result.get("clips", [])
        if not isinstance(candidates, list):
            raise DomainValidationError("Analysis clips must be a list")

        with self._write_lock:
            connection = self._connect()
            try:
                analysis_row = connection.execute(
                    "SELECT * FROM analyses WHERE analysis_id = ?",
                    (analysis_id,),
                ).fetchone()
                if analysis_row is None:
                    raise DomainNotFoundError("Analysis not found")
                if analysis_row["status"] == "completed":
                    existing = connection.execute(
                        "SELECT * FROM clips WHERE analysis_id = ? ORDER BY rank",
                        (analysis_id,),
                    ).fetchall()
                    return [self._public_clip(self._row(row) or {}) for row in existing]

                timestamp = _now()
                prepared: list[tuple[Any, ...]] = []
                clip_ids: list[str] = []
                ui_settings = result.get("ui_settings") or {}
                aspect_ratio = str(ui_settings.get("aspect_ratio", "9:16"))
                if aspect_ratio not in {"9:16", "1:1", "16:9"}:
                    raise DomainValidationError("Analysis aspect ratio is invalid")
                for index, raw_candidate in enumerate(candidates, start=1):
                    if not isinstance(raw_candidate, dict):
                        raise DomainValidationError("Analysis candidate must be an object")
                    start_ms, end_ms = self._clip_bounds(raw_candidate)
                    clip_id = _new_id("clp")
                    rank = int(raw_candidate.get("rank", index))
                    title = str(raw_candidate.get("title") or f"Corte {rank}").strip()
                    score = float(raw_candidate.get("score", 0.0))
                    edit_plan = {
                        "schema_version": "1.0.0",
                        "plan_version": 1,
                        "clip_id": clip_id,
                        "source_id": analysis_row["source_id"],
                        "timeline": {
                            "start_ms": start_ms,
                            "end_ms": end_ms,
                            "duration_ms": end_ms - start_ms,
                        },
                        "layout": {"mode": "blur_background"},
                        "captions": {
                            "enabled": False,
                            "theme": "classic",
                            "position": "bottom",
                        },
                        "audio": {
                            "include_source": True,
                            "normalize": True,
                            "narration_type": "none",
                            "narration_path": None,
                        },
                        "editorial": {
                            "overlay_enabled": False,
                            "overlay_text": None,
                            "template_variant": "variant_default",
                        },
                        "output": {
                            "aspect_ratio": aspect_ratio,
                            "resolution": (
                                "1080x1080"
                                if aspect_ratio == "1:1"
                                else "1920x1080"
                                if aspect_ratio == "16:9"
                                else "1080x1920"
                            ),
                        },
                    }
                    prepared.append(
                        (
                            clip_id,
                            analysis_row["project_id"],
                            analysis_row["source_id"],
                            analysis_id,
                            rank,
                            title,
                            start_ms,
                            end_ms,
                            score,
                            "proposed",
                            1,
                            _json_dump(edit_plan),
                            _json_dump(raw_candidate),
                            timestamp,
                            timestamp,
                        )
                    )
                    clip_ids.append(clip_id)

                connection.execute("BEGIN IMMEDIATE")
                connection.executemany(
                    """
                    INSERT INTO clips(
                        clip_id, project_id, source_id, analysis_id, rank, title,
                        start_ms, end_ms, score, status, plan_version,
                        edit_plan_json, suggestion_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    prepared,
                )
                connection.execute(
                    """
                    UPDATE analyses
                    SET status = 'completed', result_json = ?, updated_at = ?
                    WHERE analysis_id = ?
                    """,
                    (_json_dump(result), timestamp, analysis_id),
                )
                connection.execute(
                    "UPDATE projects SET updated_at = ? WHERE project_id = ?",
                    (timestamp, analysis_row["project_id"]),
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.close()

        clips = [self.get_clip(clip_id) for clip_id in clip_ids]
        for clip in clips:
            self._write_clip_manifest(clip["clip_id"])
        return clips

    def fail_analysis(self, analysis_id: str, result: dict[str, Any]) -> None:
        self._require_id(analysis_id, "anl")
        with self._write_lock:
            connection = self._connect()
            try:
                cursor = connection.execute(
                    """
                    UPDATE analyses
                    SET status = 'failed', result_json = ?, updated_at = ?
                    WHERE analysis_id = ?
                    """,
                    (_json_dump(result), _now(), analysis_id),
                )
                if cursor.rowcount != 1:
                    raise DomainNotFoundError("Analysis not found")
            finally:
                connection.close()

    def list_clips(self, project_id: str) -> list[dict[str, Any]]:
        self.get_project(project_id)
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM clips
                WHERE project_id = ?
                ORDER BY created_at DESC, rank ASC
                """,
                (project_id,),
            ).fetchall()
            clip_ids = [str(row["clip_id"]) for row in rows]
        finally:
            connection.close()
        return [self.get_clip(clip_id) for clip_id in clip_ids]

    def get_clip(self, clip_id: str) -> dict[str, Any]:
        self._require_id(clip_id, "clp")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM clips WHERE clip_id = ?",
                (clip_id,),
            ).fetchone()
            if row is None:
                raise DomainNotFoundError("Clip not found")
            clip = self._public_clip(self._row(row) or {})
            assets = connection.execute(
                """
                SELECT * FROM assets
                WHERE clip_id = ?
                ORDER BY kind, version DESC
                """,
                (clip_id,),
            ).fetchall()
            clip["assets"] = [self._public_asset(self._row(item) or {}) for item in assets]
            latest_valid = {}
            for asset in clip["assets"]:
                if asset["valid"] and asset["kind"] not in latest_valid:
                    latest_valid[asset["kind"]] = asset
            preview = latest_valid.get("preview")
            poster = latest_valid.get("poster")
            clip["preview_asset"] = preview
            clip["poster_asset"] = poster
            clip["preview_url"] = preview["url"] if preview else None
            clip["poster_url"] = poster["url"] if poster else None
            if preview:
                clip["preview_status"] = "ready"
            elif any(asset["kind"] == "preview" for asset in clip["assets"]):
                clip["preview_status"] = "stale"
            else:
                clip["preview_status"] = "missing"
            return clip
        finally:
            connection.close()

    @staticmethod
    def _public_clip(clip: dict[str, Any]) -> dict[str, Any]:
        result = dict(clip)
        result["duration_ms"] = int(result["end_ms"]) - int(result["start_ms"])
        return result

    def update_clip(
        self,
        clip_id: str,
        changes: dict[str, Any],
        *,
        expected_plan_version: Optional[int] = None,
    ) -> dict[str, Any]:
        allowed = {
            "title", "start_ms", "end_ms", "status",
            "layout", "captions", "audio", "editorial", "output",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise DomainValidationError(
                f"Unsupported clip fields: {', '.join(sorted(unknown))}"
            )
        current = self.get_clip(clip_id)
        if (
            expected_plan_version is not None
            and int(expected_plan_version) != int(current["plan_version"])
        ):
            raise DomainConflictError(
                "Edit plan changed since it was loaded; refresh before saving"
            )
        title = str(changes.get("title", current["title"])).strip()
        start_ms = int(changes.get("start_ms", current["start_ms"]))
        end_ms = int(changes.get("end_ms", current["end_ms"]))
        status = str(changes.get("status", current["status"])).strip().lower()
        if not title or len(title) > 240:
            raise DomainValidationError("Clip title must contain 1 to 240 characters")
        if start_ms < 0 or end_ms <= start_ms:
            raise DomainValidationError("Clip interval is invalid")
        if end_ms - start_ms > 59900:
            raise DomainValidationError("Clip duration must be at most 59900 ms")
        if status not in CLIP_STATES:
            raise DomainValidationError("Clip status is invalid")
        if status != current["status"] and status not in CLIP_TRANSITIONS[current["status"]]:
            raise DomainConflictError(
                f"Cannot transition clip from {current['status']} to {status}"
            )

        plan = json.loads(json.dumps(current["edit_plan"]))
        plan_version = int(current["plan_version"])
        timeline_changed = (
            start_ms != current["start_ms"] or end_ms != current["end_ms"]
        )
        plan_changed = timeline_changed
        plan_sections = {
            "layout": {"mode", "crop_focus", "blur_sigma", "overlay_position"},
            "captions": {"enabled", "theme", "position"},
            "audio": {
                "include_source", "normalize", "narration_type", "narration_path",
            },
            "editorial": {
                "overlay_enabled", "overlay_text", "template_variant",
            },
            "output": {"aspect_ratio", "resolution"},
        }
        for section, allowed_keys in plan_sections.items():
            if section not in changes:
                continue
            incoming = changes[section]
            if not isinstance(incoming, dict):
                raise DomainValidationError(f"{section} must be an object")
            unknown_keys = set(incoming) - allowed_keys
            if unknown_keys:
                raise DomainValidationError(
                    f"Unsupported {section} fields: "
                    f"{', '.join(sorted(unknown_keys))}"
                )
            merged = dict(plan.get(section) or {})
            merged.update(incoming)
            if merged != plan.get(section):
                plan_changed = True
                plan[section] = merged

        layout = plan.get("layout") or {}
        if layout.get("mode", "blur_background") not in {
            "blur_background", "split_blur", "crop_center",
        }:
            raise DomainValidationError("Layout mode is invalid")
        if layout.get("crop_focus", "center") not in {"left", "center", "right"}:
            raise DomainValidationError("Layout crop_focus is invalid")
        if layout.get("overlay_position", "top") not in {"top", "bottom"}:
            raise DomainValidationError("Layout overlay_position is invalid")
        try:
            blur_sigma = float(layout.get("blur_sigma", 12.0))
        except (TypeError, ValueError) as exc:
            raise DomainValidationError("Layout blur_sigma is invalid") from exc
        if not 0.0 <= blur_sigma <= 50.0:
            raise DomainValidationError("Layout blur_sigma is invalid")
        if not isinstance((plan.get("captions") or {}).get("enabled", False), bool):
            raise DomainValidationError("Captions enabled must be boolean")
        if (plan.get("captions") or {}).get("theme", "classic") not in {
            "classic", "solid", "highlight",
        }:
            raise DomainValidationError("Captions theme is invalid")
        if (plan.get("captions") or {}).get("position", "bottom") not in {
            "bottom", "center", "top",
        }:
            raise DomainValidationError("Captions position is invalid")
        if not isinstance((plan.get("audio") or {}).get("include_source", True), bool):
            raise DomainValidationError("Audio include_source must be boolean")
        if not isinstance((plan.get("audio") or {}).get("normalize", True), bool):
            raise DomainValidationError("Audio normalize must be boolean")
        if (plan.get("audio") or {}).get("narration_type", "none") not in {
            "none", "external",
        }:
            raise DomainValidationError("Audio narration_type is invalid")
        narration_path = (plan.get("audio") or {}).get("narration_path")
        if narration_path is not None and not isinstance(narration_path, str):
            raise DomainValidationError("Audio narration_path is invalid")
        overlay_text = (plan.get("editorial") or {}).get("overlay_text")
        if overlay_text is not None and (
            not isinstance(overlay_text, str) or len(overlay_text) > 240
        ):
            raise DomainValidationError("Editorial overlay_text is invalid")
        if not isinstance(
            (plan.get("editorial") or {}).get("overlay_enabled", False), bool
        ):
            raise DomainValidationError("Editorial overlay_enabled must be boolean")
        if (plan.get("editorial") or {}).get(
            "template_variant", "variant_default"
        ) not in {"variant_default", "variant_news", "variant_impact"}:
            raise DomainValidationError("Editorial template_variant is invalid")
        output = plan.get("output") or {}
        if output.get("aspect_ratio", "9:16") not in {"9:16", "1:1", "16:9"}:
            raise DomainValidationError("Output aspect_ratio is invalid")
        if output.get("resolution", "1080x1920") not in {
            "720x1280", "1080x1920", "1080x1080", "1920x1080",
        }:
            raise DomainValidationError("Output resolution is invalid")

        if plan_changed:
            plan_version += 1
            plan["plan_version"] = plan_version
            if status in {"approved", "rejected", "rendered", "exported", "failed"}:
                status = "ready"
        if timeline_changed:
            plan["timeline"] = {
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration_ms": end_ms - start_ms,
            }

        timestamp = _now()
        with self._write_lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    UPDATE clips
                    SET title = ?, start_ms = ?, end_ms = ?, status = ?,
                        plan_version = ?, edit_plan_json = ?, updated_at = ?
                    WHERE clip_id = ?
                    """,
                    (
                        title,
                        start_ms,
                        end_ms,
                        status,
                        plan_version,
                        _json_dump(plan),
                        timestamp,
                        clip_id,
                    ),
                )
                if plan_changed:
                    connection.execute(
                        """
                        UPDATE assets
                        SET valid = 0, invalidated_at = ?
                        WHERE clip_id = ?
                          AND kind IN ('preview', 'poster', 'render')
                          AND valid = 1
                        """,
                        (timestamp, clip_id),
                    )
                connection.execute(
                    "UPDATE projects SET updated_at = ? WHERE project_id = ?",
                    (timestamp, current["project_id"]),
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.close()
        updated = self.get_clip(clip_id)
        self._write_clip_manifest(clip_id)
        return updated

    def review_clips(
        self,
        clip_ids: list[str],
        decision: str,
    ) -> list[dict[str, Any]]:
        """Apply one bounded review decision atomically by immutable clip ID."""
        unique_ids = list(dict.fromkeys(clip_ids))
        if not unique_ids or len(unique_ids) > 20:
            raise DomainValidationError(
                "Review actions require between 1 and 20 unique clips"
            )
        clean_decision = str(decision or "").strip().lower()
        if clean_decision not in {"approve", "reject"}:
            raise DomainValidationError("Review decision must be approve or reject")

        clips = [self.get_clip(clip_id) for clip_id in unique_ids]
        project_ids = {clip["project_id"] for clip in clips}
        if len(project_ids) != 1:
            raise DomainValidationError(
                "A batch review may only contain clips from one project"
            )
        for clip in clips:
            if clean_decision == "approve":
                if clip["preview_status"] != "ready":
                    raise DomainConflictError(
                        f"Clip {clip['clip_id']} requires a ready preview before approval"
                    )
                if clip["status"] not in {"ready", "rejected"}:
                    raise DomainConflictError(
                        f"Cannot approve clip while it is {clip['status']}"
                    )
            elif clip["status"] not in {"proposed", "ready", "approved"}:
                raise DomainConflictError(
                    f"Cannot reject clip while it is {clip['status']}"
                )

        target_status = "approved" if clean_decision == "approve" else "rejected"
        timestamp = _now()
        placeholders = ",".join("?" for _ in unique_ids)
        with self._write_lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    f"""
                    UPDATE clips SET status = ?, updated_at = ?
                    WHERE clip_id IN ({placeholders})
                    """,
                    (target_status, timestamp, *unique_ids),
                )
                connection.execute(
                    "UPDATE projects SET updated_at = ? WHERE project_id = ?",
                    (timestamp, next(iter(project_ids))),
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.close()

        reviewed = [self.get_clip(clip_id) for clip_id in unique_ids]
        for clip_id in unique_ids:
            self._write_clip_manifest(clip_id)
        return reviewed

    def create_job(
        self,
        *,
        project_id: str,
        kind: str,
        clip_id: Optional[str] = None,
        analysis_id: Optional[str] = None,
        state: str = "queued",
    ) -> dict[str, Any]:
        self.get_project(project_id)
        job_id = _new_id("job")
        timestamp = _now()
        with self._write_lock:
            connection = self._connect()
            try:
                connection.execute(
                    """
                    INSERT INTO jobs(
                        job_id, project_id, clip_id, analysis_id, kind, state,
                        attempt, run_id, error, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, NULL, NULL, ?, ?)
                    """,
                    (
                        job_id,
                        project_id,
                        clip_id,
                        analysis_id,
                        str(kind),
                        str(state),
                        timestamp,
                        timestamp,
                    ),
                )
            finally:
                connection.close()
        return self.get_job(job_id)

    def update_job(
        self,
        job_id: str,
        *,
        state: str,
        run_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> dict[str, Any]:
        self._require_id(job_id, "job")
        with self._write_lock:
            connection = self._connect()
            try:
                cursor = connection.execute(
                    """
                    UPDATE jobs
                    SET state = ?, run_id = COALESCE(?, run_id), error = ?,
                        updated_at = ?
                    WHERE job_id = ?
                    """,
                    (state, run_id, error, _now(), job_id),
                )
                if cursor.rowcount != 1:
                    raise DomainNotFoundError("Job not found")
            finally:
                connection.close()
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict[str, Any]:
        self._require_id(job_id, "job")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise DomainNotFoundError("Job not found")
            return self._row(row) or {}
        finally:
            connection.close()

    def list_jobs(
        self,
        *,
        project_id: Optional[str] = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        if project_id is not None:
            self.get_project(project_id)
        normalized_limit = int(limit)
        if normalized_limit < 1 or normalized_limit > 100:
            raise DomainValidationError("Job limit must be between 1 and 100")
        connection = self._connect()
        try:
            if project_id is None:
                rows = connection.execute(
                    """
                    SELECT * FROM jobs
                    ORDER BY updated_at DESC, job_id DESC
                    LIMIT ?
                    """,
                    (normalized_limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM jobs
                    WHERE project_id = ?
                    ORDER BY updated_at DESC, job_id DESC
                    LIMIT ?
                    """,
                    (project_id, normalized_limit),
                ).fetchall()
            return [self._row(row) or {} for row in rows]
        finally:
            connection.close()

    def add_asset(
        self,
        *,
        clip_id: str,
        kind: str,
        source_path: Path | str,
        mime_type: str,
        duration_ms: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> dict[str, Any]:
        clip = self.get_clip(clip_id)
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise DomainValidationError("Asset source file does not exist")
        clean_kind = re.sub(r"[^a-z0-9_-]+", "-", str(kind).lower()).strip("-")
        if not clean_kind:
            raise DomainValidationError("Asset kind is required")
        suffix = source.suffix.lower() or ".bin"
        asset_id = _new_id("ast")
        timestamp = _now()

        with self._write_lock:
            connection = self._connect()
            try:
                latest = connection.execute(
                    """
                    SELECT COALESCE(MAX(version), 0)
                    FROM assets WHERE clip_id = ? AND kind = ?
                    """,
                    (clip_id, clean_kind),
                ).fetchone()[0]
                version = int(latest) + 1
                clip_dir = self._clip_dir(clip["project_id"], clip_id)
                asset_dir = clip_dir / "assets"
                asset_dir.mkdir(parents=True, exist_ok=True)
                file_name = f"{asset_id}.v{version}{suffix}"
                destination = (asset_dir / file_name).resolve()
                destination.relative_to(asset_dir.resolve())
                if destination.exists():
                    raise DomainConflictError("Immutable asset path already exists")
                with source.open("rb") as source_stream, destination.open("xb") as target:
                    digest = hashlib.sha256()
                    size_bytes = 0
                    for chunk in iter(lambda: source_stream.read(65536), b""):
                        target.write(chunk)
                        digest.update(chunk)
                        size_bytes += len(chunk)
                sha256 = digest.hexdigest()
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute(
                        """
                        INSERT INTO assets(
                            asset_id, project_id, clip_id, kind, version,
                            file_path, sha256, size_bytes, duration_ms,
                            width, height, mime_type, valid, invalidated_at,
                            created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, ?)
                        """,
                        (
                            asset_id,
                            clip["project_id"],
                            clip_id,
                            clean_kind,
                            version,
                            str(destination),
                            sha256,
                            size_bytes,
                            duration_ms,
                            width,
                            height,
                            str(mime_type),
                            timestamp,
                        ),
                    )
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    destination.unlink(missing_ok=True)
                    raise
            finally:
                connection.close()

        asset = self.get_asset(asset_id)
        self._write_clip_manifest(clip_id)
        return asset

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        self._require_id(asset_id, "ast")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM assets WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
            if row is None:
                raise DomainNotFoundError("Asset not found")
            return self._public_asset(self._row(row) or {})
        finally:
            connection.close()

    @staticmethod
    def _public_asset(asset: dict[str, Any]) -> dict[str, Any]:
        result = dict(asset)
        result.pop("file_path", None)
        result["valid"] = bool(result.get("valid"))
        result["url"] = (
            f"/api/v1/assets/{result['asset_id']}?v={result['version']}"
        )
        return result

    def resolve_asset_file(
        self,
        asset_id: str,
        *,
        version: Optional[int] = None,
        require_valid: bool = True,
    ) -> tuple[dict[str, Any], Path]:
        self._require_id(asset_id, "ast")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM assets WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
            if row is None:
                raise DomainNotFoundError("Asset not found")
            record = self._row(row) or {}
        finally:
            connection.close()
        if version is not None and int(record["version"]) != int(version):
            raise DomainNotFoundError("Asset version not found")
        if require_valid and not bool(record["valid"]):
            raise DomainConflictError("Asset is no longer valid")

        path = Path(record["file_path"]).resolve()
        clip_root = self._clip_dir(
            record["project_id"], record["clip_id"]
        ).resolve()
        try:
            path.relative_to(clip_root)
        except ValueError as exc:
            raise DomainConflictError("Asset path escaped its clip workspace") from exc
        if not path.is_file():
            raise DomainNotFoundError("Asset file not found")

        digest = hashlib.sha256()
        size_bytes = 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
                size_bytes += len(chunk)
        if (
            size_bytes != int(record["size_bytes"])
            or digest.hexdigest() != record["sha256"]
        ):
            raise DomainConflictError("Asset integrity verification failed")
        return self._public_asset(record), path

    def create_render(
        self,
        *,
        clip_id: str,
        asset_id: Optional[str] = None,
        status: str = "rendered",
    ) -> dict[str, Any]:
        clip = self.get_clip(clip_id)
        if asset_id is not None:
            asset = self.get_asset(asset_id)
            if asset["clip_id"] != clip_id:
                raise DomainConflictError("Render asset belongs to a different clip")
        render_id = _new_id("rnd")
        timestamp = _now()
        with self._write_lock:
            connection = self._connect()
            try:
                connection.execute(
                    """
                    INSERT INTO renders(
                        render_id, project_id, clip_id, asset_id, status,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        render_id,
                        clip["project_id"],
                        clip_id,
                        asset_id,
                        status,
                        timestamp,
                        timestamp,
                    ),
                )
            finally:
                connection.close()
        return {
            "render_id": render_id,
            "project_id": clip["project_id"],
            "clip_id": clip_id,
            "asset_id": asset_id,
            "status": status,
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    def _clip_dir(self, project_id: str, clip_id: str) -> Path:
        return self.workspace_dir / "projects" / project_id / "clips" / clip_id

    def manifest_path(self, clip_id: str) -> Path:
        clip = self.get_clip(clip_id)
        return self._clip_dir(clip["project_id"], clip_id) / "manifest.json"

    def _write_clip_manifest(self, clip_id: str) -> Path:
        clip = self.get_clip(clip_id)
        manifest_path = self._clip_dir(
            clip["project_id"], clip_id
        ) / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema_version": "1.0.0",
            "project_id": clip["project_id"],
            "source_id": clip["source_id"],
            "analysis_id": clip["analysis_id"],
            "clip_id": clip["clip_id"],
            "rank": clip["rank"],
            "status": clip["status"],
            "plan_version": clip["plan_version"],
            "edit_plan": clip["edit_plan"],
            "assets": [
                {
                    key: asset.get(key)
                    for key in (
                        "asset_id",
                        "clip_id",
                        "kind",
                        "version",
                        "sha256",
                        "size_bytes",
                        "duration_ms",
                        "width",
                        "height",
                        "mime_type",
                        "valid",
                        "invalidated_at",
                        "url",
                    )
                }
                for asset in clip.get("assets", [])
            ],
            "updated_at": clip["updated_at"],
        }
        temporary = manifest_path.with_name(
            f".{manifest_path.name}.{uuid.uuid4().hex}.tmp"
        )
        temporary.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, manifest_path)
        return manifest_path

    def database_user_version(self) -> int:
        connection = self._connect()
        try:
            return int(connection.execute("PRAGMA user_version").fetchone()[0])
        finally:
            connection.close()
