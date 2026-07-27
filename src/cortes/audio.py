"""Audited Stage 7 (audio) processing module."""

import json
import pathlib
import re
from typing import Any, Callable, Dict, Optional, Union

from cortes.log import audited, get_run_dir, run_cmd
from youtube_clipper.exceptions import ProcessingError


@audited(stage="audio")
def parse_loudnorm_pass1_stderr(stderr: str) -> Dict[str, str]:
    """Parse JSON loudnorm stats block from FFmpeg stderr."""
    match = re.search(r"\{[\s\S]*?\"input_i\"[\s\S]*?\}", stderr)
    if not match:
        raise ProcessingError(f"Failed to find loudnorm Pass 1 JSON block in FFmpeg stderr: {stderr}")
    try:
        return json.loads(match.group(0))
    except Exception as e:
        raise ProcessingError(f"Failed to parse loudnorm Pass 1 JSON: {e}") from e


@audited(stage="audio")
def process_audio_loudnorm(
    input_media: Union[str, pathlib.Path],
    output_media: Union[str, pathlib.Path],
    stats_json: Union[str, pathlib.Path],
    target_lufs: float = -14.0,
    target_lra: float = 11.0,
    target_tp: float = -0.1,
) -> Dict[str, Any]:
    """Execute two-pass FFmpeg loudnorm audio normalization."""
    in_p = pathlib.Path(input_media).resolve()
    if not in_p.exists():
        raise ProcessingError(f"Input media file for audio stage does not exist: {in_p}")

    out_p = pathlib.Path(output_media).resolve()
    stats_p = pathlib.Path(stats_json).resolve()

    out_p.parent.mkdir(parents=True, exist_ok=True)
    stats_p.parent.mkdir(parents=True, exist_ok=True)

    # Pass 1: Measure
    cmd_pass1 = [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-hide_banner",
        "-i",
        str(in_p),
        "-af",
        f"loudnorm=I={target_lufs}:LRA={target_lra}:TP={target_tp}:print_format=json",
        "-f",
        "null",
        "-",
    ]
    res1 = run_cmd(cmd_pass1, stage="audio")
    if res1.returncode != 0:
        raise ProcessingError(f"FFmpeg loudnorm Pass 1 failed with returncode {res1.returncode}: {res1.stderr}")

    pass1_stats = parse_loudnorm_pass1_stderr(res1.stderr)

    input_i = pass1_stats.get("input_i", "-24.0")
    input_lra = pass1_stats.get("input_lra", "7.0")
    input_tp = pass1_stats.get("input_tp", "-2.0")
    input_thresh = pass1_stats.get("input_thresh", "-34.0")
    target_offset = pass1_stats.get("target_offset", "0.0")

    # Pass 2: Apply
    filter_pass2 = (
        f"loudnorm=I={target_lufs}:LRA={target_lra}:TP={target_tp}:"
        f"measured_I={input_i}:measured_LRA={input_lra}:measured_TP={input_tp}:"
        f"measured_thresh={input_thresh}:offset={target_offset}:linear=true"
    )

    cmd_pass2 = [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-hide_banner",
        "-i",
        str(in_p),
        "-af",
        filter_pass2,
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(out_p),
    ]
    res2 = run_cmd(cmd_pass2, stage="audio")
    if res2.returncode != 0 or not out_p.exists() or out_p.stat().st_size <= 1024:
        raise ProcessingError(f"FFmpeg loudnorm Pass 2 failed: {res2.stderr}")

    audio_stats = {
        "schema_version": "1.0.0",
        "target_lufs": target_lufs,
        "target_lra": target_lra,
        "target_tp": target_tp,
        "pass1_measured": pass1_stats,
    }
    stats_p.write_text(json.dumps(audio_stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {
        "status": "ok",
        "audio_path": str(out_p),
        "stats_path": str(stats_p),
        "evidence_paths": [str(out_p), str(stats_p)],
    }


@audited(stage="audio")
def run_audio(
    input_source_or_action: Union[str, pathlib.Path, Callable[..., Any]],
    *args: Any,
    run_id: Optional[str] = None,
    target_lufs: float = -14.0,
    output_path: Optional[Union[str, pathlib.Path]] = None,
    **kwargs: Any,
) -> Any:
    """Audited entrypoint for Stage 7 (audio). Supports action callback or stage execution."""
    if callable(input_source_or_action):
        callback_kwargs = dict(kwargs)
        if output_path is not None:
            callback_kwargs["output_path"] = output_path
        return input_source_or_action(*args, **callback_kwargs)

    in_p = pathlib.Path(input_source_or_action).resolve()
    if not in_p.exists():
        raise ProcessingError(f"Input media for audio stage does not exist: {in_p}")

    run_dir = get_run_dir(run_id)
    audio_dir = run_dir / "artifacts" / "audio"
    out_media = pathlib.Path(output_path).resolve() if output_path else audio_dir / "audio_normalized.mp4"
    stats_json = audio_dir / "audio_stats.json"

    return process_audio_loudnorm(
        input_media=in_p,
        output_media=out_media,
        stats_json=stats_json,
        target_lufs=target_lufs,
    )
