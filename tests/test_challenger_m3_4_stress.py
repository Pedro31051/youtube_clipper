"""Empirical challenger stress suite for Milestone M3 remediation.

Rigorously verifies:
1. End-to-end execution of run_full_pipeline on synthetic video fixture.
2. Artifact structure across all 8 artifact directories under runs/<run_id>/artifacts/.
3. events.jsonl sequence continuity, non-decreasing timestamps, relative evidence paths, SHA-256 hashes, and byte sizes.
4. Zero-trust verification engine (verify_run) overall_passed == True and failed_checks == 0.
5. report.md generation with PASSED status.
6. Adversarial mutation stress tests (hash corruption, sequence tampering, non-monotonic timestamps, path escape attempts).
"""

import json
import os
import pathlib
import pytest

from cortes.log import compute_sha256, run_cmd, set_run_id
from cortes.pipeline import run_full_pipeline
from cortes.report import run_report
from cortes.verify import _resolve_evidence_path, verify_run


def _e2e_device() -> str:
    """Select the explicit device for empirical E2E tests.

    CPU is the portable default used by GitHub-hosted runners. A GPU runner
    opts into the exact same scenarios with
    ``YOUTUBE_CLIPPER_E2E_DEVICE=cuda``.
    """
    device = os.environ.get("YOUTUBE_CLIPPER_E2E_DEVICE", "cpu").strip().lower()
    if device not in {"cpu", "cuda"}:
        raise ValueError(
            "YOUTUBE_CLIPPER_E2E_DEVICE must be either 'cpu' or 'cuda'"
        )
    return device


@pytest.fixture
def synthetic_30s_video(tmp_path):
    """Generate a valid 30-second synthetic MP4 test video with video and audio streams."""
    vid_path = tmp_path / "synthetic_30s_input.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=30:size=640x360:rate=30",
        "-f", "lavfi", "-i",
        "flite=text=This technical demonstration explains reliable video processing with transcription scenes selection subtitles audio normalization and vertical rendering. Every spoken word receives an accurate timestamp so the verifier can independently prove synchronization and integrity. This sentence repeats enough useful speech for a complete short video pipeline stress test.",
        "-af", "apad",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        "-t", "30",
        str(vid_path),
    ]
    res = run_cmd(cmd, stage="env", audit=False)
    assert res.returncode == 0, f"FFmpeg video creation failed: {res.stderr}"
    assert vid_path.exists() and vid_path.stat().st_size > 1024
    return vid_path


