"""
Module cortes/report.py - Deterministic Markdown Report Generator.
"""

import json
import pathlib
import sys
from typing import Any, Dict, List, Union


def generate_report(run_dir: Union[str, pathlib.Path]) -> pathlib.Path:
    """Generate report.md exclusively from events.jsonl and verify_result.json."""
    r_path = pathlib.Path(run_dir).resolve()
    run_id = r_path.name
    report_file = r_path / "report.md"

    events_file = r_path / "events.jsonl"
    verify_file = r_path / "verify_result.json"

    events: List[Dict[str, Any]] = []
    if events_file.exists():
        for line in events_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass

    verify_data: Dict[str, Any] = {}
    if verify_file.exists():
        try:
            verify_data = json.loads(verify_file.read_text(encoding="utf-8"))
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
    clip_id = events[0].get("clip_id") if events else None
    agent = events[0].get("agent", "worker") if events else "worker"
    total_events = len(events)
    total_duration_ms = sum(float(ev.get("duration_ms", 0.0)) for ev in events)

    lines: List[str] = [
        f"# Execution & Verification Report — Run `{run_id}`",
        "",
        f"**Generated At**: `{verified_at}`  ",
        f"**Verification Verdict**: `{'PASSED' if overall_passed else 'FAILED'}`",
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
        "",
        "---",
        "",
        "## 2. Stage Execution Log (`events.jsonl`)",
        "",
        "| Seq | Stage | Attempt | Tool / Command | Exit Code | Outcome | Duration (ms) |",
        "|---|---|---|---|---|---|---|",
    ]

    for ev in events:
        cmd_disp = ev.get("cmd") or ev.get("tool") or "N/A"
        if len(cmd_disp) > 60:
            cmd_disp = cmd_disp[:57] + "..."
        lines.append(
            f"| {ev.get('seq')} | {ev.get('stage')} | {ev.get('attempt')} | `{cmd_disp}` | {ev.get('exit_code')} | {ev.get('outcome')} | {ev.get('duration_ms')} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Verification Check Results (`verify_result.json`)",
        "",
        "| Check ID | Status | Measured | Expected | Evidence Path |",
        "|---|---|---|---|---|",
    ])

    for chk in checks:
        status = "PASS" if chk.get("passed") else "FAIL"
        lines.append(
            f"| `{chk.get('check_id')}` | {status} | {chk.get('measured')} | {chk.get('expected')} | `{chk.get('evidence_path')}` |"
        )

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
        f"- **Overall Status**: `{'PASSED' if overall_passed else 'FAILED'}`",
        f"- **Total Checks Passed**: `{passed_checks}/{total_checks}`",
        "",
    ])

    report_content = "\n".join(lines)
    report_file.write_text(report_content, encoding="utf-8")
    return report_file


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 -m cortes.report <run_dir>")
        sys.exit(1)
    run_dir = sys.argv[1]
    res_path = generate_report(run_dir)
    print(f"Report generated at {res_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
