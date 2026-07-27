"""Captura append-only de comandos e evidências da auditoria T0."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = RUN_DIR / "evidencias"
COMMANDS_FILE = RUN_DIR / "COMANDOS.jsonl"
SEQ_FILE = RUN_DIR / "scratch" / ".seq_state"
REPO = RUN_DIR.parents[3]


def next_seq() -> int:
    SEQ_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SEQ_FILE.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        current = int(handle.read().strip() or "0")
        handle.seek(0)
        handle.truncate()
        handle.write(str(current + 1))
        handle.flush()
        os.fsync(handle.fileno())
        return current + 1


def evidence_paths(slot: str) -> tuple[Path, Path, str, str]:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    attempt = 1
    while True:
        suffix = "" if attempt == 1 else f".att{attempt}"
        out_rel = f"evidencias/{slot}{suffix}.txt"
        err_rel = f"evidencias/{slot}{suffix}.stderr.txt"
        out_path = RUN_DIR / out_rel
        err_path = RUN_DIR / err_rel
        if not out_path.exists() and not err_path.exists():
            return out_path, err_path, out_rel, err_rel
        attempt += 1


def main() -> int:
    args = sys.argv[1:]
    cwd = REPO
    if args[:1] == ["--cwd"]:
        cwd = Path(args[1]).resolve()
        args = args[2:]
    if len(args) < 2:
        raise SystemExit("uso: runner.py [--cwd DIR] SLOT COMANDO [ARGS...]")

    slot, command = args[0], args[1:]
    seq = next_seq()
    out_path, err_path, out_rel, err_rel = evidence_paths(slot)
    started = time.monotonic()
    timestamp = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        errors="replace",
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    out_path.write_text(result.stdout or "", encoding="utf-8")
    err_path.write_text(result.stderr or "", encoding="utf-8")

    record = {
        "seq": seq,
        "cmd_uid": f"{RUN_DIR.name}#{seq:04d}",
        "ts_utc": timestamp,
        "cwd": str(cwd),
        "cmd": " ".join(command),
        "exit_code": result.returncode,
        "stdout_path": out_rel,
        "stderr_path": err_rel,
        "duration_ms": duration_ms,
    }
    with COMMANDS_FILE.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())

    print(
        f"seq={seq} exit={result.returncode} duration_ms={duration_ms} "
        f"stdout={out_rel} stderr={err_rel}"
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
