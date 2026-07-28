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
from youtube_clipper.media_composer import (
    DEFAULT_BACKGROUND_MUSIC_VOLUME,
    MAX_OUTPUT_DURATION_SECONDS,
    compose_media,
    validate_media_options,
)
from youtube_clipper.processor import FFmpegProcessor
from youtube_clipper.video_formatter import VideoFormatter
from cortes.log import action_span, emit_skipped, run_context
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
    background_music_path: Optional[Union[str, Path]] = None,
    background_music_volume: Union[float, int] = DEFAULT_BACKGROUND_MUSIC_VOLUME,
    intro_image_path: Optional[Union[str, Path]] = None,
    intro_duration: Union[float, int] = 0.0,
    **kwargs: Any,
) -> str:
    """Execute the end-to-end media clipping pipeline."""
    plan = [
        {"action": "public.validate_input", "stage": "ingest"},
        {"action": "public.resolve_output", "stage": "ingest", "depends_on": "public.validate_input"},
        {"action": "public.download", "stage": "ingest", "depends_on": "public.validate_input"},
        {"action": "public.cut", "stage": "cut", "depends_on": "public.download"},
        {"action": "public.vertical_transform", "stage": "transform", "depends_on": "public.download"},
        {"action": "public.cleanup", "stage": "env"},
    ]
    requested_run_id = kwargs.pop("run_id", None)
    requested_request_id = kwargs.pop("request_id", None)
    with run_context(
        run_id=requested_run_id,
        request_id=requested_request_id,
        actions=plan,
        component="youtube_clipper.pipeline",
    ):
        return _run_pipeline_observed(
            input_source=input_source,
            start=start,
            end=end,
            duration=duration,
            output=output,
            fast=fast,
            verbose=verbose,
            vertical=vertical,
            background_music_path=background_music_path,
            background_music_volume=background_music_volume,
            intro_image_path=intro_image_path,
            intro_duration=intro_duration,
            **kwargs,
        )


