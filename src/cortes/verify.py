"""
Module cortes/verify.py - Zero-Trust Re-measurement and Verification.
"""

import hashlib
import json
import os
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Union

from cortes.log import compute_sha256, run_cmd


def measure_sha256(file_path: pathlib.Path) -> str:
    """Compute sha256 of file from scratch."""
    return compute_sha256(file_path)


def run_ffprobe_json(file_path: pathlib.Path) -> Dict[str, Any]:
    """Run ffprobe on file and return parsed JSON metadata."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(file_path),
    ]
    res = run_cmd(cmd, stage="verify")
    if res.returncode != 0:
        return {}
    try:
        return json.loads(res.stdout)
    except Exception:
        return {}


def measure_audio_loudness_lufs(file_path: pathlib.Path) -> float:
    """Measure integrated LUFS using pyloudnorm if available, else ffmpeg ebur128 filter."""
    try:
        import pyloudnorm as pyln
        import soundfile as sf

        temp_wav = file_path.parent / f"_temp_loudness_{file_path.stem}.wav"
        try:
            res = run_cmd(
                [
                    "ffmpeg",
                    "-y",
                    "-nostdin",
                    "-v",
                    "error",
                    "-i",
                    str(file_path),
                    "-vn",
                    "-ac",
                    "2",
                    "-ar",
                    "48000",
                    str(temp_wav),
                ],
                stage="verify",
            )
            if res.returncode == 0 and temp_wav.exists():
                data, rate = sf.read(str(temp_wav))
                meter = pyln.Meter(rate)
                loudness = float(meter.integrated_loudness(data))
                return round(loudness, 2)
        finally:
            if temp_wav.exists():
                try:
                    temp_wav.unlink()
                except Exception:
                    pass
    except Exception:
        pass

    # Fallback to ffmpeg ebur128 filter (without -v error so summary is output)
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-nostats",
        "-hide_banner",
        "-i",
        str(file_path),
        "-filter_complex",
        "ebur128=peak=true",
        "-f",
        "null",
        "-",
    ]
    res = run_cmd(cmd, stage="verify")
    stderr = res.stderr
    for line in stderr.splitlines():
        line_str = line.strip()
        if line_str.startswith("I:") and "LUFS" in line_str:
            parts = line_str.split()
            if len(parts) >= 2:
                try:
                    return float(parts[1])
                except ValueError:
                    pass
    return -999.0


def verify_run(run_dir: Union[str, pathlib.Path]) -> Dict[str, Any]:
    """Perform zero-trust verification on a run directory and generate verify_result.json."""
    r_path = pathlib.Path(run_dir).resolve()
    run_id = r_path.name
    verified_at = datetime.now(timezone.utc).isoformat()

    checks: List[Dict[str, Any]] = []

    def add_check(check_id: str, passed: bool, measured: Any, expected: Any, evidence_path: str) -> None:
        checks.append(
            {
                "check_id": check_id,
                "passed": bool(passed),
                "measured": str(measured),
                "expected": str(expected),
                "evidence_path": str(evidence_path),
            }
        )

    # 1. Check events_file_exists
    events_file = r_path / "events.jsonl"
    events_exists = events_file.exists()
    add_check(
        check_id="events_file_exists",
        passed=events_exists,
        measured="File exists" if events_exists else "File missing",
        expected="File exists",
        evidence_path=str(events_file),
    )

    events: List[Dict[str, Any]] = []
    events_valid_schema = True
    schema_error_msg = "All events valid"

    if events_exists:
        lines = [l for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not lines:
            events_valid_schema = False
            schema_error_msg = "events.jsonl is empty"
        else:
            for idx, line in enumerate(lines, start=1):
                try:
                    ev = json.loads(line)
                    from cortes.log import validate_event_dict

                    validate_event_dict(ev)
                    events.append(ev)
                except Exception as ex:
                    events_valid_schema = False
                    schema_error_msg = f"Line {idx} invalid: {ex}"
                    break

        add_check(
            check_id="events_schema_valid",
            passed=events_valid_schema,
            measured=schema_error_msg if not events_valid_schema else f"Validated {len(events)} events",
            expected="Schema Version 1.0.0 valid",
            evidence_path=str(events_file),
        )

        # 2. Check seq_integrity
        seq_passed = True
        seq_msg = "seq 1..N continuous without gaps"
        if events_valid_schema and events:
            for i, ev in enumerate(events):
                expected_seq = i + 1
                if ev.get("seq") != expected_seq:
                    seq_passed = False
                    seq_msg = f"Mismatch at index {i}: expected seq {expected_seq}, found {ev.get('seq')}"
                    break
        else:
            seq_passed = False
            seq_msg = "Events schema invalid or empty"

        add_check(
            check_id="seq_integrity",
            passed=seq_passed,
            measured=seq_msg,
            expected="seq == index + 1 without gaps or duplicates",
            evidence_path=str(events_file),
        )

        # 3. Check ts_monotonic
        ts_passed = True
        ts_msg = "Timestamps non-decreasing"
        if events_valid_schema and events:
            prev_ts = ""
            for i, ev in enumerate(events):
                curr_ts = ev.get("ts", "")
                if curr_ts < prev_ts:
                    ts_passed = False
                    ts_msg = f"Timestamp decreased at seq {ev.get('seq')}: {curr_ts} < {prev_ts}"
                    break
                prev_ts = curr_ts

        add_check(
            check_id="ts_monotonic",
            passed=ts_passed,
            measured=ts_msg,
            expected="Monotonic non-decreasing ISO timestamps",
            evidence_path=str(events_file),
        )

        # 4. Check commands_log_sync
        commands_file = r_path / "commands.log"
        commands_passed = True
        cmd_msg = "Commands log in sync"
        if commands_file.exists():
            cmd_content = commands_file.read_text(encoding="utf-8")
            for ev in events:
                if ev.get("cmd"):
                    cmd_line = f"COMMAND: {ev['cmd']}"
                    if cmd_line not in cmd_content:
                        commands_passed = False
                        cmd_msg = f"Command '{ev['cmd']}' missing from commands.log"
                        break
        else:
            has_cmd_events = any(ev.get("cmd") for ev in events)
            if has_cmd_events:
                commands_passed = False
                cmd_msg = "commands.log missing while events contain commands"

        add_check(
            check_id="commands_log_sync",
            passed=commands_passed,
            measured=cmd_msg,
            expected="All event commands present in commands.log",
            evidence_path=str(commands_file if commands_file.exists() else events_file),
        )

        # 5. Check exit_codes_zero
        exit_passed = True
        exit_msg = "All ok events have exit_code 0"
        for ev in events:
            if ev.get("outcome") == "ok" and ev.get("exit_code") != 0:
                exit_passed = False
                exit_msg = f"Event seq {ev.get('seq')} outcome ok but exit_code {ev.get('exit_code')}"
                break

        add_check(
            check_id="exit_codes_zero",
            passed=exit_passed,
            measured=exit_msg,
            expected="exit_code == 0 for all outcome ok events",
            evidence_path=str(events_file),
        )

        # 6. Check producer_evidence_required
        producer_stages = {"ingest", "transcribe", "cut", "subtitles", "audio", "transform", "render"}
        prod_ev_passed = True
        prod_ev_msg = "All producer ok events have evidence paths"
        for ev in events:
            if ev.get("stage") in producer_stages and ev.get("outcome") == "ok":
                ev_paths = ev.get("evidence", {}).get("paths", [])
                if not ev_paths:
                    prod_ev_passed = False
                    prod_ev_msg = (
                        f"Producer stage '{ev.get('stage')}' at seq {ev.get('seq')} has no evidence paths"
                    )
                    break

        add_check(
            check_id="producer_evidence_required",
            passed=prod_ev_passed,
            measured=prod_ev_msg,
            expected="Producer stages with outcome ok must declare non-empty evidence paths",
            evidence_path=str(events_file),
        )

        # 7. Check artifact_exists, artifact_sha256, artifact_bytes
        artifacts_checked = 0
        all_exists = True
        all_hashes = True
        all_bytes = True
        exists_fail_msg = "All declared evidence artifacts exist"
        hash_fail_msg = "All SHA-256 hashes match"
        bytes_fail_msg = "All byte sizes match"

        for ev in events:
            if ev.get("outcome") == "ok":
                evidence = ev.get("evidence", {})
                paths = evidence.get("paths", [])
                sha256s = evidence.get("sha256", [])
                bytes_list = evidence.get("bytes", [])

                for idx, p_str in enumerate(paths):
                    artifacts_checked += 1
                    p_obj = pathlib.Path(p_str)
                    if not p_obj.exists():
                        all_exists = False
                        exists_fail_msg = f"Artifact {p_str} does not exist"
                        all_hashes = False
                        hash_fail_msg = f"Artifact {p_str} missing for hash check"
                        all_bytes = False
                        bytes_fail_msg = f"Artifact {p_str} missing for byte check"
                        continue

                    # Check bytes
                    real_size = p_obj.stat().st_size
                    decl_size = bytes_list[idx] if idx < len(bytes_list) else -1
                    if real_size != decl_size:
                        all_bytes = False
                        bytes_fail_msg = f"Size mismatch for {p_str}: measured {real_size}, expected {decl_size}"

                    # Check sha256
                    real_sha = measure_sha256(p_obj)
                    decl_sha = sha256s[idx] if idx < len(sha256s) else ""
                    if real_sha != decl_sha:
                        all_hashes = False
                        hash_fail_msg = f"SHA256 mismatch for {p_str}: measured {real_sha}, expected {decl_sha}"

        add_check(
            check_id="artifact_exists",
            passed=all_exists,
            measured=exists_fail_msg,
            expected="All evidence files exist on disk",
            evidence_path=str(events_file),
        )

        add_check(
            check_id="artifact_sha256",
            passed=all_hashes,
            measured=hash_fail_msg,
            expected="Calculated SHA-256 matches declared hash",
            evidence_path=str(events_file),
        )

        add_check(
            check_id="artifact_bytes",
            passed=all_bytes,
            measured=bytes_fail_msg,
            expected="Disk byte size matches declared size",
            evidence_path=str(events_file),
        )

        # 8. Media Artifact Checks (find any render/clip/short mp4 files)
        media_files = list(r_path.rglob("*.mp4"))
        for video_file in media_files:
            info = run_ffprobe_json(video_file)
            streams = info.get("streams", [])
            video_streams = [s for s in streams if s.get("codec_type") == "video"]
            audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
            format_info = info.get("format", {})

            # Resolution check
            res_passed = False
            res_measured = "No video stream"
            if video_streams:
                w = video_streams[0].get("width")
                h = video_streams[0].get("height")
                res_measured = f"{w}x{h}"
                if w == 1080 and h == 1920:
                    res_passed = True

            add_check(
                check_id="video_resolution",
                passed=res_passed,
                measured=res_measured,
                expected="1080x1920",
                evidence_path=str(
                    video_file.relative_to(r_path.parent) if r_path.parent in video_file.parents else video_file
                ),
            )

            # Audio stream count check
            add_check(
                check_id="audio_stream_count",
                passed=len(audio_streams) == 1,
                measured=f"{len(audio_streams)} audio stream(s)",
                expected="Exactly 1 audio stream",
                evidence_path=str(video_file),
            )

            # Video duration check
            duration = float(format_info.get("duration", 0.0))
            if duration == 0.0 and video_streams:
                duration = float(video_streams[0].get("duration", 0.0))
            dur_passed = 20.0 <= duration <= 58.0
            add_check(
                check_id="video_duration_range",
                passed=dur_passed,
                measured=f"{round(duration, 2)} seconds",
                expected="20.0 <= duration <= 58.0 seconds",
                evidence_path=str(video_file),
            )

            # Audio LUFS Loudness check
            loudness = measure_audio_loudness_lufs(video_file)
            lufs_passed = -16.0 <= loudness <= -13.0
            add_check(
                check_id="audio_lufs_loudness",
                passed=lufs_passed,
                measured=f"{loudness:.2f} LUFS",
                expected="[-16.0 LUFS, -13.0 LUFS]",
                evidence_path=str(video_file),
            )

    passed_count = sum(1 for c in checks if c["passed"])
    total_count = len(checks)
    failed_count = total_count - passed_count
    overall_passed = failed_count == 0

    result = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "verified_at": verified_at,
        "overall_passed": overall_passed,
        "total_checks": total_count,
        "passed_checks": passed_count,
        "failed_checks": failed_count,
        "checks": checks,
    }

    verify_result_file = r_path / "verify_result.json"
    verify_result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 -m cortes.verify <run_dir>")
        sys.exit(1)
    run_dir = sys.argv[1]
    res = verify_run(run_dir)
    print(json.dumps(res, indent=2))
    sys.exit(0 if res["overall_passed"] else 1)


if __name__ == "__main__":
    main()
