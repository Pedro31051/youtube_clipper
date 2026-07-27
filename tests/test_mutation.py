"""
Synthetic mutation test suite for Phase T0 verification engine.
Proves that cortes.verify.verify_run detects every intentional corruption.
"""

import json
import pathlib
import shutil
import pytest
from cortes.log import set_run_id, run_cmd, compute_sha256
from cortes.verify import verify_run


def create_synthetic_golden_run(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a perfectly valid synthetic Golden Run directory."""
    run_dir = tmp_path / "run_golden_synthetic"
    run_dir.mkdir(parents=True, exist_ok=True)
    set_run_id(run_dir.name)

    artifacts_dir = run_dir / "artifacts" / "clip_01"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    video_path = artifacts_dir / "short.mp4"

    # Generate 21s 1080x1920 synthetic video with loudnorm audio (-14.5 LUFS) via ffmpeg
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=1080x1920:rate=15",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000",
        "-af",
        "loudnorm=I=-14.5:TP=-1.5:LRA=11",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-t",
        "21",
        "-shortest",
        str(video_path),
    ]
    proc = run_cmd(cmd, stage="render")
    assert proc.returncode == 0 and video_path.exists()

    cmd_str = " ".join(cmd)
    video_sha = compute_sha256(video_path)
    video_bytes = video_path.stat().st_size

    # Populate commands.log in run_dir
    commands_log_file = run_dir / "commands.log"
    log_entry = (
        "================================================================================\n"
        "[2026-07-26T22:00:01.000000Z] [AGENT: worker] [CWD: /] [EXIT: 0] [DURATION: 1500.00ms]\n"
        f"COMMAND: {cmd_str}\n"
        "--- STDOUT ---\n\n"
        "--- STDERR ---\n\n"
        "================================================================================\n"
    )
    commands_log_file.write_text(log_entry, encoding="utf-8")

    # Manually populate events.jsonl for golden run
    events_file = run_dir / "events.jsonl"

    events = [
        {
            "schema_version": "1.0.0",
            "run_id": run_dir.name,
            "seq": 1,
            "ts": "2026-07-26T22:00:00.000000Z",
            "agent": "worker",
            "video_id": "test_video",
            "clip_id": None,
            "stage": "env",
            "attempt": 1,
            "severity": "info",
            "duration_ms": 100.0,
            "tool": "python",
            "cmd": None,
            "exit_code": 0,
            "args_hash": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "cost": {"usd": 0.0, "tokens_in": 0, "tokens_out": 0},
            "trace": {"span_id": "0123456789abcdef", "parent_span_id": None},
            "evidence": {"paths": [], "sha256": [], "bytes": []},
            "outcome": "ok",
            "error": None,
            "claim": None,
        },
        {
            "schema_version": "1.0.0",
            "run_id": run_dir.name,
            "seq": 2,
            "ts": "2026-07-26T22:00:01.000000Z",
            "agent": "worker",
            "video_id": "test_video",
            "clip_id": "clip_01",
            "stage": "render",
            "attempt": 1,
            "severity": "info",
            "duration_ms": 1500.0,
            "tool": "ffmpeg",
            "cmd": cmd_str,
            "exit_code": 0,
            "args_hash": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "cost": {"usd": 0.0, "tokens_in": 0, "tokens_out": 0},
            "trace": {"span_id": "0123456789abcdeg", "parent_span_id": "0123456789abcdef"},
            "evidence": {
                "paths": ["artifacts/clip_01/short.mp4"],
                "sha256": [video_sha],
                "bytes": [video_bytes],
            },
            "outcome": "ok",
            "error": None,
            "claim": None,
        },
    ]

    with open(events_file, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    return run_dir


def copy_golden_for_mutation(golden_run: pathlib.Path, target_dir: pathlib.Path) -> pathlib.Path:
    """Copy golden run to target_dir and update absolute evidence paths in events.jsonl."""
    shutil.copytree(golden_run, target_dir)
    events_file = target_dir / "events.jsonl"
    content = events_file.read_text(encoding="utf-8")
    content = content.replace(str(golden_run), str(target_dir))
    events_file.write_text(content, encoding="utf-8")
    return target_dir


@pytest.fixture(scope="module")
def golden_run(tmp_path_factory):
    """Build the expensive 21-second golden media only once per test module."""
    return create_synthetic_golden_run(tmp_path_factory.mktemp("mutation_golden"))


def test_mutation_0_golden_run_passes(golden_run):
    """Verify that the uncorrupted synthetic golden run passes verification completely."""
    res = verify_run(golden_run)
    assert res["overall_passed"] is True, f"Golden run failed checks: {res['checks']}"
    assert res["failed_checks"] == 0


def test_mutation_1_byte_corruption(golden_run, tmp_path):
    """Mutate video artifact by flipping bytes -> verify must fail artifact_sha256."""
    mut_dir = copy_golden_for_mutation(golden_run, tmp_path / "mut_byte")

    video_path = mut_dir / "artifacts" / "clip_01" / "short.mp4"
    with open(video_path, "r+b") as f:
        f.seek(100)
        byte_val = f.read(1)[0]
        f.seek(100)
        f.write(bytes([byte_val ^ 0xFF]))

    res = verify_run(mut_dir)
    assert res["overall_passed"] is False
    failed_checks = [c["check_id"] for c in res["checks"] if not c["passed"]]
    assert "artifact_sha256" in failed_checks


def test_mutation_2_seq_hole(golden_run, tmp_path):
    """Remove line 1 from events.jsonl creating a gap in seq -> verify must fail seq_integrity."""
    mut_dir = copy_golden_for_mutation(golden_run, tmp_path / "mut_seq_hole")

    events_file = mut_dir / "events.jsonl"
    lines = [l for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines = lines[1:]  # remove line seq 1
    events_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    res = verify_run(mut_dir)
    assert res["overall_passed"] is False
    failed_checks = [c["check_id"] for c in res["checks"] if not c["passed"]]
    assert "seq_integrity" in failed_checks


def test_mutation_3_seq_duplicate(golden_run, tmp_path):
    """Duplicate event line in events.jsonl -> verify must fail seq_integrity."""
    mut_dir = copy_golden_for_mutation(golden_run, tmp_path / "mut_seq_dup")

    events_file = mut_dir / "events.jsonl"
    lines = [l for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines.append(lines[-1])  # duplicate seq 2
    events_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    res = verify_run(mut_dir)
    assert res["overall_passed"] is False
    failed_checks = [c["check_id"] for c in res["checks"] if not c["passed"]]
    assert "seq_integrity" in failed_checks


def test_mutation_4_wrong_video_resolution(golden_run, tmp_path):
    """Replace short video with 1920x1080 video -> verify must fail video_resolution."""
    mut_dir = copy_golden_for_mutation(golden_run, tmp_path / "mut_res")

    video_path = mut_dir / "artifacts" / "clip_01" / "short.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=1920x1080:rate=15",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000",
        "-af",
        "loudnorm=I=-14.5:TP=-1.5:LRA=11",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-t",
        "21",
        "-shortest",
        str(video_path),
    ]
    run_cmd(cmd, stage="render")

    new_sha = compute_sha256(video_path)
    new_bytes = video_path.stat().st_size
    events_file = mut_dir / "events.jsonl"
    lines = [json.loads(l) for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines[1]["evidence"]["sha256"] = [new_sha]
    lines[1]["evidence"]["bytes"] = [new_bytes]
    events_file.write_text("\n".join(json.dumps(ev) for ev in lines) + "\n", encoding="utf-8")

    res = verify_run(mut_dir)
    assert res["overall_passed"] is False
    failed_checks = [c["check_id"] for c in res["checks"] if not c["passed"]]
    assert any(check.startswith("video_resolution::") for check in failed_checks)


def test_mutation_5_audio_loudness_out_of_bounds(golden_run, tmp_path):
    """Replace audio with hyper-amplified audio (-5 LUFS) -> verify must fail audio_lufs_loudness."""
    mut_dir = copy_golden_for_mutation(golden_run, tmp_path / "mut_loud")

    video_path = mut_dir / "artifacts" / "clip_01" / "short.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=1080x1920:rate=15",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000",
        "-af",
        "loudnorm=I=-5.0:TP=0:LRA=11",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-t",
        "21",
        "-shortest",
        str(video_path),
    ]
    run_cmd(cmd, stage="render")

    new_sha = compute_sha256(video_path)
    new_bytes = video_path.stat().st_size
    events_file = mut_dir / "events.jsonl"
    lines = [json.loads(l) for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines[1]["evidence"]["sha256"] = [new_sha]
    lines[1]["evidence"]["bytes"] = [new_bytes]
    events_file.write_text("\n".join(json.dumps(ev) for ev in lines) + "\n", encoding="utf-8")

    res = verify_run(mut_dir)
    assert res["overall_passed"] is False
    failed_checks = [c["check_id"] for c in res["checks"] if not c["passed"]]
    assert any(check.startswith("audio_lufs_loudness::") for check in failed_checks)


def test_mutation_6_video_duration_out_of_bounds(golden_run, tmp_path):
    """Replace video with 10s video (< 20s min) -> verify must fail video_duration_range."""
    mut_dir = copy_golden_for_mutation(golden_run, tmp_path / "mut_dur")

    video_path = mut_dir / "artifacts" / "clip_01" / "short.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=1080x1920:rate=15",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000",
        "-af",
        "loudnorm=I=-14.5:TP=-1.5:LRA=11",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-t",
        "10",
        "-shortest",
        str(video_path),
    ]
    run_cmd(cmd, stage="render")

    new_sha = compute_sha256(video_path)
    new_bytes = video_path.stat().st_size
    events_file = mut_dir / "events.jsonl"
    lines = [json.loads(l) for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines[1]["evidence"]["sha256"] = [new_sha]
    lines[1]["evidence"]["bytes"] = [new_bytes]
    events_file.write_text("\n".join(json.dumps(ev) for ev in lines) + "\n", encoding="utf-8")

    res = verify_run(mut_dir)
    assert res["overall_passed"] is False
    failed_checks = [c["check_id"] for c in res["checks"] if not c["passed"]]
    assert any(check.startswith("video_duration_range::") for check in failed_checks)


def test_mutation_7_missing_evidence_artifact(golden_run, tmp_path):
    """Delete declared video artifact file -> verify must fail artifact_exists."""
    mut_dir = copy_golden_for_mutation(golden_run, tmp_path / "mut_missing_artifact")

    video_path = mut_dir / "artifacts" / "clip_01" / "short.mp4"
    video_path.unlink()

    res = verify_run(mut_dir)
    assert res["overall_passed"] is False
    failed_checks = [c["check_id"] for c in res["checks"] if not c["passed"]]
    assert "artifact_exists" in failed_checks


def test_mutation_8_missing_events_file(golden_run, tmp_path):
    """Delete events.jsonl -> verify must fail events_file_exists."""
    mut_dir = copy_golden_for_mutation(golden_run, tmp_path / "mut_missing_events")

    events_file = mut_dir / "events.jsonl"
    events_file.unlink()

    res = verify_run(mut_dir)
    assert res["overall_passed"] is False
    failed_checks = [c["check_id"] for c in res["checks"] if not c["passed"]]
    assert "events_file_exists" in failed_checks


def test_mutation_9_invalid_event_schema(golden_run, tmp_path):
    """Corrupt events.jsonl schema version -> verify must fail events_schema_valid."""
    mut_dir = copy_golden_for_mutation(golden_run, tmp_path / "mut_invalid_schema")

    events_file = mut_dir / "events.jsonl"
    lines = [json.loads(l) for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines[0]["schema_version"] = "9.9.9"
    events_file.write_text("\n".join(json.dumps(ev) for ev in lines) + "\n", encoding="utf-8")

    res = verify_run(mut_dir)
    assert res["overall_passed"] is False
    failed_checks = [c["check_id"] for c in res["checks"] if not c["passed"]]
    assert "events_schema_valid" in failed_checks


def test_mutation_10_stage_dag_out_of_order(golden_run, tmp_path):
    """Reorder stage events (place render before env) -> verify must fail seq_integrity."""
    mut_dir = copy_golden_for_mutation(golden_run, tmp_path / "mut_stage_dag")

    events_file = mut_dir / "events.jsonl"
    lines = [json.loads(l) for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    ev_render = lines[1]
    ev_env = lines[0]
    ev_render["seq"] = 1
    ev_env["seq"] = 2
    events_file.write_text(json.dumps(ev_render) + "\n" + json.dumps(ev_env) + "\n", encoding="utf-8")

    res = verify_run(mut_dir)
    assert res["overall_passed"] is False
    failed_checks = [c["check_id"] for c in res["checks"] if not c["passed"]]
    assert "seq_integrity" in failed_checks


def test_mutation_11_non_monotonic_timestamp(golden_run, tmp_path):
    """Decrease event timestamp in seq 2 -> verify must fail ts_monotonic."""
    mut_dir = copy_golden_for_mutation(golden_run, tmp_path / "mut_ts_mono")

    events_file = mut_dir / "events.jsonl"
    lines = [json.loads(l) for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines[1]["ts"] = "2020-01-01T00:00:00.000000Z"
    events_file.write_text("\n".join(json.dumps(ev) for ev in lines) + "\n", encoding="utf-8")

    res = verify_run(mut_dir)
    assert res["overall_passed"] is False
    failed_checks = [c["check_id"] for c in res["checks"] if not c["passed"]]
    assert "ts_monotonic" in failed_checks


def test_mutation_12_commands_log_unsynced(golden_run, tmp_path):
    """Delete commands.log when events contain commands -> verify must fail commands_log_sync."""
    mut_dir = copy_golden_for_mutation(golden_run, tmp_path / "mut_commands_sync")

    commands_file = mut_dir / "commands.log"
    if commands_file.exists():
        commands_file.unlink()

    res = verify_run(mut_dir)
    assert res["overall_passed"] is False
    failed_checks = [c["check_id"] for c in res["checks"] if not c["passed"]]
    assert "commands_log_sync" in failed_checks


def test_mutation_13_non_zero_exit_code(golden_run, tmp_path):
    """Set non-zero exit_code on outcome ok event -> verify must fail exit_codes_zero."""
    mut_dir = copy_golden_for_mutation(golden_run, tmp_path / "mut_exit_code")

    events_file = mut_dir / "events.jsonl"
    lines = [json.loads(l) for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines[1]["exit_code"] = 1
    events_file.write_text("\n".join(json.dumps(ev) for ev in lines) + "\n", encoding="utf-8")

    res = verify_run(mut_dir)
    assert res["overall_passed"] is False
    failed_checks = [c["check_id"] for c in res["checks"] if not c["passed"]]
    assert "exit_codes_zero" in failed_checks


def test_mutation_14_missing_producer_evidence(golden_run, tmp_path):
    """Remove evidence paths from producer stage event -> verify must fail producer_evidence_required."""
    mut_dir = copy_golden_for_mutation(golden_run, tmp_path / "mut_producer_ev")

    events_file = mut_dir / "events.jsonl"
    lines = [json.loads(l) for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines[1]["evidence"] = {"paths": [], "sha256": [], "bytes": []}
    events_file.write_text("\n".join(json.dumps(ev) for ev in lines) + "\n", encoding="utf-8")

    res = verify_run(mut_dir)
    assert res["overall_passed"] is False
    failed_checks = [c["check_id"] for c in res["checks"] if not c["passed"]]
    assert "producer_evidence_required" in failed_checks


def test_mutation_15_artifact_bytes_mismatch(golden_run, tmp_path):
    """Alter declared byte size in event -> verify must fail artifact_bytes."""
    mut_dir = copy_golden_for_mutation(golden_run, tmp_path / "mut_artifact_bytes")

    events_file = mut_dir / "events.jsonl"
    lines = [json.loads(l) for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines[1]["evidence"]["bytes"][0] += 999
    events_file.write_text("\n".join(json.dumps(ev) for ev in lines) + "\n", encoding="utf-8")

    res = verify_run(mut_dir)
    assert res["overall_passed"] is False
    failed_checks = [c["check_id"] for c in res["checks"] if not c["passed"]]
    assert "artifact_bytes" in failed_checks


def test_mutation_16_audio_stream_count_mismatch(golden_run, tmp_path):
    """Replace video artifact with an audio-less video -> verify must fail audio_stream_count."""
    mut_dir = copy_golden_for_mutation(golden_run, tmp_path / "mut_audio_stream")

    video_path = mut_dir / "artifacts" / "clip_01" / "short.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi", "-i", "testsrc=size=1080x1920:rate=15",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-an",
        "-t", "21",
        str(video_path),
    ]
    run_cmd(cmd, stage="render")

    new_sha = compute_sha256(video_path)
    new_bytes = video_path.stat().st_size
    events_file = mut_dir / "events.jsonl"
    lines = [json.loads(l) for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines[1]["evidence"]["sha256"] = [new_sha]
    lines[1]["evidence"]["bytes"] = [new_bytes]
    events_file.write_text("\n".join(json.dumps(ev) for ev in lines) + "\n", encoding="utf-8")

    res = verify_run(mut_dir)
    assert res["overall_passed"] is False
    failed_checks = [c["check_id"] for c in res["checks"] if not c["passed"]]
    assert any(check.startswith("audio_stream_count::") for check in failed_checks)
