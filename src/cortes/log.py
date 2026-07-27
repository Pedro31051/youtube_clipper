"""
Module cuts/log.py - Audit logging, event emission, and subprocess execution.
"""

import fcntl
import functools
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

# Fixed Event Schema Version 1.0.0 allowed stages
ALLOWED_STAGES = {
    "env",
    "ingest",
    "transcribe",
    "scenes",
    "select",
    "cut",
    "subtitles",
    "audio",
    "transform",
    "render",
    "verify",
    "report",
}

_CURRENT_RUN_ID: Optional[str] = None


def set_run_id(run_id: str) -> None:
    """Set global active run_id."""
    global _CURRENT_RUN_ID
    _CURRENT_RUN_ID = run_id


def get_run_id() -> str:
    """Get active run_id or initialize default."""
    global _CURRENT_RUN_ID
    if _CURRENT_RUN_ID:
        return _CURRENT_RUN_ID
    env_run_id = os.environ.get("CORTES_RUN_ID")
    if env_run_id:
        _CURRENT_RUN_ID = env_run_id
        return env_run_id
    _CURRENT_RUN_ID = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    return _CURRENT_RUN_ID


def get_run_dir(run_id: Optional[str] = None) -> pathlib.Path:
    """Return path to runs/<run_id> directory, creating it if needed."""
    r_id = run_id or get_run_id()
    run_dir = pathlib.Path("runs") / r_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def compute_sha256(file_path: Union[str, pathlib.Path]) -> str:
    """Compute sha256:HEX hash of a file."""
    path = pathlib.Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Cannot compute hash: file '{file_path}' does not exist.")
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def validate_event_dict(event: Dict[str, Any]) -> None:
    """Validate that an event dictionary conforms strictly to Event Schema 1.0.0."""
    required_fields = [
        "schema_version",
        "run_id",
        "seq",
        "ts",
        "agent",
        "video_id",
        "clip_id",
        "stage",
        "attempt",
        "severity",
        "duration_ms",
        "tool",
        "cmd",
        "exit_code",
        "args_hash",
        "cost",
        "trace",
        "evidence",
        "outcome",
        "error",
        "claim",
    ]
    if len(event) != len(required_fields):
        missing = [f for f in required_fields if f not in event]
        extra = [f for f in event if f not in required_fields]
        raise ValueError(
            f"Event schema violation: expected exactly 21 fields. Missing: {missing}, Extra: {extra}"
        )

    for field in required_fields:
        if field not in event:
            raise ValueError(f"Event schema violation: missing required field '{field}'")

    if event["schema_version"] != "1.0.0":
        raise ValueError(f"Invalid schema_version: expected '1.0.0', got {event['schema_version']}")

    if not isinstance(event["seq"], int) or event["seq"] < 1:
        raise ValueError(f"Invalid seq: must be integer >= 1, got {event['seq']}")

    if event["stage"] not in ALLOWED_STAGES:
        raise ValueError(f"Invalid stage '{event['stage']}': must be one of {ALLOWED_STAGES}")

    if event["severity"] not in {"info", "warn", "error"}:
        raise ValueError(f"Invalid severity '{event['severity']}'")

    if event["outcome"] not in {"ok", "fail"}:
        raise ValueError(f"Invalid outcome '{event['outcome']}'")

    args_hash = event["args_hash"]
    if not isinstance(args_hash, str) or not args_hash.startswith("sha256:") or len(args_hash) != 71:
        raise ValueError(f"Invalid args_hash format: '{args_hash}'")

    evidence = event["evidence"]
    if not isinstance(evidence, dict) or set(evidence.keys()) != {"paths", "sha256", "bytes"}:
        raise ValueError("Invalid evidence object: must contain paths, sha256, and bytes arrays.")

    p_len = len(evidence["paths"])
    if len(evidence["sha256"]) != p_len or len(evidence["bytes"]) != p_len:
        raise ValueError("Invalid evidence lengths: paths, sha256, and bytes lists must have equal lengths.")


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
    error: Optional[str] = None,
    claim: Optional[str] = None,
    run_id: Optional[str] = None,
    ts: Optional[str] = None,
) -> Dict[str, Any]:
    """Emit an audit event to runs/<run_id>/events.jsonl with file locking and strict seq increment."""
    if stage not in ALLOWED_STAGES:
        # Fallback/default mapping to "env" if unexpected stage passed
        stage = "env"

    r_id = run_id or get_run_id()
    run_dir = get_run_dir(r_id)
    events_file = run_dir / "events.jsonl"

    if ts is None:
        ts = datetime.now(timezone.utc).isoformat()

    if args_hash is None:
        empty_hash = hashlib.sha256(b"").hexdigest()
        args_hash = f"sha256:{empty_hash}"

    if cost is None:
        cost = {"usd": 0.0, "tokens_in": 0, "tokens_out": 0}

    if trace is None:
        trace = {"span_id": uuid.uuid4().hex[:16], "parent_span_id": None}

    if evidence is None:
        evidence = {"paths": [], "sha256": [], "bytes": []}

    # Open events file with exclusive file lock to determine seq and append
    with open(events_file, "a+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.seek(0)
            lines = f.read().splitlines()
            seq = len([l for l in lines if l.strip()]) + 1

            event_dict = {
                "schema_version": "1.0.0",
                "run_id": r_id,
                "seq": seq,
                "ts": ts,
                "agent": agent,
                "video_id": video_id,
                "clip_id": clip_id,
                "stage": stage,
                "attempt": attempt,
                "severity": severity,
                "duration_ms": round(float(duration_ms), 2),
                "tool": tool,
                "cmd": cmd,
                "exit_code": int(exit_code),
                "args_hash": args_hash,
                "cost": {
                    "usd": float(cost.get("usd", 0.0)),
                    "tokens_in": int(cost.get("tokens_in", 0)),
                    "tokens_out": int(cost.get("tokens_out", 0)),
                },
                "trace": {
                    "span_id": str(trace.get("span_id", "")),
                    "parent_span_id": trace.get("parent_span_id"),
                },
                "evidence": {
                    "paths": [],
                    "sha256": [str(h) for h in evidence.get("sha256", [])],
                    "bytes": [int(b) for b in evidence.get("bytes", [])],
                },
                "outcome": outcome,
                "error": error,
                "claim": claim,
            }

            run_root = run_dir.resolve()
            for raw_path in evidence.get("paths", []):
                resolved = pathlib.Path(raw_path).resolve()
                try:
                    relative = resolved.relative_to(run_root)
                except ValueError as exc:
                    raise ValueError(
                        f"Evidence path must be inside its run directory: {resolved}"
                    ) from exc
                event_dict["evidence"]["paths"].append(str(relative))

            validate_event_dict(event_dict)

            f.write(json.dumps(event_dict, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
            return event_dict
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def audited(
    stage: str,
    evidence_args: Optional[List[str]] = None,
    agent: str = "worker",
    video_id: str = "unknown",
    clip_id: Optional[str] = None,
) -> Callable:
    """Decorator to measure duration, compute args_hash & evidence hashes, and emit event."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.perf_counter()
            start_ts = datetime.now(timezone.utc).isoformat()
            span_id = uuid.uuid4().hex[:16]

            # Calculate deterministic args_hash
            arg_str = repr((args, sorted([(k, v) for k, v in kwargs.items()])))
            args_hash = f"sha256:{hashlib.sha256(arg_str.encode('utf-8')).hexdigest()}"

            outcome = "ok"
            severity = "info"
            error_msg = None
            result = None

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                outcome = "fail"
                severity = "error"
                error_msg = f"{type(e).__name__}: {str(e)}"
                raise e
            finally:
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

                ev_paths: List[str] = []
                ev_hashes: List[str] = []
                ev_bytes: List[int] = []

                # Extract potential evidence paths from result or kwargs
                paths_to_check: List[Union[str, pathlib.Path]] = []

                if isinstance(result, dict):
                    if "evidence_paths" in result:
                        paths_to_check.extend(result["evidence_paths"])
                    elif "evidence" in result and isinstance(result["evidence"], list):
                        paths_to_check.extend(result["evidence"])

                if evidence_args:
                    for arg_name in evidence_args:
                        if arg_name in kwargs:
                            val = kwargs[arg_name]
                            if isinstance(val, (str, pathlib.Path)):
                                paths_to_check.append(val)
                            elif isinstance(val, list):
                                paths_to_check.extend(val)

                for p_item in paths_to_check:
                    p_obj = pathlib.Path(p_item)
                    if p_obj.exists() and p_obj.is_file():
                        p_str = str(p_obj)
                        if p_str not in ev_paths:
                            ev_paths.append(p_str)
                            ev_hashes.append(compute_sha256(p_obj))
                            ev_bytes.append(p_obj.stat().st_size)

                emit_event(
                    stage=stage,
                    agent=agent,
                    video_id=video_id,
                    clip_id=clip_id,
                    severity=severity,
                    duration_ms=duration_ms,
                    tool="python",
                    cmd=None,
                    exit_code=0,
                    args_hash=args_hash,
                    trace={"span_id": span_id, "parent_span_id": None},
                    evidence={"paths": ev_paths, "sha256": ev_hashes, "bytes": ev_bytes},
                    outcome=outcome,
                    error=error_msg,
                    ts=start_ts,
                )

        return wrapper

    return decorator


def run_cmd(
    cmd: Union[List[str], str],
    cwd: Optional[str] = None,
    agent: str = "worker",
    stage: str = "cmd",
    check: bool = False,
    env: Optional[Dict[str, str]] = None,
    video_id: str = "unknown",
    clip_id: Optional[str] = None,
    audit: bool = True,
) -> subprocess.CompletedProcess:
    """Sole authorized function in the repository for invoking external subprocesses.

    ``audit=False`` is reserved for read-only verification.  It executes through
    this controlled boundary without creating a new run or mutating the run that
    is being inspected.
    """
    if isinstance(cmd, list):
        cmd_list = cmd
        cmd_str = " ".join(cmd)
    else:
        cmd_str = cmd
        cmd_list = shlex.split(cmd)

    tool_name = pathlib.Path(cmd_list[0]).name if cmd_list else "cmd"

    effective_stage = stage if stage in ALLOWED_STAGES else "env"

    start_time = time.perf_counter()
    start_ts = datetime.now(timezone.utc).isoformat()
    actual_cwd = cwd or os.getcwd()

    proc = subprocess.run(
        cmd_list if isinstance(cmd, list) else cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        shell=isinstance(cmd, str),
    )

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    if not audit:
        if check and proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode, cmd, proc.stdout, proc.stderr
            )
        return proc

    # Append to commands.log with locking
    run_dir = get_run_dir()
    commands_log_file = run_dir / "commands.log"
    with open(commands_log_file, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            log_entry = (
                f"================================================================================\n"
                f"[{start_ts}] [AGENT: {agent}] [CWD: {actual_cwd}] [EXIT: {proc.returncode}] [DURATION: {duration_ms}ms]\n"
                f"COMMAND: {cmd_str}\n"
                f"--- STDOUT ---\n"
                f"{proc.stdout}\n"
                f"--- STDERR ---\n"
                f"{proc.stderr}\n"
                f"================================================================================\n"
            )
            f.write(log_entry)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    outcome = "ok" if proc.returncode == 0 else "fail"
    severity = "info" if proc.returncode == 0 else "error"
    error_msg = None if proc.returncode == 0 else f"Process returned exit code {proc.returncode}"

    cmd_hash = f"sha256:{hashlib.sha256(cmd_str.encode('utf-8')).hexdigest()}"

    emit_event(
        stage=effective_stage,
        agent=agent,
        video_id=video_id,
        clip_id=clip_id,
        severity=severity,
        duration_ms=duration_ms,
        tool=tool_name,
        cmd=cmd_str,
        exit_code=proc.returncode,
        args_hash=cmd_hash,
        outcome=outcome,
        error=error_msg,
        ts=start_ts,
    )

    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)

    return proc