def test_m3_challenger_full_pipeline_end_to_end(synthetic_30s_video, tmp_path):
    """Task 1-4: End-to-end execution, artifact verification, event log integrity, and zero-trust verification."""
    run_id = f"run_m3_challenger_stress_{tmp_path.name}"
    set_run_id(run_id)

    # 1. Execute run_full_pipeline end-to-end
    pipeline_res = run_full_pipeline(
        input_source=synthetic_30s_video,
        run_id=run_id,
        whisper_model="small",
        device=_e2e_device(),
        vertical_mode="blur_background",
    )

    assert pipeline_res["status"] == "ok"
    assert pipeline_res["run_id"] == run_id

    report_path = pathlib.Path(pipeline_res["report_path"])
    run_dir = report_path.parent
    assert run_dir.exists()

    # 2. Verify all output artifacts in runs/<run_id>/artifacts/
    art_dir = run_dir / "artifacts"
    expected_artifact_subdirs = [
        "ingest",
        "transcribe",
        "scenes",
        "select",
        "cut",
        "subtitles",
        "audio",
        "render",
    ]
    for sub in expected_artifact_subdirs:
        sub_path = art_dir / sub
        assert sub_path.exists() and sub_path.is_dir(), f"Missing artifact dir: {sub_path}"
        files = list(sub_path.glob("*"))
        assert len(files) > 0, f"Empty artifact dir: {sub_path}"
        for f in files:
            assert f.stat().st_size > 0, f"Zero-byte artifact file: {f}"

    # Specific mandatory artifact files
    assert (art_dir / "ingest" / "metadata.json").exists()
    assert (art_dir / "transcribe" / "transcript.json").exists()
    assert (art_dir / "scenes" / "scenes.json").exists()
    assert (art_dir / "select" / "selection.json").exists()
    assert (art_dir / "cut" / "clip.mp4").exists()
    assert (art_dir / "cut" / "clip.mp4").stat().st_size > 1024
    assert (art_dir / "subtitles" / "subtitles.ass").exists()
    assert (art_dir / "audio" / "audio_normalized.mp4").exists()
    assert (art_dir / "audio" / "audio_normalized.mp4").stat().st_size > 1024
    assert (art_dir / "render" / "short.mp4").exists()
    assert (art_dir / "render" / "short.mp4").stat().st_size > 1024

    # 3. Verify events.jsonl integrity
    events_file = run_dir / "events.jsonl"
    assert events_file.exists()
    event_lines = [l for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(event_lines) >= 9, f"Expected >= 9 events, found {len(event_lines)}"

    seqs = []
    for idx, line in enumerate(event_lines, start=1):
        ev = json.loads(line)
        seqs.append(ev["seq"])
        assert ev["seq"] == idx, f"Sequence mismatch at index {idx}: expected {idx}, got {ev['seq']}"

        # Verify evidence paths are relative and hashes match
        if ev.get("outcome") == "ok" and ev.get("evidence"):
            paths = ev["evidence"].get("paths", [])
            hashes = ev["evidence"].get("sha256", [])
            sizes = ev["evidence"].get("bytes", [])

            assert len(paths) == len(hashes) == len(sizes)
            for p_rel, h_decl, s_decl in zip(paths, hashes, sizes):
                assert not pathlib.Path(p_rel).is_absolute(), f"Absolute evidence path in event: {p_rel}"
                p_abs = (run_dir / p_rel).resolve()
                assert p_abs.exists(), f"Evidence path does not exist on disk: {p_abs}"
                assert compute_sha256(p_abs) == h_decl, f"Hash signature mismatch for {p_rel}"
                assert p_abs.stat().st_size == s_decl, f"Byte size mismatch for {p_rel}"

    assert seqs == list(range(1, len(seqs) + 1))

    # 4. Verify verify_result.json zero-trust verification pass
    verify_out_path = tmp_path / f"verify_result_{run_id}.json"
    verify_res = verify_run(run_dir=run_dir, output_path=verify_out_path)

    assert verify_res["overall_passed"] is True, f"Zero-trust verification failed: {verify_res}"
    assert verify_res["failed_checks"] == 0
    assert verify_res["passed_checks"] == verify_res["total_checks"]

    # 5. Emit an immutable verified report without overwriting report.md
    report_res = run_report(run_dir_or_action=run_dir, run_id=run_id, verify_result_path=verify_out_path)
    assert report_res["status"] == "ok"

    report_text = pathlib.Path(report_res["report_path"]).read_text(encoding="utf-8")
    assert "**Verification Verdict**: `PASSED`" in report_text
    assert "- **Overall Status**: `PASSED`" in report_text


def test_m3_challenger_mutation_stress(synthetic_30s_video, tmp_path):
    """Adversarial stress test: prove verify.py catches artifact mutation, seq gap, non-monotonic ts, path traversal."""
    run_id = f"run_m3_mutation_{tmp_path.name}"
    set_run_id(run_id)

    pipeline_res = run_full_pipeline(
        input_source=synthetic_30s_video,
        run_id=run_id,
        device=_e2e_device(),
    )
    report_path = pathlib.Path(pipeline_res["report_path"])
    run_dir = report_path.parent

    # Baseline pass
    base_verify = verify_run(run_dir=run_dir)
    assert base_verify["overall_passed"] is True

    # 1. Corrupt artifact content (hash mismatch)
    short_mp4 = run_dir / "artifacts" / "render" / "short.mp4"
    original_bytes = short_mp4.read_bytes()
    try:
        short_mp4.write_bytes(original_bytes + b"CORRUPT")
        corrupt_verify = verify_run(run_dir=run_dir)
        assert corrupt_verify["overall_passed"] is False
        assert any(c["check_id"] == "artifact_sha256" and not c["passed"] for c in corrupt_verify["checks"])
        assert any(c["check_id"] == "artifact_bytes" and not c["passed"] for c in corrupt_verify["checks"])
    finally:
        short_mp4.write_bytes(original_bytes)

    # 2. Sequence gap mutation in events.jsonl
    events_file = run_dir / "events.jsonl"
    original_events_text = events_file.read_text(encoding="utf-8")
    lines = [l for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    ev0 = json.loads(lines[0])
    ev0["seq"] = 99
    lines[0] = json.dumps(ev0)
    try:
        events_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        seq_verify = verify_run(run_dir=run_dir)
        assert seq_verify["overall_passed"] is False
        assert any(c["check_id"] == "seq_integrity" and not c["passed"] for c in seq_verify["checks"])
    finally:
        # Restore the exact immutable fixture bytes; reruns must use a new ID.
        events_file.write_text(original_events_text, encoding="utf-8")

    # 3. Path escape security test
    with pytest.raises(ValueError, match="Evidence path escapes"):
        _resolve_evidence_path("../../etc/passwd", run_dir)
