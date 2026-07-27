"""Empirical step-by-step runner for Stage 1 to 9 E2E verification."""

import json
import os
import pathlib
import sys
import time

from cortes.log import compute_sha256, get_run_dir, run_cmd, set_run_id
from cortes.pipeline import run_full_pipeline
from cortes.report import run_report
from cortes.verify import verify_run


def main():
    print("=== Step 1: Generating 25s synthetic MP4 fixture ===", flush=True)
    tmp_dir = pathlib.Path("runs/scratch_empirical")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    vid_path = tmp_dir / "synthetic_25s_input.mp4"

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=25:size=640x360:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=25",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        str(vid_path),
    ]
    res = run_cmd(cmd, stage="env", audit=False)
    if res.returncode != 0:
        print(f"Error creating synthetic video: {res.stderr}", flush=True)
        sys.exit(1)
    print(f"Synthetic video generated at {vid_path} ({vid_path.stat().st_size} bytes)", flush=True)

    run_id = f"run_m3_empirical_challenger_{int(time.time())}"
    print(f"=== Step 2: Executing run_full_pipeline (run_id: {run_id}) ===", flush=True)

    pipeline_res = run_full_pipeline(
        input_source=vid_path,
        run_id=run_id,
        whisper_model="small",
        device="cuda",
        vertical_mode="blur_background",
    )

    print("Pipeline finished successfully!", flush=True)
    print(f"Pipeline Result: {json.dumps(pipeline_res, indent=2)}", flush=True)

    run_dir = get_run_dir(run_id)
    print(f"=== Step 3: Verifying artifacts in {run_dir}/artifacts/ ===", flush=True)
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
        print(f"Artifact subdir '{sub}': {[f.name for f in files]}", flush=True)
        assert len(files) > 0, f"Artifact directory is empty: {sub_path}"

    print("=== Step 4: Verifying events.jsonl sequence & hashes ===", flush=True)
    events_file = run_dir / "events.jsonl"
    assert events_file.exists()
    lines = [l for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"Total events recorded: {len(lines)}", flush=True)
    seqs = []
    for idx, l in enumerate(lines, start=1):
        ev = json.loads(l)
        seqs.append(ev["seq"])
        assert ev["seq"] == idx, f"Sequence gap/duplicate at index {idx}: expected {idx}, got {ev['seq']}"
        if ev.get("outcome") == "ok" and ev.get("evidence"):
            paths = ev["evidence"].get("paths", [])
            hashes = ev["evidence"].get("sha256", [])
            sizes = ev["evidence"].get("bytes", [])
            for p_rel, h_decl, s_decl in zip(paths, hashes, sizes):
                p_abs = (run_dir / p_rel).resolve()
                assert p_abs.exists(), f"Evidence path missing: {p_abs}"
                assert compute_sha256(p_abs) == h_decl, f"SHA256 mismatch for {p_rel}"
                assert p_abs.stat().st_size == s_decl, f"Byte size mismatch for {p_rel}"
    assert seqs == list(range(1, len(seqs) + 1))
    print("events.jsonl sequence (1..N) and cryptographic evidence hashes verified 100% OK!", flush=True)

    print("=== Step 5: Running zero-trust verification engine verify_run ===", flush=True)
    verify_out_path = run_dir.parent / f"verify_result_{run_id}.json"
    verify_res = verify_run(run_dir=run_dir, output_path=verify_out_path)
    print(f"Verification Output written to {verify_out_path}", flush=True)
    print(f"Overall Passed: {verify_res['overall_passed']}", flush=True)
    print(f"Passed Checks: {verify_res['passed_checks']} / {verify_res['total_checks']}", flush=True)
    print(f"Failed Checks: {verify_res['failed_checks']}", flush=True)
    assert verify_res["overall_passed"] is True, f"Zero-trust verification failed: {verify_res}"

    print("=== Step 6: Re-running report generator with verify_result ===", flush=True)
    report_res = run_report(run_dir_or_action=run_dir, run_id=run_id, verify_result_path=verify_out_path)
    report_text = pathlib.Path(report_res["report_path"]).read_text(encoding="utf-8")
    assert "**Verification Verdict**: `PASSED`" in report_text
    print("Immutable verified report emitted with Verification Verdict: PASSED!", flush=True)
    print("\nALL EMPIRICAL CHALLENGER VERIFICATIONS PASSED 100%!", flush=True)


if __name__ == "__main__":
    main()
