"""Canonical audit logging and the sole subprocess execution boundary.

Schema 2.0 adds explicit lifecycle events while readers remain compatible with
the fixed 1.0 audit schema.  The module deliberately has no dependency on the
rest of the application so logging is available during bootstrap and failures.
"""

from __future__ import annotations

import contextlib
import contextvars
import fcntl
import functools
import hashlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Sequence, Union

SCHEMA_VERSION = "2.0.0"
LEGACY_SCHEMA_VERSION = "1.0.0"

ALLOWED_STAGES = {
    "env", "ingest", "transcribe", "scenes", "select", "cut",
    "subtitles", "audio", "transform", "render", "verify", "report",
}
ALLOWED_STATUSES = {
    "planned", "started", "succeeded", "failed", "skipped", "retrying",
    "cancelled", "interrupted",
}
TERMINAL_STATUSES = {"succeeded", "failed", "skipped", "cancelled", "interrupted"}

_RUN_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "cortes_run_id", default=None
)
_TRACE_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "cortes_trace_id", default=None
)
_SPAN_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "cortes_span_id", default=None
)
_REQUEST_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "cortes_request_id", default=None
)

_SECRET_KEY = re.compile(
    r"(authorization|api[-_]?key|access[-_]?token|refresh[-_]?token|"
    r"client[-_]?secret|password|passwd|cookie|credential)",
    re.IGNORECASE,
)
_SECRET_INLINE = re.compile(
    r"(?i)\b(authorization|api[-_]?key|access[-_]?token|refresh[-_]?token|"
    r"client[-_]?secret|password|passwd|cookie)\b"
    r"(\s*[:=]\s*|\s+)([^\s,;]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_SIGNED_QUERY = re.compile(
    r"(?i)([?&](?:signature|sig|token|key|x-goog-signature|x-amz-signature)=)[^&\s]+"
)


