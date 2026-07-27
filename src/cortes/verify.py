"""
Module cortes/verify.py - Zero-Trust Re-measurement and Verification.
"""

import json
import pathlib
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Union

from cortes.editorial import build_clip_id, validate_template_variant
from cortes.log import compute_sha256, run_cmd


STAGE_ORDER = {
    "env": 0,
    "ingest": 1,
    "transcribe": 2,
    "scenes": 3,
    "select": 4,
    "cut": 5,
    "subtitles": 6,
    "audio": 7,
    "transform": 8,
    "render": 9,
    "verify": 10,
    "report": 11,
}


def parse_iso_ts(ts_str: str) -> datetime:
    """Parse ISO 8601 string to timezone-aware datetime object, handling 'Z' suffix."""
    if not ts_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    s = ts_str.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


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
    res = run_cmd(cmd, stage="verify", audit=False)
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

        with tempfile.TemporaryDirectory(prefix="cortes_verify_") as temp_dir:
            temp_wav = pathlib.Path(temp_dir) / "loudness.wav"
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
                audit=False,
            )
            if res.returncode == 0 and temp_wav.exists():
                data, rate = sf.read(str(temp_wav))
                meter = pyln.Meter(rate)
                loudness = float(meter.integrated_loudness(data))
                return round(loudness, 2)
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
    res = run_cmd(cmd, stage="verify", audit=False)
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


def _resolve_evidence_path(raw_path: str, run_path: pathlib.Path) -> pathlib.Path:
    """Resolve portable run-relative evidence, including legacy absolute paths."""
    candidate = pathlib.Path(raw_path)
    if not candidate.is_absolute():
        resolved = (run_path / candidate).resolve()
        try:
            resolved.relative_to(run_path.resolve())
        except ValueError as exc:
            raise ValueError(f"Evidence path escapes the supplied run: {raw_path}") from exc
        return resolved

    # Legacy T0 runs embedded host-specific prefixes before ``artifacts/``.
    # Resolve the stable suffix inside the supplied run instead of reaching
    # back into the producer machine.
    if "artifacts" in candidate.parts:
        artifact_index = candidate.parts.index("artifacts")
        resolved = (
            run_path / pathlib.Path(*candidate.parts[artifact_index:])
        ).resolve()
        try:
            resolved.relative_to(run_path.resolve())
        except ValueError as exc:
            raise ValueError(f"Evidence path escapes the supplied run: {raw_path}") from exc
        return resolved
    raise ValueError(f"Absolute evidence path has no portable artifacts suffix: {raw_path}")


def _relative_evidence_path(path: pathlib.Path, run_path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(run_path.resolve()))
    except ValueError:
        return str(path.resolve())