def _run_pipeline_observed(
    input_source: Union[str, argparse.Namespace, Dict[str, Any], None] = None,
    start: Optional[Union[str, float, int]] = None,
    end: Optional[Union[str, float, int]] = None,
    duration: Optional[Union[str, float, int]] = None,
    output: Optional[Union[str, Path]] = None,
    fast: bool = False,
    verbose: bool = False,
    vertical: bool = False,
    background_music_path: Optional[Union[str, Path]] = None,
    background_music_volume: Union[float, int] = DEFAULT_BACKGROUND_MUSIC_VOLUME,
    intro_image_path: Optional[Union[str, Path]] = None,
    intro_duration: Union[float, int] = 0.0,
    **kwargs: Any,
) -> str:
    """Implementation of :func:`run_pipeline` inside an isolated audit run."""
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
    include_audio = kwargs.get("include_audio", True)

    with action_span(
        "ingest", "public.validate_input", component="youtube_clipper.pipeline",
        next_action="public.resolve_output", next_stage="ingest",
        input_data={"input_source": raw_input, "start": start, "end": end, "duration": duration},
    ):
        if raw_input is None or not str(raw_input).strip():
            raise ValidationError("Input source cannot be empty", field="input")
        clean_input = validate_input_source(str(raw_input))
        start_sec, end_sec = validate_time_range(start, end, duration)
        media_options = validate_media_options(
            background_music_path=background_music_path,
            background_music_volume=background_music_volume,
            intro_image_path=intro_image_path,
            intro_duration=intro_duration,
            include_audio=include_audio,
        )
        composed_duration = (end_sec - start_sec) + media_options.intro_duration
        if media_options.enabled and composed_duration > MAX_OUTPUT_DURATION_SECONDS:
            raise ValidationError(
                "The clip plus intro must be at most 59.9 seconds",
                field="time_range",
            )
        if media_options.enabled and not vertical:
            raise ValidationError(
                "Intro images and background music require vertical=True",
                field="vertical",
            )

    with action_span(
        "ingest", "public.resolve_output", component="youtube_clipper.pipeline",
        next_action="public.download", next_stage="ingest",
        input_data={"output": output},
    ):
        final_output_path = synthesize_output_path(
            clean_input, start_sec, end_sec, output
        )

    processor = FFmpegProcessor()
    temp_dir_obj = None

    try:
        youtube_source = is_youtube_url(clean_input)
        if youtube_source:
            with action_span(
                "ingest", "public.download", component="youtube_clipper.pipeline",
                next_action="public.vertical_transform" if vertical else "public.cut",
                next_stage="transform" if vertical else "cut",
            ):
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
            emit_skipped(
                "ingest", "public.download", "input is a local media file",
                component="youtube_clipper.pipeline",
                next_action="public.vertical_transform" if vertical else "public.cut",
                next_stage="transform" if vertical else "cut",
            )
            media_source_path = clean_input
            cut_start = start_sec
            cut_end = end_sec

        if vertical:
            emit_skipped(
                "cut", "public.cut", "vertical conversion performs the temporal cut",
                component="youtube_clipper.pipeline",
                next_action="public.vertical_transform", next_stage="transform",
            )
            with action_span(
                "transform", "public.vertical_transform",
                component="youtube_clipper.pipeline",
                next_action="public.cleanup", next_stage="env",
            ) as span:
                fmt_mode = kwargs.get("mode") or (
                    vars(input_source).get("mode", None) if isinstance(input_source, argparse.Namespace) else None
                ) or (
                    input_source.get("mode") if isinstance(input_source, dict) else None
                ) or "blur_background"
                blur_sigma = kwargs.get("blur_sigma", 12.0)
                crop_focus = kwargs.get("crop_focus", "center")
                overlay_text = kwargs.get("overlay_text")
                overlay_position = kwargs.get("overlay_position", "top")
                vertical_output_path = final_output_path
                if media_options.enabled:
                    if temp_dir_obj is None:
                        temp_dir_obj = tempfile.TemporaryDirectory(
                            prefix="yt_clipper_compose_"
                        )
                    vertical_output_path = str(
                        Path(temp_dir_obj.name) / "vertical_base.mp4"
                    )
                span.decision = {
                    "vertical": True,
                    "mode": fmt_mode,
                    "blur_sigma": blur_sigma,
                    "crop_focus": crop_focus,
                    "include_audio": include_audio,
                    "editorial_overlay": bool(overlay_text),
                    "overlay_position": overlay_position,
                    "background_music": bool(
                        media_options.background_music_path
                        and media_options.include_audio
                    ),
                    "background_music_volume": (
                        media_options.background_music_volume
                        if media_options.background_music_path
                        and media_options.include_audio
                        else None
                    ),
                    "intro_image": bool(
                        media_options.intro_image_path
                        and media_options.intro_duration > 0.0
                    ),
                    "intro_duration": media_options.intro_duration,
                }
                converted_path = VideoFormatter.convert_to_vertical(
                    input_path=media_source_path,
                    output_path=vertical_output_path,
                    mode=fmt_mode,
                    target_aspect="9:16",
                    start=cut_start,
                    end=cut_end,
                    sigma=blur_sigma,
                    crop_focus=crop_focus,
                    include_audio=include_audio,
                    overlay_text=overlay_text,
                    overlay_position=overlay_position,
                )
                if media_options.enabled:
                    converted_path = compose_media(
                        input_path=converted_path,
                        output_path=final_output_path,
                        background_music_path=media_options.background_music_path,
                        background_music_volume=media_options.background_music_volume,
                        intro_image_path=media_options.intro_image_path,
                        intro_duration=media_options.intro_duration,
                        include_audio=media_options.include_audio,
                    )
                span.set_evidence([converted_path])
            return str(Path(converted_path).resolve())
        else:
            emit_skipped(
                "transform", "public.vertical_transform", "vertical output was not requested",
                component="youtube_clipper.pipeline",
                next_action="public.cut", next_stage="cut",
            )
            with action_span(
                "cut", "public.cut", component="youtube_clipper.pipeline",
                next_action="public.cleanup", next_stage="env",
            ) as span:
                result_path = processor.cut_media(
                    input_path=media_source_path,
                    start=cut_start,
                    end=cut_end,
                    output_path=final_output_path,
                    fast_copy=fast,
                )
                span.set_evidence([result_path])
            return str(Path(result_path).resolve())

    finally:
        if temp_dir_obj is not None:
            with action_span(
                "env", "public.cleanup", component="youtube_clipper.pipeline"
            ):
                temp_dir_obj.cleanup()
        else:
            emit_skipped(
                "env", "public.cleanup", "no temporary workspace was created",
                component="youtube_clipper.pipeline",
            )


process_clip = run_pipeline
