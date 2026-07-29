"""Contract tests for lifecycle audit schema 2.0."""

from __future__ import annotations

import json
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from cortes.log import (
    action_span,
    emit_event,
    run_cmd,
    run_context,
    validate_event_dict,
)
from cortes.verify import verify_run


def _events(run_dir: pathlib.Path):
    return [
        json.loads(line)
        for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_action_span_emits_started_and_terminal_with_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with run_context(
        run_id="run_lifecycle",
        actions=[{"action": "test.produce", "stage": "ingest"}],
    ):
        artifact = pathlib.Path("runs/run_lifecycle/artifacts/result.txt")
        artifact.parent.mkdir(parents=True)
        with action_span("ingest", "test.produce") as span:
            artifact.write_text("result", encoding="utf-8")
            span.set_evidence([artifact])
            span.set_next("test.consume", "select", "producer completed")

    events = _events(tmp_path / "runs/run_lifecycle")
    statuses = [event["status"] for event in events if event["action"] == "test.produce"]
    assert statuses == ["planned", "started", "succeeded"]
    completed = next(event for event in events if event["status"] == "succeeded")
    assert completed["evidence"]["paths"] == ["artifacts/result.txt"]
    assert completed["next"]["action"] == "test.consume"
    assert (tmp_path / "runs/run_lifecycle/seal.json").exists()


def test_run_context_reconciles_actions_that_never_started(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError):
        with run_context(
            run_id="run_reconcile",
            actions=[
                {"action": "test.fail", "stage": "env"},
                {"action": "test.never", "stage": "render"},
            ],
        ):
            with action_span("env", "test.fail"):
                raise RuntimeError("boom")

    events = _events(tmp_path / "runs/run_reconcile")
    skipped = [
        event for event in events
        if event["action"] == "test.never" and event["status"] == "skipped"
    ]
    failed = next(
        event for event in events
        if event["action"] == "test.fail" and event["status"] == "failed"
    )
    assert failed["error"]["type"] == "RuntimeError"
    assert failed["error"]["failure_point"]
    assert (
        tmp_path / "runs/run_reconcile" / failed["error"]["traceback_path"]
    ).exists()
    assert len(skipped) == 1
    assert "run aborted" in skipped[0]["next"]["reason"]
    assert json.loads(
        (tmp_path / "runs/run_reconcile/seal.json").read_text(encoding="utf-8")
    )["status"] == "failed"


def test_redaction_applies_to_command_and_stream_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    secret = "super-secret-value"
    with run_context(run_id="run_redaction"):
        run_cmd(
            [
                sys.executable,
                "-c",
                "import sys; print(sys.argv[1])",
                f"authorization=Bearer {secret}",
            ],
            stage="env",
        )

    run_dir = tmp_path / "runs/run_redaction"
    persisted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [run_dir / "events.jsonl", run_dir / "commands.log", *sorted((run_dir / "commands").glob("*"))]
    )
    assert secret not in persisted
    assert "[REDACTED]" in persisted


def test_contextvars_isolate_concurrent_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def worker(index: int):
        run_id = f"run_thread_{index}"
        with run_context(run_id=run_id):
            emit_event(
                stage="env",
                action="thread.event",
                status="succeeded",
                transition_reason="thread completed",
            )
        return run_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        run_ids = list(pool.map(worker, range(16)))

    for run_id in run_ids:
        events = _events(tmp_path / "runs" / run_id)
        assert {event["run_id"] for event in events} == {run_id}
        assert [event["seq"] for event in events] == list(range(1, len(events) + 1))


def test_unsealed_started_action_is_detected_as_interrupted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from cortes.log import set_run_id

    set_run_id("run_interrupted")
    emit_event(
        stage="render",
        action="render.never_finished",
        status="planned",
        transition_reason="declared in execution plan",
    )
    emit_event(
        stage="render",
        action="render.never_finished",
        status="started",
    )

    result = verify_run(tmp_path / "runs/run_interrupted")
    checks = {check["check_id"]: check for check in result["checks"]}
    assert not checks["lifecycle_complete"]["passed"]
    assert not checks["run_sealed"]["passed"]


def test_validate_event_dict_accepts_legacy_schema():
    empty_hash = "sha256:" + ("0" * 64)
    event = {
        "schema_version": "1.0.0",
        "run_id": "legacy",
        "seq": 1,
        "ts": "2026-01-01T00:00:00+00:00",
        "agent": "worker",
        "video_id": "unknown",
        "clip_id": None,
        "stage": "env",
        "attempt": 1,
        "severity": "info",
        "duration_ms": 0,
        "tool": "python",
        "cmd": None,
        "exit_code": 0,
        "args_hash": empty_hash,
        "cost": {"usd": 0.0, "tokens_in": 0, "tokens_out": 0},
        "trace": {"span_id": "legacy-span", "parent_span_id": None},
        "evidence": {"paths": [], "sha256": [], "bytes": []},
        "outcome": "ok",
        "error": None,
        "claim": None,
    }
    validate_event_dict(event)