def _parse_rate(raw_rate: Any) -> float:
    """Parse ffprobe frame-rate fields such as ``30000/1001``."""
    value = str(raw_rate or "0")
    try:
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            denominator_f = float(denominator)
            return float(numerator) / denominator_f if denominator_f else 0.0
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def verify_run(
    run_dir: Union[str, pathlib.Path],
    output_path: Union[str, pathlib.Path, None] = None,
) -> Dict[str, Any]:
    """Perform read-only zero-trust verification on a run directory.

    Results are returned in memory.  A JSON file is written only when the
    caller explicitly supplies ``output_path``.
    """
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
        evidence_path=_relative_evidence_path(events_file, r_path),
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
            evidence_path=_relative_evidence_path(events_file, r_path),
        )

        # 2. Check seq_integrity
        seq_passed = True
        seq_msg = "seq 1..N continuous without gaps and stage DAG sequence valid"
        if events_valid_schema and events:
            prev_stage_rank = -1
            for i, ev in enumerate(events):
                expected_seq = i + 1
                if ev.get("seq") != expected_seq:
                    seq_passed = False
                    seq_msg = f"Mismatch at index {i}: expected seq {expected_seq}, found {ev.get('seq')}"
                    break
                stage_name = ev.get("stage")
                stage_rank = STAGE_ORDER.get(stage_name, 999)
                if stage_rank < prev_stage_rank:
                    seq_passed = False
                    seq_msg = f"Invalid stage DAG sequence at seq {ev.get('seq')}: stage '{stage_name}' occurred after higher rank stage"
                    break
                prev_stage_rank = stage_rank
        else:
            seq_passed = False
            seq_msg = "Events schema invalid or empty"

        add_check(
            check_id="seq_integrity",
            passed=seq_passed,
            measured=seq_msg,
            expected="seq == index + 1 without gaps or duplicates and stage DAG sequence valid",
            evidence_path=_relative_evidence_path(events_file, r_path),
        )

        # 3. Check ts_monotonic
        ts_passed = True
        ts_msg = "Timestamps non-decreasing"
        if events_valid_schema and events:
            prev_dt = None
            prev_ts_str = ""
            for ev in events:
                curr_ts_str = ev.get("ts", "")
                try:
                    curr_dt = parse_iso_ts(curr_ts_str)
                    if prev_dt is not None and curr_dt < prev_dt:
                        ts_passed = False
                        ts_msg = f"Timestamp decreased at seq {ev.get('seq')}: {curr_ts_str} < {prev_ts_str}"
                        break
                    prev_dt = curr_dt
                    prev_ts_str = curr_ts_str
                except Exception as ex:
                    ts_passed = False
                    ts_msg = f"Invalid timestamp format at seq {ev.get('seq')}: {curr_ts_str} ({ex})"
                    break

        add_check(
            check_id="ts_monotonic",
            passed=ts_passed,
            measured=ts_msg,
            expected="Monotonic non-decreasing ISO timestamps",
            evidence_path=_relative_evidence_path(events_file, r_path),
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
            evidence_path=_relative_evidence_path(
                commands_file if commands_file.exists() else events_file, r_path
            ),
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
            evidence_path=_relative_evidence_path(events_file, r_path),
        )

        # All current evidence must be portable and relative to the run root.
        relative_paths_passed = True
        relative_paths_msg = "All evidence paths are run-relative"
        for ev in events:
            for raw_path in ev.get("evidence", {}).get("paths", []):
                path_obj = pathlib.Path(raw_path)
                if path_obj.is_absolute() or ".." in path_obj.parts:
                    relative_paths_passed = False
                    relative_paths_msg = (
                        f"Non-portable evidence path at seq {ev.get('seq')}: {raw_path}"
                    )
                    break
            if not relative_paths_passed:
                break
        add_check(
            check_id="evidence_paths_relative",
            passed=relative_paths_passed,
            measured=relative_paths_msg,
            expected="Every evidence path is relative and confined to the run",
            evidence_path=_relative_evidence_path(events_file, r_path),
        )

        # 6. Check producer_evidence_required
        producer_stages = {
            "ingest",
            "transcribe",
            "cut",
            "subtitles",
            "audio",
            "render",
        }
        prod_ev_passed = True
        prod_ev_msg = "Every executed producer stage has at least one completion event with evidence"
        executed_producers = {
            ev.get("stage")
            for ev in events
            if ev.get("stage") in producer_stages and ev.get("outcome") == "ok"
        }
        for producer_stage in sorted(executed_producers):
            if not any(
                ev.get("stage") == producer_stage
                and ev.get("outcome") == "ok"
                and ev.get("evidence", {}).get("paths")
                for ev in events
            ):
                prod_ev_passed = False
                prod_ev_msg = (
                    f"Producer stage '{producer_stage}' has no completion event with evidence"
                )
                break

        add_check(
            check_id="producer_evidence_required",
            passed=prod_ev_passed,
            measured=prod_ev_msg,
            expected="Producer stages with outcome ok must declare non-empty evidence paths",
            evidence_path=_relative_evidence_path(events_file, r_path),
        )

        # 7. Check artifact_exists, artifact_sha256, artifact_bytes
        artifacts_checked = 0
        all_exists = True
        all_hashes = True
        all_bytes = True
        exists_fail_msg = "All declared evidence artifacts exist"
        hash_fail_msg = "All SHA-256 hashes match"
        bytes_fail_msg = "All byte sizes match"
        declared_media_files: List[pathlib.Path] = []
        render_stage_media_files: List[pathlib.Path] = []
        intermediate_media_files: List[pathlib.Path] = []

        for ev in events:
            if ev.get("outcome") == "ok":
                stg = ev.get("stage")
                evidence = ev.get("evidence", {})
                paths = evidence.get("paths", [])
                sha256s = evidence.get("sha256", [])
                bytes_list = evidence.get("bytes", [])

                for idx, p_str in enumerate(paths):
                    artifacts_checked += 1
                    try:
                        p_obj = _resolve_evidence_path(p_str, r_path)
                    except ValueError as exc:
                        all_exists = False
                        all_hashes = False
                        all_bytes = False
                        exists_fail_msg = str(exc)
                        hash_fail_msg = str(exc)
                        bytes_fail_msg = str(exc)
                        continue

                    if p_obj.suffix.lower() == ".mp4":
                        declared_media_files.append(p_obj)
                        rel_str = _relative_evidence_path(p_obj, r_path)
                        if stg in ("render", "transform") or rel_str.startswith("artifacts/render/") or p_obj.name == "short.mp4":
                            if p_obj not in render_stage_media_files:
                                render_stage_media_files.append(p_obj)
                        else:
                            if p_obj not in intermediate_media_files:
                                intermediate_media_files.append(p_obj)

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
            passed=artifacts_checked > 0 and all_exists,
            measured=(
                exists_fail_msg
                if artifacts_checked > 0
                else "No evidence artifacts were declared"
            ),
            expected="All evidence files exist on disk",
            evidence_path=_relative_evidence_path(events_file, r_path),
        )

        add_check(
            check_id="artifact_sha256",
            passed=artifacts_checked > 0 and all_hashes,
            measured=(
                hash_fail_msg
                if artifacts_checked > 0
                else "No evidence artifacts were declared"
            ),
            expected="Calculated SHA-256 matches declared hash",
            evidence_path=_relative_evidence_path(events_file, r_path),
        )

        add_check(
            check_id="artifact_bytes",
            passed=artifacts_checked > 0 and all_bytes,
            measured=(
                bytes_fail_msg
                if artifacts_checked > 0
                else "No evidence artifacts were declared"
            ),
            expected="Disk byte size matches declared size",
            evidence_path=_relative_evidence_path(events_file, r_path),
        )

        # 8. Intermediate Media Artifact Checks (existence, size > 1024 bytes, probed duration > 0.0s)
        for media_file in sorted(set(intermediate_media_files)):
            if not media_file.exists():
                continue
            subject = _relative_evidence_path(media_file, r_path)
            info = run_ffprobe_json(media_file)
            format_info = info.get("format", {})
            duration = float(format_info.get("duration", 0.0))
            if duration == 0.0 and info.get("streams"):
                v_streams = [s for s in info["streams"] if s.get("codec_type") == "video"]
                if v_streams:
                    duration = float(v_streams[0].get("duration", 0.0))
            st_size = media_file.stat().st_size
            add_check(
                check_id=f"intermediate_media_valid::{subject}",
                passed=st_size > 1024 and duration > 0.0,
                measured=f"size={st_size} bytes, duration={round(duration, 2)}s",
                expected="size > 1024 bytes and duration > 0.0s",
                evidence_path=subject,
            )

        # 9. Final Rendered Short Media Checks (1080x1920, 1 audio stream, 20-58s duration, LUFS [-16, -13])
        target_render_files = sorted({p for p in render_stage_media_files if p.exists()})
        t2_artifacts_present = any(
            (r_path / "artifacts" / stage).exists()
            for stage in ("select", "cut", "subtitles", "audio")
        )
        add_check(
            check_id="final_render_required",
            passed=bool(target_render_files) or not t2_artifacts_present,
            measured=(
                f"{len(target_render_files)} final render(s) found"
                if target_render_files
                else "No final render declared"
            ),
            expected="At least one declared short.mp4 for a T2 run",
            evidence_path="artifacts",
        )
        for video_file in target_render_files:
            subject = _relative_evidence_path(video_file, r_path)
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
                check_id=f"video_resolution::{subject}",
                passed=res_passed,
                measured=res_measured,
                expected="1080x1920",
                evidence_path=subject,
            )

            # Constant-frame-rate proof.  FFmpeg writes identical nominal and
            # average rates for CFR output; a zero or divergent rate is rejected.
            if video_streams:
                nominal_fps = _parse_rate(video_streams[0].get("r_frame_rate"))
                average_fps = _parse_rate(video_streams[0].get("avg_frame_rate"))
            else:
                nominal_fps = average_fps = 0.0
            fps_passed = (
                nominal_fps > 0.0
                and average_fps > 0.0
                and abs(nominal_fps - average_fps) <= 0.001
            )
            add_check(
                check_id=f"video_constant_fps::{subject}",
                passed=fps_passed,
                measured=(
                    f"r_frame_rate={nominal_fps:.6f}, "
                    f"avg_frame_rate={average_fps:.6f}"
                ),
                expected="Positive constant FPS (r_frame_rate == avg_frame_rate)",
                evidence_path=subject,
            )

            # Audio stream count check
            add_check(
                check_id=f"audio_stream_count::{subject}",
                passed=len(audio_streams) == 1,
                measured=f"{len(audio_streams)} audio stream(s)",
                expected="Exactly 1 audio stream",
                evidence_path=subject,
            )

            # Video duration check
            duration = float(format_info.get("duration", 0.0))
            if duration == 0.0 and video_streams:
                duration = float(video_streams[0].get("duration", 0.0))
            dur_passed = 20.0 <= duration <= 58.0
            add_check(
                check_id=f"video_duration_range::{subject}",
                passed=dur_passed,
                measured=f"{round(duration, 2)} seconds",
                expected="20.0 <= duration <= 58.0 seconds",
                evidence_path=subject,
            )

            # Audio LUFS Loudness check
            loudness = measure_audio_loudness_lufs(video_file)
            lufs_passed = -16.0 <= loudness <= -13.0
            add_check(
                check_id=f"audio_lufs_loudness::{subject}",
                passed=lufs_passed,
                measured=f"{loudness:.2f} LUFS",
                expected="[-16.0 LUFS, -13.0 LUFS]",
                evidence_path=subject,
            )

            # T3 editorial transformation proof is derived from physical
            # artifacts, the audited FFmpeg command, and immutable metadata.
            render_metadata_path = video_file.parent / "render_metadata.json"
            if render_metadata_path.exists():
                try:
                    render_metadata = json.loads(
                        render_metadata_path.read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError) as exc:
                    render_metadata = {}
                    metadata_valid = False
                    metadata_msg = f"Invalid render metadata: {exc}"
                else:
                    metadata_valid = isinstance(render_metadata, dict)
                    metadata_msg = (
                        "Render metadata is valid JSON"
                        if metadata_valid
                        else "Render metadata must be an object"
                    )

                is_t3 = bool(
                    render_metadata.get("phase") == "T3"
                    or render_metadata.get("editorial_transformation_required")
                )
                if is_t3:
                    metadata_subject = _relative_evidence_path(
                        render_metadata_path, r_path
                    )
                    add_check(
                        check_id=f"editorial_metadata::{subject}",
                        passed=metadata_valid,
                        measured=metadata_msg,
                        expected="Valid T3 render_metadata.json",
                        evidence_path=metadata_subject,
                    )

                    render_commands = [
                        str(ev.get("cmd") or "")
                        for ev in events
                        if ev.get("stage") == "render" and ev.get("cmd")
                    ]
                    requirements = render_metadata.get(
                        "editorial_requirements", []
                    )
                    if not isinstance(requirements, list):
                        requirements = []
                    requirements = [str(item) for item in requirements]

                    narration_passed = False
                    narration_msg = "Narration is not required"
                    narration_evidence = metadata_subject
                    if (
                        "narration" in requirements
                        or render_metadata.get("narration_required")
                        or render_metadata.get("narration_mixed")
                    ):
                        raw_narration_path = str(
                            render_metadata.get("narration_source_path") or ""
                        )
                        try:
                            narration_file = _resolve_evidence_path(
                                raw_narration_path, r_path
                            )
                        except ValueError as exc:
                            narration_msg = str(exc)
                        else:
                            narration_evidence = _relative_evidence_path(
                                narration_file, r_path
                            )
                            narration_is_file = (
                                narration_file.exists()
                                and narration_file.is_file()
                            )
                            narration_info = (
                                run_ffprobe_json(narration_file)
                                if narration_is_file
                                else {}
                            )
                            narration_duration = float(
                                narration_info.get("format", {}).get(
                                    "duration", 0.0
                                )
                                or 0.0
                            )
                            expected_hash = render_metadata.get(
                                "narration_source_sha256"
                            )
                            expected_bytes = render_metadata.get(
                                "narration_source_bytes"
                            )
                            real_hash = (
                                measure_sha256(narration_file)
                                if narration_is_file
                                else None
                            )
                            real_bytes = (
                                narration_file.stat().st_size
                                if narration_is_file
                                else None
                            )
                            command_proves_mix = any(
                                "amix=inputs=2" in command
                                and narration_file.name in command
                                for command in render_commands
                            )
                            narration_passed = bool(
                                render_metadata.get("narration_mixed")
                                and narration_is_file
                                and narration_duration >= 8.0
                                and expected_hash == real_hash
                                and expected_bytes == real_bytes
                                and command_proves_mix
                            )
                            narration_msg = (
                                f"exists={narration_is_file}, "
                                f"duration={narration_duration:.3f}s, "
                                f"hash_match={expected_hash == real_hash}, "
                                f"bytes_match={expected_bytes == real_bytes}, "
                                f"amix_proven={command_proves_mix}"
                            )
                        add_check(
                            check_id=f"editorial_narration::{subject}",
                            passed=narration_passed,
                            measured=narration_msg,
                            expected=(
                                "Physical narration >= 8.0s with matching hash/bytes "
                                "and audited amix command"
                            ),
                            evidence_path=narration_evidence,
                        )

                    overlay_passed = False
                    overlay_msg = "Analytical overlay is not required"
                    if (
                        "analytical_overlay" in requirements
                        or render_metadata.get("analytical_overlay")
                    ):
                        overlay_text = str(
                            render_metadata.get("overlay_text") or ""
                        ).strip()
                        overlay_command_proof = any(
                            "drawbox=" in command
                            and "drawtext=" in command
                            and overlay_text
                            in command.replace("\\:", ":").replace("\\'", "'")
                            for command in render_commands
                        )
                        overlay_passed = bool(
                            render_metadata.get("analytical_overlay")
                            and overlay_text
                            and overlay_command_proof
                        )
                        overlay_msg = (
                            f"metadata_enabled={bool(render_metadata.get('analytical_overlay'))}, "
                            f"text_present={bool(overlay_text)}, "
                            f"command_proven={overlay_command_proof}"
                        )
                        add_check(
                            check_id=f"editorial_overlay::{subject}",
                            passed=overlay_passed,
                            measured=overlay_msg,
                            expected="Non-empty analytical overlay burned by drawbox/drawtext",
                            evidence_path=metadata_subject,
                        )

                    requirement_results = {
                        "narration": narration_passed,
                        "analytical_overlay": overlay_passed,
                    }
                    supported_requirements = set(requirement_results)
                    declared_requirements = set(requirements)
                    transformation_passed = bool(declared_requirements) and (
                        declared_requirements <= supported_requirements
                    ) and all(
                        requirement_results[item]
                        for item in declared_requirements
                    )
                    add_check(
                        check_id=f"editorial_transformation::{subject}",
                        passed=transformation_passed,
                        measured=(
                            f"requirements={sorted(declared_requirements)}, "
                            f"results={requirement_results}"
                        ),
                        expected="Every declared T3 editorial requirement is physically proven",
                        evidence_path=metadata_subject,
                    )

                    variant = str(
                        render_metadata.get("template_variant") or ""
                    ).strip()
                    history = render_metadata.get(
                        "template_variant_history", []
                    )
                    history_valid = isinstance(history, list) and len(history) <= 5
                    recent_variants = (
                        [
                            str(item.get("template_variant") or "").strip()
                            for item in history
                            if isinstance(item, dict)
                        ]
                        if isinstance(history, list)
                        else []
                    )
                    try:
                        normalized_variant = validate_template_variant(variant)
                    except Exception as exc:
                        variant_valid = False
                        variant_msg = str(exc)
                    else:
                        variant_valid = (
                            history_valid
                            and normalized_variant not in recent_variants
                        )
                        variant_msg = (
                            f"variant={normalized_variant}, "
                            f"previous_five={recent_variants}"
                        )
                    add_check(
                        check_id=f"template_variant_unique::{subject}",
                        passed=variant_valid,
                        measured=variant_msg,
                        expected="Non-default variant absent from previous five renders",
                        evidence_path=metadata_subject,
                    )

                    selection_artifact_path = (
                        r_path / "artifacts" / "select" / "selection.json"
                    )
                    if (
                        selection_artifact_path.exists()
                        and render_metadata.get("clip_id")
                        and variant_valid
                    ):
                        expected_clip_id = build_clip_id(
                            selection_artifact_path.read_bytes(), variant
                        )
                        declared_clip_id = str(render_metadata.get("clip_id"))
                        add_check(
                            check_id=f"clip_id_binds_variant::{subject}",
                            passed=declared_clip_id == expected_clip_id,
                            measured=(
                                f"declared={declared_clip_id}, "
                                f"recomputed={expected_clip_id}"
                            ),
                            expected="clip_id = SHA256(selection + template_variant)",
                            evidence_path=metadata_subject,
                        )

        # 10. Selection bounds are re-measured against source/cut metadata.
        selection_path = r_path / "artifacts" / "select" / "selection.json"
        cut_metadata_path = r_path / "artifacts" / "cut" / "cut_metadata.json"
        ingest_metadata_path = r_path / "artifacts" / "ingest" / "metadata.json"
        if selection_path.exists():
            try:
                selection_data = json.loads(selection_path.read_text(encoding="utf-8"))
                selection_start = int(selection_data["start_ms"])
                selection_end = int(selection_data["end_ms"])
                source_duration_ms = 0
                if ingest_metadata_path.exists():
                    ingest_metadata = json.loads(
                        ingest_metadata_path.read_text(encoding="utf-8")
                    )
                    source_duration_ms = int(
                        round(float(ingest_metadata.get("duration", 0.0)) * 1000)
                    )
                if source_duration_ms <= 0 and cut_metadata_path.exists():
                    cut_metadata = json.loads(
                        cut_metadata_path.read_text(encoding="utf-8")
                    )
                    source_duration_ms = int(cut_metadata.get("source_duration_ms", 0))
                selection_passed = (
                    source_duration_ms > 0
                    and 0 <= selection_start < selection_end <= source_duration_ms
                )
                selection_measured = (
                    f"start_ms={selection_start}, end_ms={selection_end}, "
                    f"source_duration_ms={source_duration_ms}"
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                selection_passed = False
                selection_measured = f"Invalid selection metadata: {exc}"
            add_check(
                check_id="selection_within_source_bounds",
                passed=selection_passed,
                measured=selection_measured,
                expected="0 <= start_ms < end_ms <= source_duration_ms",
                evidence_path=_relative_evidence_path(selection_path, r_path),
            )

        # 11. Re-read the physical ASS and map every event to a transcript word.
        mapping_path = r_path / "artifacts" / "subtitles" / "subtitle_mapping.json"
        ass_path = r_path / "artifacts" / "subtitles" / "subtitles.ass"
        if mapping_path.exists() or ass_path.exists():
            alignment_passed = True
            alignment_msg = "All ASS events map to transcript words within +/-200 ms"
            try:
                import pysubs2

                mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
                selection = mapping["selection"]
                clip_start_ms = int(selection["start_ms"])
                clip_end_ms = int(selection["end_ms"])
                clip_duration_ms = clip_end_ms - clip_start_ms
                source_words = mapping.get("source_words", [])
                normalized_words = []
                for word in source_words:
                    word_start = int(
                        word.get(
                            "start_ms",
                            round(float(word.get("start", 0.0)) * 1000),
                        )
                    )
                    word_end = int(
                        word.get(
                            "end_ms",
                            round(float(word.get("end", 0.0)) * 1000),
                        )
                    )
                    normalized_words.append(
                        (
                            str(word.get("word", "")).strip().casefold(),
                            word_start,
                            word_end,
                        )
                    )
                subtitles = pysubs2.load(str(ass_path), encoding="utf-8")
                if not normalized_words or not subtitles.events:
                    alignment_passed = False
                    alignment_msg = (
                        f"words={len(normalized_words)}, "
                        f"subtitle_events={len(subtitles.events)}; both must be non-zero"
                    )
                else:
                    for index, event in enumerate(subtitles.events):
                        if event.start < 0 or event.end > clip_duration_ms or event.end <= event.start:
                            alignment_passed = False
                            alignment_msg = (
                                f"Subtitle event {index} is outside [0, {clip_duration_ms}]"
                            )
                            break
                        event_word = event.text.strip().casefold()
                        absolute_start = clip_start_ms + int(event.start)
                        absolute_end = clip_start_ms + int(event.end)
                        if not any(
                            candidate_word == event_word
                            and abs(candidate_start - absolute_start) <= 200
                            and abs(candidate_end - absolute_end) <= 200
                            for candidate_word, candidate_start, candidate_end in normalized_words
                        ):
                            alignment_passed = False
                            alignment_msg = (
                                f"Subtitle event {index} '{event.text}' at "
                                f"{absolute_start}-{absolute_end} ms has no matching word"
                            )
                            break
            except Exception as exc:
                alignment_passed = False
                alignment_msg = f"Unable to verify subtitle alignment: {exc}"
            add_check(
                check_id="subtitle_word_alignment",
                passed=alignment_passed,
                measured=alignment_msg,
                expected=(
                    "Non-empty ASS; every event maps to a transcript word within "
                    "+/-200 ms and remains inside the selected interval"
                ),
                evidence_path=(
                    _relative_evidence_path(ass_path, r_path)
                    if ass_path.exists()
                    else _relative_evidence_path(mapping_path, r_path)
                ),
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

    if output_path is not None:
        verify_result_file = pathlib.Path(output_path).resolve()
        try:
            verify_result_file.relative_to(r_path)
        except ValueError:
            pass
        else:
            raise ValueError("Verification output must be outside the run being verified")
        verify_result_file.parent.mkdir(parents=True, exist_ok=True)
        verify_result_file.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return result


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Zero-Trust Re-measurement and Verification")
    parser.add_argument("run_dir_pos", nargs="?", help="Run directory (positional)")
    parser.add_argument("--run-dir", dest="run_dir_flag", help="Run directory (--run-dir flag)")
    parser.add_argument("--output", dest="output_file", help="Output result JSON file")
    parser.add_argument("--audit-out", dest="audit_out_file", help="Alias for --output result JSON file")

    args = parser.parse_args()
    run_dir = args.run_dir_flag or args.run_dir_pos
    if not run_dir:
        parser.error("run_dir is required (either positional or via --run-dir)")

    output_path = args.audit_out_file or args.output_file
    res = verify_run(run_dir, output_path=output_path)
    print(json.dumps(res, indent=2))
    sys.exit(0 if res["overall_passed"] else 1)


if __name__ == "__main__":
    main()
