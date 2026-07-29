"""Local FFmpeg composition for optional intro artwork and background music."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from cortes.log import audited, run_cmd
from youtube_clipper.exceptions import ProcessingError, ValidationError


PathValue = Union[str, os.PathLike[str]]

DEFAULT_BACKGROUND_MUSIC_VOLUME = 0.2
MAX_INTRO_DURATION_SECONDS = 5.0
MAX_OUTPUT_DURATION_SECONDS = 59.9
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FPS = 30


@dataclass(frozen=True)
class MediaCompositionOptions:
    """Validated, local-only media composition controls."""

    background_music_path: Optional[Path]
    background_music_volume: float
    intro_image_path: Optional[Path]
    intro_duration: float
    include_audio: bool

    @property
    def enabled(self) -> bool:
        """Return whether a physical composition pass is required."""
        return bool(
            (self.include_audio and self.background_music_path)
            or (self.intro_image_path and self.intro_duration > 0.0)
        )


def _local_file(value: Optional[PathValue], *, field: str) -> Optional[Path]:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be a local file path", field=field)
    try:
        raw_value = os.fspath(value)
    except TypeError as exc:
        raise ValidationError(
            f"{field} must be a local file path", field=field
        ) from exc
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValidationError(f"{field} cannot be empty", field=field)
    if "://" in raw_value:
        raise ValidationError(
            f"{field} must be a local file; remote URLs are not supported",
            field=field,
        )

    path = Path(raw_value).expanduser().resolve()
    if not path.exists():
        raise ValidationError(f"{field} does not exist: {path}", field=field)
    if not path.is_file():
        raise ValidationError(f"{field} must point to a file: {path}", field=field)
    return path


def _bounded_number(
    value: object, *, field: str, minimum: float, maximum: float
) -> float:
    if isinstance(value, bool):
        raise ValidationError(
            f"{field} must be a number between {minimum:g} and {maximum:g}",
            field=field,
        )
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"{field} must be a number between {minimum:g} and {maximum:g}",
            field=field,
        ) from exc
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValidationError(
            f"{field} must be between {minimum:g} and {maximum:g}",
            field=field,
        )
    return number


def validate_media_options(
    *,
    background_music_path: Optional[PathValue] = None,
    background_music_volume: object = DEFAULT_BACKGROUND_MUSIC_VOLUME,
    intro_image_path: Optional[PathValue] = None,
    intro_duration: object = 0.0,
    include_audio: bool = True,
) -> MediaCompositionOptions:
    """Validate composition values without downloading or opening any asset."""
    if not isinstance(include_audio, bool):
        raise ValidationError(
            "include_audio must be a boolean", field="include_audio"
        )

    music_path = _local_file(
        background_music_path, field="background_music_path"
    )
    image_path = _local_file(intro_image_path, field="intro_image_path")
    music_volume = _bounded_number(
        background_music_volume,
        field="background_music_volume",
        minimum=0.0,
        maximum=1.0,
    )
    image_duration = _bounded_number(
        intro_duration,
        field="intro_duration",
        minimum=0.0,
        maximum=MAX_INTRO_DURATION_SECONDS,
    )
    if image_duration > 0.0 and image_path is None:
        raise ValidationError(
            "intro_duration requires intro_image_path", field="intro_image_path"
        )

    return MediaCompositionOptions(
        background_music_path=music_path,
        background_music_volume=music_volume,
        intro_image_path=image_path,
        intro_duration=image_duration,
        include_audio=include_audio,
    )


def _seconds(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _normalized_video_filter(input_label: str, duration: float, output_label: str) -> str:
    return (
        f"{input_label}trim=duration={_seconds(duration)},setpts=PTS-STARTPTS,"
        f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
        f"setsar=1,settb=AVTB,fps={OUTPUT_FPS},format=yuv420p{output_label}"
    )


def build_composition_command(
    input_path: PathValue,
    output_path: PathValue,
    *,
    options: MediaCompositionOptions,
    source_has_audio: bool,
    ffmpeg_bin: str = "ffmpeg",
) -> List[str]:
    """Build the shell-free FFmpeg argv for a validated composition."""
    if not isinstance(options, MediaCompositionOptions):
        raise TypeError("options must be a MediaCompositionOptions instance")
    if not isinstance(source_has_audio, bool):
        raise ValidationError(
            "source_has_audio must be a boolean", field="source_has_audio"
        )
    if not isinstance(ffmpeg_bin, str) or not ffmpeg_bin.strip():
        raise ValidationError("ffmpeg_bin cannot be empty", field="ffmpeg_bin")

    source_path = _local_file(input_path, field="input_path")
    if source_path is None:  # Kept explicit for static type narrowing.
        raise ValidationError("input_path is required", field="input_path")
    try:
        raw_output = os.fspath(output_path)
    except TypeError as exc:
        raise ValidationError(
            "output_path must be a local file path", field="output_path"
        ) from exc
    if not isinstance(raw_output, str) or not raw_output.strip():
        raise ValidationError("output_path cannot be empty", field="output_path")
    if "://" in raw_output:
        raise ValidationError(
            "output_path must be a local file", field="output_path"
        )
    destination = Path(raw_output).expanduser().resolve()
    if destination == source_path:
        raise ValidationError(
            "output_path must differ from input_path", field="output_path"
        )

    intro_enabled = bool(
        options.intro_image_path and options.intro_duration > 0.0
    )
    music_enabled = bool(
        options.include_audio and options.background_music_path
    )
    main_duration = MAX_OUTPUT_DURATION_SECONDS - (
        options.intro_duration if intro_enabled else 0.0
    )

    cmd: List[str] = [
        ffmpeg_bin,
        "-y",
        "-nostdin",
        "-hide_banner",
        "-i",
        str(source_path),
    ]
    input_index = 1
    intro_index: Optional[int] = None
    music_index: Optional[int] = None
    if intro_enabled:
        intro_index = input_index
        input_index += 1
        cmd.extend(
            [
                "-loop",
                "1",
                "-framerate",
                str(OUTPUT_FPS),
                "-t",
                _seconds(options.intro_duration),
                "-i",
                str(options.intro_image_path),
            ]
        )
    if music_enabled:
        music_index = input_index
        cmd.extend(
            [
                "-stream_loop",
                "-1",
                "-i",
                str(options.background_music_path),
            ]
        )

    filters = [
        _normalized_video_filter("[0:v]", main_duration, "[mainv]")
    ]
    if intro_index is not None:
        filters.append(
            _normalized_video_filter(
                f"[{intro_index}:v]",
                options.intro_duration,
                "[introv]",
            )
        )
        filters.append("[introv][mainv]concat=n=2:v=1:a=0[vout]")
    else:
        filters.append("[mainv]null[vout]")

    base_audio_label: Optional[str] = None
    if options.include_audio and source_has_audio:
        filters.append(
            "[0:a]aformat=sample_fmts=fltp:sample_rates=48000:"
            "channel_layouts=stereo,"
            "apad,"
            f"atrim=duration={_seconds(main_duration)},"
            "asetpts=PTS-STARTPTS[maina]"
        )
        if intro_enabled:
            filters.append(
                "anullsrc=channel_layout=stereo:sample_rate=48000,"
                f"atrim=duration={_seconds(options.intro_duration)},"
                "asetpts=PTS-STARTPTS[introa]"
            )
            filters.append("[introa][maina]concat=n=2:v=0:a=1[basea]")
            base_audio_label = "[basea]"
        else:
            base_audio_label = "[maina]"

    output_audio_label: Optional[str] = base_audio_label
    if music_index is not None:
        filters.append(
            f"[{music_index}:a]aformat=sample_fmts=fltp:sample_rates=48000:"
            "channel_layouts=stereo,"
            f"volume={_seconds(options.background_music_volume)},"
            f"atrim=duration={_seconds(MAX_OUTPUT_DURATION_SECONDS)},"
            "asetpts=PTS-STARTPTS[musica]"
        )
        if base_audio_label:
            filters.append(
                f"{base_audio_label}[musica]"
                "amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
                "alimiter=limit=0.95[aout]"
            )
        else:
            filters.append("[musica]alimiter=limit=0.95[aout]")
        output_audio_label = "[aout]"

    cmd.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[vout]",
        ]
    )
    if output_audio_label and options.include_audio:
        cmd.extend(
            [
                "-map",
                output_audio_label,
                "-c:a",
                "aac",
                "-b:a",
                "192k",
            ]
        )
    else:
        cmd.append("-an")

    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-t",
            _seconds(MAX_OUTPUT_DURATION_SECONDS),
            "-shortest",
            str(destination),
        ]
    )
    return cmd


def _source_has_audio(input_path: Path, *, ffprobe_bin: str) -> bool:
    probe_cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "json",
        str(input_path),
    ]
    result = run_cmd(
        probe_cmd,
        stage="transform",
        action="media.probe_composition_audio",
    )
    if result.returncode != 0:
        raise ProcessingError(
            f"Unable to inspect source audio: {result.stderr}",
            returncode=result.returncode,
            stderr=result.stderr,
            cmd=probe_cmd,
        )
    try:
        payload = json.loads(result.stdout or "{}")
    except (TypeError, json.JSONDecodeError) as exc:
        raise ProcessingError(
            "Unable to parse source audio metadata",
            stderr=str(exc),
            cmd=probe_cmd,
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("streams", []), list):
        raise ProcessingError("Invalid source audio metadata", cmd=probe_cmd)
    return any(
        isinstance(stream, dict) and stream.get("codec_type") == "audio"
        for stream in payload.get("streams", [])
    )


@audited(
    stage="transform",
    action="media.compose_assets",
    component="youtube_clipper.media_composer",
)
def compose_media(
    input_path: PathValue,
    output_path: PathValue,
    *,
    background_music_path: Optional[PathValue] = None,
    background_music_volume: object = DEFAULT_BACKGROUND_MUSIC_VOLUME,
    intro_image_path: Optional[PathValue] = None,
    intro_duration: object = 0.0,
    include_audio: bool = True,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
) -> str:
    """Add optional intro/music to an existing vertical render using local assets."""
    options = validate_media_options(
        background_music_path=background_music_path,
        background_music_volume=background_music_volume,
        intro_image_path=intro_image_path,
        intro_duration=intro_duration,
        include_audio=include_audio,
    )
    source_path = _local_file(input_path, field="input_path")
    if source_path is None:
        raise ValidationError("input_path is required", field="input_path")
    source_has_audio = (
        _source_has_audio(source_path, ffprobe_bin=ffprobe_bin)
        if include_audio
        else False
    )
    cmd = build_composition_command(
        source_path,
        output_path,
        options=options,
        source_has_audio=source_has_audio,
        ffmpeg_bin=ffmpeg_bin,
    )
    destination = Path(os.fspath(output_path)).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    result = run_cmd(
        cmd,
        stage="transform",
        action="media.compose_assets.ffmpeg",
    )
    if (
        result.returncode != 0
        or not destination.exists()
        or destination.stat().st_size <= 1024
    ):
        raise ProcessingError(
            f"FFmpeg media composition failed: {result.stderr}",
            returncode=result.returncode,
            stderr=result.stderr,
            cmd=cmd,
        )
    return str(destination)
