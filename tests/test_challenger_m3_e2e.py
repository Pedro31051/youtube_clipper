"""Empirical E2E pipeline challenger stress test for Milestone M3.

Verifies end-to-end execution of run_full_pipeline on a synthetic video fixture,
checks all 8 stage output artifact directories under runs/<run_id>/artifacts/,
verifies events.jsonl sequence continuity and hash signatures, runs zero-trust
verify_run, re-runs report generator, and verifies overall_passed == True.
"""

import json
import pathlib
import pytest

from cortes.log import compute_sha256, run_cmd, set_run_id
from cortes.pipeline import run_full_pipeline
from cortes.report import run_report
from cortes.verify import verify_run


@pytest.fixture
def synthetic_25s_video(tmp_path):
    """Generate a synthetic 25-second MP4 test video with audio and a scene cut."""
    vid_path = tmp_path / "synthetic_25s_input.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=25:size=640x360:rate=30",
        "-f", "lavfi", "-i",
        "flite=text=This technical demonstration explains reliable video processing with transcription scenes selection subtitles audio normalization and vertical rendering. Every spoken word receives an accurate timestamp so the verifier can independently prove synchronization and integrity. This sentence repeats enough useful speech for a complete short video pipeline test.",
        "-af", "apad",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        "-t", "25",
        str(vid_path),
    ]
    res = run_cmd(cmd, stage="env", audit=False)
    assert res.returncode == 0, f"FFmpeg video creation failed: {res.stderr}"
    assert vid_path.exists() and vid_path.stat().st_size > 1024
    return vid_path


def test_e2e_full_pipeline_empirical_challenger(synthetic_25s_video, tmp_path):
    """Empirical E2E test verifying run_full_pipeline across all 9 stages."""
    run_id = f"run_challenger_e2e_{tmp_path.name}"
    set_run_id(run_id)

    # 1. Execute run_full_pipeline end-to-end
    pipeline_res = run_full_pipeline(
        input_source=synthetic_25s_video,
        run_id=run_id,
        whisper_model="small",
        device="cuda",
        vertical_mode="blur_background",
    )

    assert pipeline_res["status"] == "ok"
    run_dir = pathlib.Path(pipeline_res["report_path"]).parent
    assert run_dir.exists()

    # 2. Verify all output artifact directories in runs/<run_id>/artifacts/
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
        assert sub_path.exists() and sub_path.is_dir(), f"Artifact directory missing: {sub_path}"
        files = list(sub_path.glob("*"))
        assert len(files) > 0, f"Artifact directory is empty: {sub_path}"

    # Specific key artifact file checks
    assert (art_dir / "ingest" / "metadata.json").exists()
    assert (art_dir / "transcribe" / "transcript.json").exists()
    assert (art_dir / "scenes" / "scenes.json").exists()
    assert (art_dir / "select" / "selection.json").exists()
    assert (art_dir / "cut" / "clip.mp4").exists()
    assert (art_dir / "subtitles" / "subtitles.ass").exists()
    assert (art_dir / "audio" / "audio_normalized.mp4").exists()
    assert (art_dir / "render" / "short.mp4").exists()

    # 3. Verify events.jsonl integrity
    events_file = run_dir / "events.jsonl"
    assert events_file.exists()
    event_lines = [l for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(event_lines) >= 9, f"Expected at least 9 events, got {len(event_lines)}"

    seqs = []
    for idx, line in enumerate(event_lines, start=1):
        ev = json.loads(line)
        seqs.append(ev["seq"])
        assert ev["seq"] == idx, f"Sequence mismatch at index {idx}: expected {idx}, got {ev['seq']}"

        # Verify evidence paths and SHA-256 hashes
        if ev.get("outcome") == "ok" and ev.get("evidence"):
            paths = ev["evidence"].get("paths", [])
            hashes = ev["evidence"].get("sha256", [])
            sizes = ev["evidence"].get("bytes", [])

            for p_rel, h_decl, s_decl in zip(paths, hashes, sizes):
                p_abs = (run_dir / p_rel).resolve()
                assert p_abs.exists(), f"Evidence file does not exist: {p_abs}"
                assert compute_sha256(p_abs) == h_decl, f"Hash mismatch for {p_rel}"
                assert p_abs.stat().st_size == s_decl, f"Size mismatch for {p_rel}"

    # Confirm strict monotonic sequence 1..N with zero gaps or duplicates
    assert seqs == list(range(1, len(seqs) + 1))

    # 4. Zero-Trust Verification Engine Run
    verify_out_path = tmp_path / f"verify_result_{run_id}.json"
    verify_res = verify_run(run_dir=run_dir, output_path=verify_out_path)

    assert verify_res["overall_passed"] is True, f"Zero-trust verification failed: {verify_res}"
    assert verify_res["failed_checks"] == 0

    # 5. Emit an immutable verified report without overwriting report.md
    report_res = run_report(run_dir_or_action=run_dir, run_id=run_id, verify_result_path=verify_out_path)
    assert report_res["status"] == "ok"

    report_text = pathlib.Path(report_res["report_path"]).read_text(encoding="utf-8")
    assert "**Verification Verdict**: `PASSED`" in report_text
    assert "- **Overall Status**: `PASSED`" in report_text
