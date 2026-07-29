"""Physical validation helpers for generated media artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from cortes.log import run_cmd
from youtube_clipper.exceptions import ProcessingError


CommandRunner = Callable[..., Any]


def validate_media_output(
    media_path: Union[str, Path],
    *,
    expected_width: Optional[int] = None,
    expected_height: Optional[int] = None,
    expected_duration: Optional[float] = None,
    duration_tolerance: float = 1.0,
    require_audio: bool = False,
    min_size_bytes: int = 1024,
    stage: str = "verify",
    command_runner: CommandRunner = run_cmd,
) -> Dict[str, Any]:
    """Validate a media artifact using ffprobe instead of trusting FFmpeg exit 0."""
    path = Path(media_path)
    if not path.exists() or not path.is_file() or path.stat().st_size <= min_size_bytes:
        raise ProcessingError(
            f"Media output is empty or undersized, missing, or not a file: {path}",
            exit_code=4,
        )

    probe = command_runner(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-show_entries",
            "stream=codec_type,width,height",
            "-of",
            "json",
            str(path),
        ],
        stage=stage,
    )
    if probe.returncode != 0:
        raise ProcessingError(
            f"ffprobe failed to validate media output: {path}",
            returncode=probe.returncode,
            stderr=probe.stderr,
            exit_code=4,
        )

    try:
        metadata = json.loads(probe.stdout)
        duration = float(metadata.get("format", {}).get("duration", 0.0))
        streams = metadata.get("streams", [])
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ProcessingError(
            f"ffprobe returned invalid metadata for media output: {path}",
            stderr=probe.stderr,
            exit_code=4,
        ) from exc

    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        None,
    )
    if duration <= 0.0 or video_stream is None:
        raise ProcessingError(
            f"Media output has no positive duration or video stream: {path}",
            exit_code=4,
        )
    if require_audio and not any(
        stream.get("codec_type") == "audio" for stream in streams
    ):
        raise ProcessingError(f"Media output has no audio stream: {path}", exit_code=4)

    width = int(video_stream.get("width", 0) or 0)
    height = int(video_stream.get("height", 0) or 0)
    if expected_width is not None and width != int(expected_width):
        raise ProcessingError(
            f"Media output width is {width}, expected {expected_width}: {path}",
            exit_code=4,
        )
    if expected_height is not None and height != int(expected_height):
        raise ProcessingError(
            f"Media output height is {height}, expected {expected_height}: {path}",
            exit_code=4,
        )
    if expected_duration is not None and abs(duration - float(expected_duration)) > float(
        duration_tolerance
    ):
        raise ProcessingError(
            f"Media output duration is {duration:.3f}s, expected "
            f"{float(expected_duration):.3f}s ± {float(duration_tolerance):.3f}s: {path}",
            exit_code=4,
        )

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "streams": streams,
        "size_bytes": path.stat().st_size,
    }
