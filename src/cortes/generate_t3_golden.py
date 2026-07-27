"""Script to execute Golden Run for Phase T3."""

import pathlib
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

    return {
        "status": "ok",
        "source_video": str(source_video),
        "evidence_paths": [str(proof_file)],
    }


def generate_t3_golden():
    run_id = "run_t3_golden"
    set_run_id(run_id)

    env_res = setup_env_stage(run_id)
    source_video = env_res["source_video"]

    pipeline_res = run_full_pipeline(
        input_source=source_video,
        run_id=run_id,
        whisper_model="small",
        device="cuda",
        vertical_mode="blur_background",
        analytical_overlay=True,
        overlay_text="ANALYTICAL OVERLAY | VIRAL HOOK SCORE: 9.8",
        tts_narration=True,
        tts_duration_s=10.5,
        template_variant="variant_t3_analytical_v1",
    )

    print("Golden run generated successfully:", pipeline_res)


if __name__ == "__main__":
    generate_t3_golden()
