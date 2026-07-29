"""Module cortes/report.py - Deterministic Markdown Report Generator."""

import json
import pathlib
import sys
from typing import Any, Callable, Dict, List, Optional, Union

from cortes.log import audited, get_run_dir


@audited(stage="report")
def generate_report(
    run_dir: Union[str, pathlib.Path],
    verify_result_path: Optional[Union[str, pathlib.Path]] = None,
    force: bool = False,
) -> pathlib.Path:
    """Generate report.md exclusively from events.jsonl and verify_result.json."""
    r_path = pathlib.Path(run_dir).resolve()
    run_id = r_path.name
    events_file = r_path / "events.jsonl"

    # Resolve verify_result.json location
    verify_file = None
    if verify_result_path:
        v_candidate = pathlib.Path(verify_result_path).resolve()
        if v_candidate.exists():
            verify_file = v_candidate
    if not verify_file or not verify_file.exists():
        if (r_path / "verify_result.json").exists():
            verify_file = r_path / "verify_result.json"
        elif (r_path.parent / "verify_result.json").exists():
            verify_file = r_path.parent / "verify_result.json"

    if verify_file and (r_path / "seal.json").exists():
        report_file = verify_file.parent / f"{run_id}_report_verified.md"
    else:
        report_file = r_path / (
            "report_verified.md" if verify_result_path else "report.md"
        )

    if report_file.exists() and not force and not verify_file:
        return report_file

    events: List[Dict[str, Any]] = []
    if events_file.exists():
        for line in events_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass

    verify_data: Dict[str, Any] = {}
    is_verified = False
    if verify_file and verify_file.exists():
        try:
            verify_data = json.loads(verify_file.read_text(encoding="utf-8"))
            is_verified = True
        except Exception:
            pass

    overall_passed = verify_data.get("overall_passed", False)
    verified_at = verify_data.get("verified_at", "N/A")
    total_checks = verify_data.get("total_checks", 0)
    passed_checks = verify_data.get("passed_checks", 0)
    checks = verify_data.get("checks", [])

    ts_first = events[0]["ts"] if events else "N/A"
    ts_last = events[-1]["ts"] if events else "N/A"
    video_id = events[0].get("video_id", "unknown") if events else "unknown"
    clip_id = next(
        (event.get("clip_id") for event in events if event.get("clip_id")),
        None,
    )
    agent = events[0].get("agent", "worker") if events else "worker"
    total_events = len(events)
    total_duration_ms = sum(float(ev.get("duration_ms", 0.0)) for ev in events)
    status_counts: Dict[str, int] = {}
    for event in events:
        status = event.get("status") or (
            "succeeded" if event.get("outcome") == "ok" else "failed"
        )
        status_counts[status] = status_counts.get(status, 0) + 1
    started_actions = {
        event.get("action")
        for event in events
        if event.get("status") == "started" and event.get("action")
    }
    terminal_actions = {
        event.get("action")
        for event in events
        if event.get("status") in {"succeeded", "failed", "skipped", "cancelled", "interrupted"}
        and event.get("action")
    }
    interrupted_actions = sorted(started_actions - terminal_actions)

    verdict_str = "PASSED" if (is_verified and overall_passed) else ("FAILED" if is_verified else "UNVERIFIED")

    lines: List[str] = [
        f"# Execution & Verification Report — Run `{run_id}`",
        "",
        f"**Generated At**: `{verified_at}`  ",
        f"**Verification Verdict**: `{verdict_str}`",
        "",
        "---",
        "",
        "## 1. Run Metadata Summary",
        "",
        "| Attribute | Value |",
        "|---|---|",
        f"| **Run ID** | `{run_id}` |",
        f"| **Video ID** | `{video_id}` |",
        f"| **Clip ID** | `{clip_id or 'null'}` |",
        f"| **Agent** | `{agent}` |",
        f"| **Start Time (UTC)** | `{ts_first}` |",
        f"| **End Time (UTC)** | `{ts_last}` |",
        f"| **Total Events** | `{total_events}` |",
        f"| **Total Duration (ms)** | `{total_duration_ms:.2f}` |",
        f"| **Lifecycle Status Counts** | `{json.dumps(status_counts, sort_keys=True)}` |",
        f"| **Started Without Terminal** | `{len(interrupted_actions)}` |",
        "",
        "---",
        "",
        "## 2. Stage Execution Log (`events.jsonl`)",
        "",
        "| Seq | Stage | Action | Status | Attempt | Next Action | Reason / Error | Duration (ms) |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for ev in events:
        action = str(ev.get("action") or ev.get("tool") or "legacy.event")
        status = ev.get("status") or ("succeeded" if ev.get("outcome") == "ok" else "failed")
        next_value = ev.get("next") or {}
        next_action = next_value.get("action") or "END"
        error_value = ev.get("error")
        if isinstance(error_value, dict):
            reason = error_value.get("message") or next_value.get("reason") or ""
        else:
            reason = error_value or next_value.get("reason") or ""
        reason = str(reason).replace("|", "\\|").replace("\n", " ")[:120]
        lines.append(
            f"| {ev.get('seq')} | {ev.get('stage')} | `{action}` | {status} | "
            f"{ev.get('attempt')} | `{next_action}` | {reason} | {ev.get('duration_ms')} |"
        )

    lines.extend([
        "",
        "### Interrupted or Incomplete Actions",
        "",
    ])
    if interrupted_actions:
        lines.extend(f"- `{action}`: started without a terminal event" for action in interrupted_actions)
    else:
        lines.append("- None detected.")

    lines.extend([
        "",
        "---",
        "",
        "## 3. Verification Check Results (`verify_result.json`)",
        "",
        "| Check ID | Status | Measured | Expected | Evidence Path |",
        "|---|---|---|---|---|",
    ])

    if checks:
        for chk in checks:
            status = "PASS" if chk.get("passed") else "FAIL"
            lines.append(
                f"| `{chk.get('check_id')}` | {status} | {chk.get('measured')} | {chk.get('expected')} | `{chk.get('evidence_path')}` |"
            )
    else:
        lines.append("| N/A | UNVERIFIED | N/A | N/A | N/A |")

    lines.extend([
        "",
        "---",
        "",
        "## 4. Produced Artifacts & Cryptographic Signatures",
        "",
        "| Stage | Path | Bytes | SHA-256 Hash |",
        "|---|---|---|---|",
    ])

    artifacts_seen = set()
    for ev in events:
        stage = ev.get("stage", "unknown")
        evidence = ev.get("evidence", {})
        paths = evidence.get("paths", [])
        sha256s = evidence.get("sha256", [])
        bytes_list = evidence.get("bytes", [])
        for idx, p in enumerate(paths):
            if p not in artifacts_seen:
                artifacts_seen.add(p)
                b = bytes_list[idx] if idx < len(bytes_list) else "N/A"
                s = sha256s[idx] if idx < len(sha256s) else "N/A"
                lines.append(f"| {stage} | `{p}` | {b} | `{s}` |")

    lines.extend([
        "",
        "---",
        "",
        "## 5. Executed Subprocess Commands (`commands.log`)",
        "",
        "```bash",
    ])

    cmd_entries = [ev.get("cmd") for ev in events if ev.get("cmd")]
    if cmd_entries:
        for c in cmd_entries:
            lines.append(c)
    else:
        lines.append("# No external subprocess commands executed")

    lines.extend([
        "```",
        "",
        "---",
        "",
        "## 6. Final Integrity Verdict",
        "",
        f"- **Overall Status**: `{verdict_str}`",
        f"- **Total Checks Passed**: `{passed_checks}/{total_checks}`",
        "",
    ])

    report_content = "\n".join(lines)
    report_file.write_text(report_content, encoding="utf-8")

    return report_file


@audited(stage="report")
def run_report(
    run_dir_or_action: Optional[Union[str, pathlib.Path, Callable[..., Any]]] = None,
    *args: Any,
    run_id: Optional[str] = None,
    verify_result_path: Optional[Union[str, pathlib.Path]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Audited entrypoint for Stage 9 (report). Supports action callback or stage execution."""
    if callable(run_dir_or_action):
        return run_dir_or_action(*args, **kwargs)

    target_dir = run_dir_or_action or get_run_dir(run_id)
    report_path = generate_report(
        run_dir=target_dir,
        verify_result_path=verify_result_path,
    )
    return {
        "status": "ok",
        "report_path": str(report_path),
        "evidence_paths": [str(report_path)],
    }


@audited(stage="report")
def main() -> None:
    """CLI entrypoint for report generation."""
    import argparse

    parser = argparse.ArgumentParser(description="Deterministic Markdown Report Generator")
    parser.add_argument("run_dir_pos", nargs="?", help="Run directory (positional)")
    parser.add_argument("--run-dir", dest="run_dir_flag", help="Run directory (--run-dir flag)")

    args = parser.parse_args()
    run_dir = args.run_dir_flag or args.run_dir_pos
    if not run_dir:
        parser.error("run_dir is required")

    report_path = generate_report(run_dir, force=True)
    sys.stdout.write(report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
