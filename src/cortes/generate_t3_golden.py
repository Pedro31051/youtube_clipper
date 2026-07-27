"""Script to execute Golden Run for Phase T3."""

import pathlib
from datetime import datetime, timezone
from typing import Optional
from cortes.log import audited, set_run_id, run_cmd, get_run_dir
from cortes.pipeline import run_full_pipeline


@audited(stage="env")
def setup_env_stage(run_id: str) -> dict:
    run_dir = get_run_dir(run_id)
    scratch_dir = run_dir / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)

    proof_file = scratch_dir / "LICENSE_PROOF.md"
    proof_file.write_text(
        "Public Domain CC0 synthetic source video generated via FFmpeg lavfi testsrc and flite TTS.\n",
        encoding="utf-8",
    )

    source_video = scratch_dir / "source_original_cc0.mp4"

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=30:size=640x360:rate=30",
        "-f", "lavfi", "-i", "flite=text=This original technical demonstration explains reliable video processing with speech transcription scene detection deterministic selection accurate subtitles audio normalization and vertical rendering. Every spoken word receives a timestamp so an independent verifier can prove synchronization selection boundaries frame rate loudness and artifact integrity. This final sentence provides enough continuous speech for a complete technical short.",
        "-af", "apad",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        "-t", "30",
        str(source_video),
    ]

    res = run_cmd(cmd, stage="env")
    if res.returncode != 0 or not source_video.exists():
        raise RuntimeError(f"Failed to generate synthetic source video: {res.stderr}")

    narration_text_path = scratch_dir / "editorial_narration.txt"
    narration_text_path.write_text(
        (
            "Editorial analysis. This demonstration adds original commentary "
            "explaining why deterministic selection, measurable loudness, "
            "synchronized captions, and reproducible evidence make the "
            "transformed short more useful than a simple copied excerpt."
        ),
        encoding="utf-8",
    )
    narration_path = scratch_dir / "editorial_narration.wav"
    narration_cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"flite=textfile={narration_text_path}",
        "-af",
        "apad",
        "-t",
        "10",
        "-c:a",
        "pcm_s16le",
        str(narration_path),
    ]
    narration_res = run_cmd(narration_cmd, stage="env")
    if narration_res.returncode != 0 or not narration_path.exists():
        raise RuntimeError(
            f"Failed to generate editorial narration: {narration_res.stderr}"
        )

    return {
        "status": "ok",
        "source_video": str(source_video),
        "narration_path": str(narration_path),
        "evidence_paths": [
            str(proof_file),
            str(narration_text_path),
            str(narration_path),
        ],
    }


def generate_t3_golden(
    run_id: Optional[str] = None,
    template_variant: Optional[str] = None,
):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = run_id or f"run_t3_golden_{stamp}"
    template_variant = template_variant or f"variant_t3_{stamp}"
    existing_run = pathlib.Path("runs") / run_id
    if existing_run.exists() and any(existing_run.iterdir()):
        raise RuntimeError(
            f"Refusing to append to existing golden run directory: {existing_run}"
        )
    set_run_id(run_id)

    env_res = setup_env_stage(run_id)
    source_video = env_res["source_video"]
    narration_path = env_res["narration_path"]

    pipeline_res = run_full_pipeline(
        input_source=source_video,
        run_id=run_id,
        whisper_model="small",
        device="cuda",
        vertical_mode="blur_background",
        analytical_overlay=True,
        overlay_text="ANALYTICAL OVERLAY | VIRAL HOOK SCORE: 9.8",
        narration_path=narration_path,
        tts_narration=True,
        require_editorial_transformation=True,
        template_variant=template_variant,
    )

    print("Golden run generated successfully:", pipeline_res)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate a physical T3 golden run")
    parser.add_argument("--run-id")
    parser.add_argument(
        "--template-variant",
    )
    cli_args = parser.parse_args()
    generate_t3_golden(
        run_id=cli_args.run_id,
        template_variant=cli_args.template_variant,
    )
