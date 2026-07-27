"""High-level orchestration pipeline for youtube_clipper.

Connects CLI arguments, input validation, YouTube downloading,
FFmpeg media processing, vertical video layout transformation, and output delivery into a unified workflow.
"""

from __future__ import annotations

import argparse
import contextlib
import tempfile
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

from youtube_clipper.downloader import YouTubeDownloader
from youtube_clipper.exceptions import ValidationError
from youtube_clipper.processor import FFmpegProcessor
from youtube_clipper.video_formatter import VideoFormatter
from youtube_clipper.validator import (
    _YOUTUBE_URL_REGEX,
    is_youtube_url,
    validate_input_source,
    validate_time_range,
)


def synthesize_output_path(
    input_source: str,
    start_sec: float,
    end_sec: float,
    output: Optional[Union[str, Path]] = None,
) -> str:
    """Synthesize and resolve final output destination Path."""
    clean_input = str(input_source).strip()

    if is_youtube_url(clean_input):
        match = _YOUTUBE_URL_REGEX.match(clean_input)
        base_id = match.group(1) if match else "youtube_video"
    else:
        base_id = Path(clean_input).stem

    start_str = f"{start_sec:g}"
    end_str = f"{end_sec:g}"
    default_filename = f"clip_{base_id}_{start_str}_{end_str}.mp4"

    if output is None or not str(output).strip():
        return str((Path.cwd() / default_filename).resolve())

    out_str = str(output).strip()
    out_path = Path(out_str).expanduser()

    is_dir_target = out_path.is_dir() or out_str.endswith(("/", "\\"))

    if is_dir_target:
        out_path.mkdir(parents=True, exist_ok=True)
        return str((out_path / default_filename).resolve())

    out_path.parent.mkdir(parents=True, exist_ok=True)
    return str(out_path.resolve())


_resolve_output_path = synthesize_output_path


def run_pipeline(
    input_source: Union[str, argparse.Namespace, Dict[str, Any], None] = None,
    start: Optional[Union[str, float, int]] = None,
    end: Optional[Union[str, float, int]] = None,
    duration: Optional[Union[str, float, int]] = None,
    output: Optional[Union[str, Path]] = None,
    fast: bool = False,
    verbose: bool = False,
    vertical: bool = False,
    **kwargs: Any,
) -> str:
    """Execute the end-to-end media clipping pipeline."""
    raw_input = input_source
    if isinstance(input_source, argparse.Namespace):
        ns_dict = vars(input_source)
        raw_input = ns_dict.get("input") or ns_dict.get("input_source")
        start = start if start is not None else ns_dict.get("start")
        end = end if end is not None else ns_dict.get("end")
        duration = (
            duration
            if duration is not None
            else ns_dict.get("duration")
        )
        output = output if output is not None else ns_dict.get("output")
        fast = fast or ns_dict.get("fast", False)
        verbose = verbose or ns_dict.get("verbose", False)
        vertical = vertical or ns_dict.get("vertical", False)
    elif isinstance(input_source, dict):
        raw_input = input_source.get("input") or input_source.get("input_source")
        start = start if start is not None else input_source.get("start")
        end = end if end is not None else input_source.get("end")
        duration = duration if duration is not None else input_source.get("duration")
        output = output if output is not None else input_source.get("output")
        fast = fast or input_source.get("fast", False)
        verbose = verbose or input_source.get("verbose", False)
        vertical = vertical or input_source.get("vertical", False)

    if raw_input is None and "input" in kwargs:
        raw_input = kwargs["input"]
    if start is None and "start" in kwargs:
        start = kwargs["start"]
    if end is None and "end" in kwargs:
        end = kwargs["end"]
    if duration is None and "duration" in kwargs:
        duration = kwargs["duration"]
    if output is None and "output" in kwargs:
        output = kwargs["output"]
    if not fast and "fast" in kwargs:
        fast = bool(kwargs["fast"])
    if not verbose and "verbose" in kwargs:
        verbose = bool(kwargs["verbose"])
    if not vertical and "vertical" in kwargs:
        vertical = bool(kwargs["vertical"])

    if raw_input is None or not str(raw_input).strip():
        raise ValidationError("Input source cannot be empty", field="input")

    clean_input = validate_input_source(str(raw_input))
    start_sec, end_sec = validate_time_range(start, end, duration)
    final_output_path = synthesize_output_path(
        clean_input, start_sec, end_sec, output
    )

    processor = FFmpegProcessor()
    temp_dir_obj = None

    try:
        youtube_source = is_youtube_url(clean_input)
        if youtube_source:
            downloader = YouTubeDownloader()
            temp_dir_obj = tempfile.TemporaryDirectory(prefix="yt_clipper_")
            temp_dir = Path(temp_dir_obj.name)
            media_source_path = downloader.download_segment(
                url=clean_input,
                start=start_sec,
                end=end_sec,
                output_dir=temp_dir,
            )
            # download_segment already consumes the absolute source offset.
            cut_start = 0.0
            cut_end = end_sec - start_sec
        else:
            media_source_path = clean_input
            cut_start = start_sec
            cut_end = end_sec

        if vertical:
            fmt_mode = kwargs.get("mode") or (
                vars(input_source).get("mode", None) if isinstance(input_source, argparse.Namespace) else None
            ) or (
                input_source.get("mode") if isinstance(input_source, dict) else None
            ) or "blur_background"
            converted_path = VideoFormatter.convert_to_vertical(
                input_path=media_source_path,
                output_path=final_output_path,
                mode=fmt_mode,
                target_aspect="9:16",
                start=cut_start,
                end=cut_end,
            )
            return str(Path(converted_path).resolve())
        else:
            result_path = processor.cut_media(
                input_path=media_source_path,
                start=cut_start,
                end=cut_end,
                output_path=final_output_path,
                fast_copy=fast,
            )
            return str(Path(result_path).resolve())

    finally:
        if temp_dir_obj is not None:
            with contextlib.suppress(Exception):
                temp_dir_obj.cleanup()


process_clip = run_pipeline
