"""Audio helpers shared by dashboard preview and final render profiles."""

from __future__ import annotations

import pathlib
import threading
from typing import Optional

from cortes.editorial import parse_loudnorm_measurement
from cortes.log import run_cmd
from youtube_clipper.exceptions import ProcessingError


def measure_loudnorm_filter(
    source_path: pathlib.Path,
    *,
    start_seconds: float,
    duration_seconds: float,
    cancel_event: Optional[threading.Event] = None,
) -> str:
    """Measure one selected interval and return a deterministic pass-two filter."""
    measured = run_cmd(
        [
            "ffmpeg",
            "-y",
            "-nostdin",
            "-hide_banner",
            "-ss",
            f"{start_seconds:.3f}",
            "-t",
            f"{duration_seconds:.3f}",
            "-i",
            str(source_path),
            "-vn",
            "-af",
            "loudnorm=I=-14:LRA=11:TP=-1.0:print_format=json",
            "-f",
            "null",
            "-",
        ],
        stage="render",
        cancel_event=cancel_event,
    )
    if cancel_event is not None and cancel_event.is_set():
        raise ProcessingError("Loudness measurement was cancelled")
    if measured.returncode != 0:
        raise ProcessingError(
            f"FFmpeg loudnorm measurement failed: {measured.stderr}"
        )
    stats = parse_loudnorm_measurement(measured.stderr)
    return (
        "loudnorm=I=-14:LRA=11:TP=-1.0:"
        f"measured_I={stats['input_i']}:"
        f"measured_LRA={stats['input_lra']}:"
        f"measured_TP={stats['input_tp']}:"
        f"measured_thresh={stats['input_thresh']}:"
        f"offset={stats['target_offset']}:linear=true"
    )