class AuditLogError(RuntimeError):
    """The canonical audit trail could not be persisted safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(value: Any, key: Optional[str] = None) -> Any:
    """Recursively remove common secrets without changing ordinary values."""
    if key and _SECRET_KEY.search(str(key)):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [redact(item) for item in value]
    if isinstance(value, pathlib.Path):
        value = str(value)
    if not isinstance(value, str):
        return value
    text = _BEARER.sub("Bearer [REDACTED]", value)
    text = _SECRET_INLINE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
    text = _SIGNED_QUERY.sub(lambda m: f"{m.group(1)}[REDACTED]", text)
    return text


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        if isinstance(value, pathlib.Path):
            return str(value)
        if isinstance(value, Mapping):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(v) for v in value]
        return repr(value)


def set_run_id(run_id: str) -> None:
    """Set the active run in the current context only."""
    _RUN_ID.set(str(run_id))
    if _TRACE_ID.get() is None:
        _TRACE_ID.set(uuid.uuid4().hex)


def set_request_id(request_id: Optional[str]) -> None:
    _REQUEST_ID.set(request_id)


def get_run_id() -> str:
    current = _RUN_ID.get()
    if current:
        return current
    env_run_id = os.environ.get("CORTES_RUN_ID")
    generated = env_run_id or f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"
    set_run_id(generated)
    return generated


def get_run_dir(run_id: Optional[str] = None) -> pathlib.Path:
    path = pathlib.Path("runs") / (run_id or get_run_id())
    path.mkdir(parents=True, exist_ok=True)
    return path


def compute_sha256(file_path: Union[str, pathlib.Path]) -> str:
    path = pathlib.Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Cannot compute hash: file '{file_path}' does not exist.")
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def evidence_for(paths: Sequence[Union[str, pathlib.Path]]) -> Dict[str, List[Any]]:
    run_root = get_run_dir().resolve()
    result: Dict[str, List[Any]] = {"paths": [], "sha256": [], "bytes": []}
    seen = set()
    for raw_path in paths:
        path = pathlib.Path(raw_path)
        if not path.exists() or not path.is_file():
            continue
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(run_root)
        except ValueError:
            continue
        key = str(relative)
        if key in seen:
            continue
        seen.add(key)
        result["paths"].append(str(resolved))
        result["sha256"].append(compute_sha256(resolved))
        result["bytes"].append(resolved.stat().st_size)
    return result


def _legacy_fields() -> List[str]:
    return [
        "schema_version", "run_id", "seq", "ts", "agent", "video_id",
        "clip_id", "stage", "attempt", "severity", "duration_ms", "tool",
        "cmd", "exit_code", "args_hash", "cost", "trace", "evidence",
        "outcome", "error", "claim",
    ]


def validate_event_dict(event: Dict[str, Any]) -> None:
    """Validate either an immutable legacy event or a lifecycle 2.0 event."""
    version = event.get("schema_version")
    if version == LEGACY_SCHEMA_VERSION:
        required = _legacy_fields()
        if set(event) != set(required):
            missing = [field for field in required if field not in event]
            extra = [field for field in event if field not in required]
            raise ValueError(f"Event schema 1.0 violation. Missing: {missing}, Extra: {extra}")
    elif version == SCHEMA_VERSION:
        required_v2 = set(_legacy_fields()) | {
            "event_id", "request_id", "component", "action", "status",
            "decision", "next", "input", "execution",
        }
        missing = sorted(required_v2 - set(event))
        if missing:
            raise ValueError(f"Event schema 2.0 violation. Missing: {missing}")
        if event["status"] not in ALLOWED_STATUSES:
            raise ValueError(f"Invalid lifecycle status: {event['status']}")
        next_value = event["next"]
        if not isinstance(next_value, dict) or set(next_value) != {"action", "stage", "reason"}:
            raise ValueError("Invalid next object")
        if event["status"] in TERMINAL_STATUSES and not next_value.get("action") and not next_value.get("reason"):
            raise ValueError("Terminal events must identify a next action or terminal reason")
        error = event["error"]
        if error is not None:
            expected_error = {
                "category", "type", "message", "causes", "failure_point",
                "retryable", "exit_code", "signal", "remediation", "traceback_path",
                "stderr_path",
            }
            if not isinstance(error, dict) or set(error) != expected_error:
                raise ValueError("Invalid structured error object")
    else:
        raise ValueError(f"Unsupported schema_version: {version}")

    if not isinstance(event.get("seq"), int) or event["seq"] < 1:
        raise ValueError("seq must be an integer >= 1")
    if event.get("stage") not in ALLOWED_STAGES:
        raise ValueError(f"Invalid stage: {event.get('stage')}")
    if event.get("severity") not in {"info", "warn", "error"}:
        raise ValueError(f"Invalid severity: {event.get('severity')}")
    if event.get("outcome") not in {"ok", "fail"}:
        raise ValueError(f"Invalid outcome: {event.get('outcome')}")
    args_hash = event.get("args_hash")
    if not isinstance(args_hash, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", args_hash):
        raise ValueError("Invalid args_hash")
    evidence = event.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != {"paths", "sha256", "bytes"}:
        raise ValueError("Invalid evidence object")
    lengths = [len(evidence[name]) for name in ("paths", "sha256", "bytes")]
    if len(set(lengths)) != 1:
        raise ValueError("Evidence arrays must have equal lengths")
    if event.get("claim") and not evidence["paths"]:
        raise ValueError("Interpretive claims require evidence")


def _normalize_evidence(
    evidence: Optional[Dict[str, Any]], run_dir: pathlib.Path
) -> Dict[str, List[Any]]:
    incoming = evidence or {"paths": [], "sha256": [], "bytes": []}
    paths = list(incoming.get("paths", []))
    hashes = list(incoming.get("sha256", []))
    sizes = list(incoming.get("bytes", []))
    if len(paths) != len(hashes) or len(paths) != len(sizes):
        raise ValueError("Evidence arrays must have equal lengths")
    normalized: Dict[str, List[Any]] = {"paths": [], "sha256": [], "bytes": []}
    run_root = run_dir.resolve()
    for index, raw_path in enumerate(paths):
        resolved = pathlib.Path(raw_path).resolve()
        try:
            relative = resolved.relative_to(run_root)
        except ValueError as exc:
            raise ValueError(f"Evidence path must be inside its run directory: {resolved}") from exc
        normalized["paths"].append(str(relative))
        normalized["sha256"].append(str(hashes[index]))
        normalized["bytes"].append(int(sizes[index]))
    return normalized


def _error_dict(
    exc: BaseException,
    *,
    category: str = "application",
    retryable: bool = False,
    exit_code: Optional[int] = None,
    signal: Optional[int] = None,
    remediation: Optional[str] = None,
    traceback_path: Optional[str] = None,
    stderr_path: Optional[str] = None,
) -> Dict[str, Any]:
    causes: List[Dict[str, str]] = []
    current = exc.__cause__ or exc.__context__
    visited = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        causes.append({"type": type(current).__name__, "message": str(redact(str(current)))})
        current = current.__cause__ or current.__context__
    frame = traceback.extract_tb(exc.__traceback__)[-1] if exc.__traceback__ else None
    failure_point = f"{frame.filename}:{frame.lineno}:{frame.name}" if frame else None
    return {
        "category": category,
        "type": type(exc).__name__,
        "message": str(redact(str(exc))),
        "causes": causes,
        "failure_point": failure_point,
        "retryable": bool(retryable),
        "exit_code": exit_code,
        "signal": signal,
        "remediation": remediation,
        "traceback_path": traceback_path,
        "stderr_path": stderr_path,
    }


def emit_event(
    stage: str,
    agent: str = "worker",
    video_id: str = "unknown",
    clip_id: Optional[str] = None,
    attempt: int = 1,
    severity: str = "info",
    duration_ms: float = 0.0,
    tool: str = "python",
    cmd: Optional[str] = None,
    exit_code: int = 0,
    args_hash: Optional[str] = None,
    cost: Optional[Dict[str, Any]] = None,
    trace: Optional[Dict[str, Any]] = None,
    evidence: Optional[Dict[str, Any]] = None,
    outcome: str = "ok",
    error: Optional[Union[str, Dict[str, Any]]] = None,
    claim: Optional[str] = None,
    run_id: Optional[str] = None,
    ts: Optional[str] = None,
    *,
    status: Optional[str] = None,
    component: str = "cortes",
    action: Optional[str] = None,
    request_id: Optional[str] = None,
    decision: Optional[Dict[str, Any]] = None,
    next_action: Optional[str] = None,
    next_stage: Optional[str] = None,
    transition_reason: Optional[str] = None,
    input_data: Optional[Dict[str, Any]] = None,
    execution: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Append one validated 2.0 event atomically. Failure is fail-closed."""
    effective_stage = stage if stage in ALLOWED_STAGES else "env"
    effective_status = status or ("succeeded" if outcome == "ok" else "failed")
    r_id = run_id or get_run_id()
    run_dir = get_run_dir(r_id)
    if (run_dir / "seal.json").exists():
        raise AuditLogError(f"Run {r_id} is sealed and cannot accept events")
    events_file = run_dir / "events.jsonl"
    if args_hash is None:
        args_hash = f"sha256:{hashlib.sha256(b'').hexdigest()}"
    parent = _SPAN_ID.get()
    trace_value = trace or {
        "trace_id": _TRACE_ID.get() or uuid.uuid4().hex,
        "span_id": uuid.uuid4().hex[:16],
        "parent_span_id": parent,
    }
    trace_value = {
        "trace_id": str(trace_value.get("trace_id") or _TRACE_ID.get() or uuid.uuid4().hex),
        "span_id": str(trace_value.get("span_id") or uuid.uuid4().hex[:16]),
        "parent_span_id": trace_value.get("parent_span_id", parent),
    }
    normalized_error: Optional[Dict[str, Any]]
    if isinstance(error, dict):
        normalized_error = redact(error)
    elif error:
        normalized_error = _error_dict(RuntimeError(str(error)))
    else:
        normalized_error = None

    try:
        with events_file.open("a+", encoding="utf-8") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                stream.seek(0)
                seq = sum(1 for line in stream if line.strip()) + 1
                event = {
                    "schema_version": SCHEMA_VERSION,
                    "run_id": r_id,
                    "seq": seq,
                    "ts": ts or utc_now(),
                    "agent": agent,
                    "video_id": str(video_id),
                    "clip_id": clip_id,
                    "stage": effective_stage,
                    "attempt": int(attempt),
                    "severity": severity,
                    "duration_ms": round(float(duration_ms), 2),
                    "tool": str(tool),
                    "cmd": redact(cmd),
                    "exit_code": int(exit_code),
                    "args_hash": args_hash,
                    "cost": {
                        "usd": float((cost or {}).get("usd", 0.0)),
                        "tokens_in": int((cost or {}).get("tokens_in", 0)),
                        "tokens_out": int((cost or {}).get("tokens_out", 0)),
                    },
                    "trace": trace_value,
                    "evidence": _normalize_evidence(evidence, run_dir),
                    "outcome": "fail" if effective_status in {"failed", "cancelled", "interrupted"} else "ok",
                    "error": normalized_error,
                    "claim": redact(claim),
                    "event_id": event_id or uuid.uuid4().hex,
                    "request_id": request_id or _REQUEST_ID.get(),
                    "component": component,
                    "action": action or f"{component}.{effective_stage}",
                    "status": effective_status,
                    "decision": redact(_json_safe(decision or {})),
                    "next": {
                        "action": next_action,
                        "stage": next_stage,
                        "reason": transition_reason or (
                            "action completed; no subsequent action"
                            if effective_status in TERMINAL_STATUSES and not next_action
                            else None
                        ),
                    },
                    "input": redact(_json_safe(input_data or {})),
                    "execution": redact(_json_safe(execution or {})),
                }
                validate_event_dict(event)
                stream.write(json.dumps(event, ensure_ascii=False, sort_keys=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                return event
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    except Exception as exc:
        try:
            sys.stderr.write(f"AUDIT_LOG_FAILURE run={r_id} action={action}: {redact(str(exc))}\n")
            sys.stderr.flush()
        finally:
            if isinstance(exc, AuditLogError):
                raise
            raise AuditLogError(f"Could not persist canonical audit event: {exc}") from exc


@dataclass
class ActionSpan:
    stage: str
    action: str
    component: str = "cortes"
    agent: str = "worker"
    video_id: str = "unknown"
    clip_id: Optional[str] = None
    attempt: int = 1
    next_action: Optional[str] = None
    next_stage: Optional[str] = None
    input_data: Dict[str, Any] = field(default_factory=dict)
    decision: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(
        default_factory=lambda: {"paths": [], "sha256": [], "bytes": []}
    )
    transition_reason: Optional[str] = None
    terminal_status: str = "succeeded"
    terminal_error: Optional[Dict[str, Any]] = None
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    started_at: float = 0.0

    def set_next(self, action: Optional[str], stage: Optional[str] = None, reason: Optional[str] = None) -> None:
        self.next_action = action
        self.next_stage = stage
        self.transition_reason = reason

    def set_evidence(self, paths: Sequence[Union[str, pathlib.Path]]) -> None:
        self.evidence = evidence_for(paths)

    def mark_failed(
        self,
        message: str,
        *,
        category: str = "application",
        retryable: bool = False,
        remediation: Optional[str] = None,
    ) -> None:
        self.terminal_status = "failed"
        self.terminal_error = _error_dict(
            RuntimeError(message),
            category=category,
            retryable=retryable,
            remediation=remediation,
        )
        if not self.transition_reason:
            self.transition_reason = "action returned an unsuccessful result"


@contextlib.contextmanager
def action_span(
    stage: str,
    action: str,
    *,
    component: str = "cortes",
    agent: str = "worker",
    video_id: str = "unknown",
    clip_id: Optional[str] = None,
    attempt: int = 1,
    next_action: Optional[str] = None,
    next_stage: Optional[str] = None,
    input_data: Optional[Dict[str, Any]] = None,
) -> Iterator[ActionSpan]:
    """Emit a started event and exactly one terminal event."""
    parent = _SPAN_ID.get()
    span = ActionSpan(
        stage=stage, action=action, component=component, agent=agent,
        video_id=video_id, clip_id=clip_id, attempt=attempt,
        next_action=next_action, next_stage=next_stage,
        input_data=input_data or {},
    )
    trace_id = _TRACE_ID.get() or uuid.uuid4().hex
    _TRACE_ID.set(trace_id)
    trace = {"trace_id": trace_id, "span_id": span.span_id, "parent_span_id": parent}
    arg_payload = json.dumps(redact(_json_safe(span.input_data)), sort_keys=True, ensure_ascii=False)
    args_hash = f"sha256:{hashlib.sha256(arg_payload.encode()).hexdigest()}"
    emit_event(
        stage=stage, agent=agent, video_id=video_id, clip_id=clip_id,
        attempt=attempt, status="started", component=component, action=action,
        input_data=span.input_data, args_hash=args_hash, trace=trace,
    )
    token = _SPAN_ID.set(span.span_id)
    span.started_at = time.perf_counter()
    try:
        yield span
    except BaseException as exc:
        duration = (time.perf_counter() - span.started_at) * 1000
        run_dir = get_run_dir()
        error_dir = run_dir / "errors"
        error_dir.mkdir(parents=True, exist_ok=True)
        traceback_file = error_dir / f"{span.span_id}.traceback.log"
        traceback_file.write_text(
            str(redact("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))),
            encoding="utf-8",
        )
        failure_evidence = {
            key: list(span.evidence.get(key, []))
            for key in ("paths", "sha256", "bytes")
        }
        trace_evidence = evidence_for([traceback_file])
        for key in ("paths", "sha256", "bytes"):
            failure_evidence[key].extend(trace_evidence[key])
        emit_event(
            stage=stage, agent=agent, video_id=video_id, clip_id=clip_id,
            attempt=attempt, severity="error", duration_ms=duration,
            status="failed", component=component, action=action,
            args_hash=args_hash, trace=trace, evidence=failure_evidence,
            error=_error_dict(
                exc,
                traceback_path=str(traceback_file.relative_to(run_dir)),
            ),
            decision=span.decision,
            transition_reason=span.transition_reason or "execution stopped because this action failed",
        )
        raise
    else:
        duration = (time.perf_counter() - span.started_at) * 1000
        emit_event(
            stage=stage, agent=agent, video_id=video_id, clip_id=clip_id,
            attempt=attempt,
            severity="error" if span.terminal_status == "failed" else "info",
            duration_ms=duration, status=span.terminal_status,
            component=component, action=action, args_hash=args_hash, trace=trace,
            evidence=span.evidence, decision=span.decision,
            next_action=span.next_action, next_stage=span.next_stage,
            transition_reason=span.transition_reason,
            error=span.terminal_error,
        )
    finally:
        _SPAN_ID.reset(token)


def emit_planned_actions(
    actions: Sequence[Dict[str, Any]], *, component: str = "pipeline", stage: str = "env"
) -> None:
    for index, item in enumerate(actions):
        emit_event(
            stage=str(item.get("stage", stage)),
            component=component,
            action=str(item["action"]),
            status="planned",
            next_action=(
                str(actions[index + 1]["action"]) if index + 1 < len(actions) else None
            ),
            next_stage=(
                str(actions[index + 1].get("stage", stage))
                if index + 1 < len(actions) else None
            ),
            transition_reason="declared in execution plan",
            input_data={"order": index + 1, "depends_on": item.get("depends_on")},
        )


def emit_skipped(
    stage: str, action: str, reason: str, *, component: str = "pipeline",
    next_action: Optional[str] = None, next_stage: Optional[str] = None
) -> None:
    emit_event(
        stage=stage, component=component, action=action, status="skipped",
        decision={"executed": False}, next_action=next_action, next_stage=next_stage,
        transition_reason=reason,
    )


def audited(
    stage: str,
    evidence_args: Optional[List[str]] = None,
    agent: str = "worker",
    video_id: str = "unknown",
    clip_id: Optional[str] = None,
    *,
    redact_args: Optional[List[str]] = None,
    action: Optional[str] = None,
    component: Optional[str] = None,
    next_action: Optional[str] = None,
    next_stage: Optional[str] = None,
) -> Callable:
    """Lifecycle decorator for observable Python boundaries."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            action_name = action or f"{func.__module__}.{func.__qualname__}"
            component_name = component or func.__module__
            redacted = set(redact_args or [])
            safe_input = {
                "args": [repr(arg) for arg in args],
                "kwargs": {
                    key: "<redacted>" if key in redacted else repr(value)
                    for key, value in kwargs.items()
                },
            }
            def invoke() -> Any:
                with action_span(
                    stage=stage,
                    action=action_name,
                    component=component_name,
                    agent=agent,
                    video_id=str(kwargs.get("video_id", video_id)),
                    clip_id=str(kwargs["clip_id"]) if kwargs.get("clip_id") is not None else clip_id,
                    next_action=next_action,
                    next_stage=next_stage,
                    input_data=safe_input,
                ) as span:
                    result = func(*args, **kwargs)
                    paths: List[Union[str, pathlib.Path]] = []
                    if isinstance(result, dict):
                        if isinstance(result.get("evidence_paths"), list):
                            paths.extend(result["evidence_paths"])
                        elif isinstance(result.get("evidence"), list):
                            paths.extend(result["evidence"])
                    elif isinstance(result, (str, pathlib.Path)):
                        path = pathlib.Path(result)
                        if path.exists() and path.is_file():
                            paths.append(path)
                    for arg_name in evidence_args or []:
                        value = kwargs.get(arg_name)
                        if isinstance(value, (str, pathlib.Path)):
                            paths.append(value)
                        elif isinstance(value, list):
                            paths.extend(value)
                    span.set_evidence(paths)
                    return result

            # Post-run operations (for example a verified report) must never
            # append to or write artifacts inside a sealed run. Audit them in a
            # fresh run while the function reads the sealed target.
            if (get_run_dir() / "seal.json").exists():
                with run_context(
                    actions=[{"action": action_name, "stage": stage}],
                    component=f"{component_name}.postrun",
                ):
                    return invoke()
            return invoke()
        return wrapper
    return decorator


def run_cmd(
    cmd: Union[List[str], str],
    cwd: Optional[str] = None,
    agent: str = "worker",
    stage: str = "env",
    attempt: int = 1,
    check: bool = False,
    env: Optional[Dict[str, str]] = None,
    video_id: str = "unknown",
    clip_id: Optional[str] = None,
    audit: bool = True,
    evidence: Optional[Dict[str, Any]] = None,
    evidence_paths: Optional[List[Union[str, pathlib.Path]]] = None,
    timeout: Optional[float] = None,
    action: Optional[str] = None,
    next_action: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Execute an external command and preserve lifecycle plus complete streams."""
    if isinstance(cmd, list):
        cmd_list = [str(item) for item in cmd]
        cmd_str = shlex.join(cmd_list)
    else:
        cmd_str = cmd
        cmd_list = shlex.split(cmd)
    safe_cmd = str(redact(cmd_str))
    tool_name = pathlib.Path(cmd_list[0]).name if cmd_list else "cmd"
    effective_stage = stage if stage in ALLOWED_STAGES else "env"
    actual_cwd = cwd or os.getcwd()

    if not audit:
        proc = subprocess.run(
            cmd_list if isinstance(cmd, list) else cmd,
            cwd=cwd, env=env, capture_output=True, text=True,
            shell=isinstance(cmd, str), timeout=timeout,
        )
        if check and proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)
        return proc

    run_dir = get_run_dir()
    command_dir = run_dir / "commands"
    command_dir.mkdir(parents=True, exist_ok=True)
    command_id = uuid.uuid4().hex[:12]
    stdout_path = command_dir / f"{command_id}.stdout.log"
    stderr_path = command_dir / f"{command_id}.stderr.log"
    action_name = action or f"command.{tool_name}"
    start = time.perf_counter()
    start_ts = utc_now()
    trace_id = _TRACE_ID.get() or uuid.uuid4().hex
    span_id = uuid.uuid4().hex[:16]
    trace = {"trace_id": trace_id, "span_id": span_id, "parent_span_id": _SPAN_ID.get()}
    cmd_hash = f"sha256:{hashlib.sha256(safe_cmd.encode()).hexdigest()}"
    emit_event(
        stage=effective_stage, agent=agent, video_id=video_id, clip_id=clip_id,
        attempt=attempt, tool=tool_name, cmd=safe_cmd, args_hash=cmd_hash,
        status="started", component="subprocess", action=action_name, trace=trace,
        input_data={"cwd": actual_cwd, "timeout_seconds": timeout},
    )
    try:
        proc = subprocess.run(
            cmd_list if isinstance(cmd, list) else cmd,
            cwd=cwd, env=env, capture_output=True, text=True,
            shell=isinstance(cmd, str), timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(str(redact(exc.stdout or "")), encoding="utf-8")
        stderr_path.write_text(str(redact(exc.stderr or "")), encoding="utf-8")
        duration = (time.perf_counter() - start) * 1000
        ev = evidence_for([stdout_path, stderr_path])
        emit_event(
            stage=effective_stage, agent=agent, video_id=video_id, clip_id=clip_id,
            attempt=attempt, severity="error", duration_ms=duration, tool=tool_name,
            cmd=safe_cmd, exit_code=124, args_hash=cmd_hash, status="failed",
            component="subprocess", action=action_name, trace=trace, evidence=ev,
            error=_error_dict(
                exc, category="timeout", retryable=True, exit_code=124,
                remediation="increase timeout or inspect command stderr",
                stderr_path=str(stderr_path.relative_to(run_dir)),
            ),
            transition_reason="command timed out; caller decides whether to retry",
        )
        raise

    stdout_path.write_text(str(redact(proc.stdout or "")), encoding="utf-8")
    stderr_path.write_text(str(redact(proc.stderr or "")), encoding="utf-8")
    duration = (time.perf_counter() - start) * 1000
    command_evidence = evidence_for([stdout_path, stderr_path])
    if evidence is None and evidence_paths:
        produced = evidence_for(evidence_paths)
        for key in ("paths", "sha256", "bytes"):
            command_evidence[key].extend(produced[key])
    elif evidence:
        for key in ("paths", "sha256", "bytes"):
            command_evidence[key].extend(evidence.get(key, []))
    error_value = None
    if proc.returncode != 0:
        signal_value = -proc.returncode if proc.returncode < 0 else None
        error_value = _error_dict(
            subprocess.CalledProcessError(proc.returncode, safe_cmd),
            category="subprocess", retryable=False, exit_code=proc.returncode,
            signal=signal_value, remediation="inspect the persisted stderr artifact",
            stderr_path=str(stderr_path.relative_to(run_dir)),
        )
    emit_event(
        stage=effective_stage, agent=agent, video_id=video_id, clip_id=clip_id,
        attempt=attempt, severity="info" if proc.returncode == 0 else "error",
        duration_ms=duration, tool=tool_name, cmd=safe_cmd, exit_code=proc.returncode,
        args_hash=cmd_hash, status="succeeded" if proc.returncode == 0 else "failed",
        component="subprocess", action=action_name, trace=trace,
        evidence=command_evidence, error=error_value, next_action=next_action,
        transition_reason=(
            "command completed; control returns to caller"
            if proc.returncode == 0 else "command failed; caller decides fallback or abort"
        ),
        execution={
            "cwd": actual_cwd,
            "started_at": start_ts,
            "stdout_path": str(stdout_path.relative_to(run_dir)),
            "stderr_path": str(stderr_path.relative_to(run_dir)),
        },
    )
    commands_log = run_dir / "commands.log"
    with commands_log.open("a", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            stream.write(
                f"[{start_ts}] id={command_id} tool={tool_name} exit={proc.returncode} "
                f"duration_ms={duration:.2f} cwd={actual_cwd}\n"
                f"command={safe_cmd}\nstdout={stdout_path.relative_to(run_dir)} "
                f"stderr={stderr_path.relative_to(run_dir)}\n"
            )
            stream.flush()
            os.fsync(stream.fileno())
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)
    return proc


def seal_run(run_id: Optional[str] = None, status: str = "completed") -> pathlib.Path:
    """Seal a completed/failed run with a digest; interrupted runs stay unsealed."""
    run_dir = get_run_dir(run_id)
    events_file = run_dir / "events.jsonl"
    seal_path = run_dir / "seal.json"
    if seal_path.exists():
        return seal_path
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_dir.name,
        "status": status,
        "sealed_at": utc_now(),
        "events_sha256": compute_sha256(events_file) if events_file.exists() else None,
        "event_count": (
            sum(1 for line in events_file.read_text(encoding="utf-8").splitlines() if line.strip())
            if events_file.exists() else 0
        ),
    }
    temp_path = run_dir / ".seal.json.tmp"
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp_path, seal_path)
    return seal_path


def reconcile_planned_actions(
    run_id: Optional[str] = None, *, reason: str = "run ended before the action started"
) -> List[str]:
    """Append ``skipped`` for every planned action without a terminal event."""
    run_dir = get_run_dir(run_id)
    events_file = run_dir / "events.jsonl"
    if not events_file.exists():
        return []
    events: List[Dict[str, Any]] = []
    for line in events_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    planned: Dict[str, Dict[str, Any]] = {}
    terminal = set()
    for event in events:
        action = event.get("action")
        if not action:
            continue
        if event.get("status") == "planned":
            planned.setdefault(action, event)
        elif event.get("status") in TERMINAL_STATUSES:
            terminal.add(action)
    skipped: List[str] = []
    for action, event in planned.items():
        if action in terminal:
            continue
        emit_skipped(
            event.get("stage", "env"),
            action,
            reason,
            component=event.get("component", "pipeline"),
        )
        skipped.append(action)
    return skipped


@contextlib.contextmanager
def run_context(
    *,
    run_id: Optional[str] = None,
    request_id: Optional[str] = None,
    actions: Optional[Sequence[Dict[str, Any]]] = None,
    component: str = "pipeline",
    seal: bool = True,
) -> Iterator[str]:
    """Create an isolated run context. A hard process kill intentionally leaves it open."""
    chosen = run_id or f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"
    run_token = _RUN_ID.set(chosen)
    trace_token = _TRACE_ID.set(uuid.uuid4().hex)
    request_token = _REQUEST_ID.set(request_id)
    span_token = _SPAN_ID.set(None)
    try:
        if actions:
            emit_planned_actions(actions, component=component)
        yield chosen
    except BaseException as exc:
        reconcile_planned_actions(
            chosen,
            reason=f"run aborted because {type(exc).__name__}: {redact(str(exc))}",
        )
        if seal:
            seal_run(chosen, status="failed")
        raise
    else:
        reconcile_planned_actions(chosen)
        if seal:
            seal_run(chosen, status="completed")
    finally:
        _SPAN_ID.reset(span_token)
        _REQUEST_ID.reset(request_token)
        _TRACE_ID.reset(trace_token)
        _RUN_ID.reset(run_token)
