"""Generate the immutable Phase T2 golden run and external verification result."""

from __future__ import annotations

import json
import pathlib
import shutil

from cortes.log import get_run_dir, run_cmd, set_run_id
from cortes.pipeline import run_full_pipeline
from cortes.report import run_report
from cortes.verify import verify_run


RUN_ID = "run_t2_golden"


def main() -> int:
    set_run_id(RUN_ID)
    run_dir = pathlib.Path("runs") / RUN_ID
    if run_dir.exists():
        raise RuntimeError(f"Refusing to overwrite immutable run: {run_dir}")

    run_dir = get_run_dir(RUN_ID)
    scratch_dir = run_dir / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    source_path = scratch_dir / "source_original_cc0.mp4"
    license_path = scratch_dir / "LICENSE_PROOF.md"
    license_path.write_text(
        "\n".join(
            [
                "# Source and license proof",
                "",
                "- Author: YouTube Clipper T2 test fixture",
                "- Created: 2026-07-27",
                "- Source: generated locally with FFmpeg `testsrc` and `flite`",
                "- Third-party audiovisual content: none",
                "- Dedication: CC0 1.0",
                "- Text: original technical test paragraph embedded in this script",
                "",
                "The fixture was generated locally and was not downloaded from YouTube",
                "or any third-party media source.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    spoken_text = (
        "This original technical demonstration explains reliable video processing "
        "with speech transcription scene detection deterministic selection accurate "
        "subtitles audio normalization and vertical rendering. Every spoken word "
        "receives a timestamp so an independent verifier can prove synchronization "
        "selection boundaries frame rate loudness and artifact integrity. This final "
        "sentence provides enough continuous speech for a complete technical short."
    )
    source_command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=30:size=640x360:rate=30",
        "-f",
        "lavfi",
        "-i",
        f"flite=text={spoken_text}",
        "-af",
        "apad",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-pix_fmt",
        "yuv420p",
        "-t",
        "30",
        str(source_path),
    ]
    source_result = run_cmd(
        source_command,
        stage="env",
        check=True,
        evidence_paths=[license_path],
    )
    if source_result.returncode != 0 or source_path.stat().st_size <= 1024:
        raise RuntimeError("Unable to generate the T2 source fixture")

    pipeline_result = run_full_pipeline(
        input_source=source_path,
        run_id=RUN_ID,
        whisper_model="small",
        device="cuda",
        vertical_mode="blur_background",
    )

    review_dir = pathlib.Path("review") / "T2"
    review_dir.mkdir(parents=True, exist_ok=True)
    verify_path = review_dir / "verify_result.json"
    verification = verify_run(run_dir, output_path=verify_path)
    if not verification["overall_passed"]:
        raise RuntimeError(
            "Golden verification failed: "
            + json.dumps(
                [
                    check
                    for check in verification["checks"]
                    if not check["passed"]
                ],
                ensure_ascii=False,
            )
        )

    report_result = run_report(
        run_dir_or_action=run_dir,
        run_id=RUN_ID,
        verify_result_path=verify_path,
    )
    shutil.copy2(report_result["report_path"], review_dir / "report.md")

    summary = {
        "run_id": RUN_ID,
        "clip_id": pipeline_result["clip_id"],
        "short_path": pipeline_result["render_path"],
        "report_path": report_result["report_path"],
        "verify_result_path": str(verify_path),
        "overall_passed": verification["overall_passed"],
        "passed_checks": verification["passed_checks"],
        "total_checks": verification["total_checks"],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
