"""Validation engine for YouTube Clipper.

Provides functions for parsing timestamps, validating time ranges,
detecting YouTube URLs, and verifying input video sources.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Union

from youtube_clipper.exceptions import ValidationError

# Regex matching valid YouTube video URLs (watch, shorts, embed, live, short-url)
_YOUTUBE_URL_REGEX = re.compile(
    r"^(?:https?://)?"  # Optional http or https protocol
    r"(?:[a-zA-Z0-9-]+\.)?"  # Optional subdomain (e.g. www, m, music, gaming, tv, kids)
    r"(?:"
    r"youtube\.com/(?:watch\?(?:[^\s#]*&)?v=|shorts/|embed/|live/)"
    r"|"
    r"youtu\.be/"
    r"|"
    r"youtube-nocookie\.com/embed/"
    r")"
    r"([a-zA-Z0-9_-]{11})"  # 11-character video ID
    r"(?:[?&/#].*)?$",  # Optional trailing parameters
    re.IGNORECASE,
)


def parse_timestamp(ts_str: Union[str, float, int]) -> float:
    """Parse a timestamp into seconds as a float.

    Supported formats:
        - "HH:MM:SS" or "HH:MM:SS.sss"
        - "MM:SS" or "MM:SS.sss"
        - "SS" or "SS.sss" (numeric strings)
        - Numeric float or int (e.g. 120, 45.5)

    Args:
        ts_str: The timestamp string or numeric value.

    Returns:
        The timestamp converted to float seconds.

    Raises:
        ValidationError: If format is invalid, values are out of bounds,
            timestamp is negative, non-finite (NaN/Inf), boolean, or malformed.
    """
    if ts_str is None:
        raise ValidationError("Timestamp value cannot be None", field="timestamp")

    if isinstance(ts_str, bool):
        raise ValidationError("Boolean values are not valid timestamps", field="timestamp")

    if isinstance(ts_str, (int, float)):
        val = float(ts_str)
        if not math.isfinite(val):
            raise ValidationError(f"Timestamp must be a finite number: {ts_str}", field="timestamp")
        if val < 0:
            raise ValidationError(f"Timestamp cannot be negative: {val}", field="timestamp")
        return val

    if not isinstance(ts_str, str):
        raise ValidationError(f"Invalid timestamp type: {type(ts_str).__name__}", field="timestamp")

    cleaned = ts_str.strip()
    if not cleaned:
        raise ValidationError("Timestamp string cannot be empty", field="timestamp")

    if cleaned.startswith("-"):
        raise ValidationError(f"Timestamp cannot be negative: '{cleaned}'", field="timestamp")

    if ":" in cleaned:
        parts = cleaned.split(":")
        if len(parts) > 3 or len(parts) < 2:
            raise ValidationError(f"Invalid timestamp format: '{cleaned}'", field="timestamp")

        for part in parts:
            if not part or any(c.isspace() for c in part):
                raise ValidationError(f"Invalid timestamp component in '{cleaned}'", field="timestamp")

        try:
            if len(parts) == 3:  # HH:MM:SS
                hh = int(parts[0])
                mm = int(parts[1])
                ss = float(parts[2])

                if not math.isfinite(ss):
                    raise ValidationError(
                        f"Seconds component must be a finite number in '{cleaned}'", field="timestamp"
                    )

                if hh < 0:
                    raise ValidationError(f"Hours component cannot be negative in '{cleaned}'", field="timestamp")
                if mm < 0 or mm >= 60:
                    raise ValidationError(
                        f"Minutes component must be less than 60 in HH:MM:SS format: '{cleaned}'",
                        field="timestamp",
                    )
                if ss < 0.0 or ss >= 60.0:
                    raise ValidationError(
                        f"Seconds component must be less than 60 in HH:MM:SS format: '{cleaned}'",
                        field="timestamp",
                    )

                total = hh * 3600.0 + mm * 60.0 + ss
                if not math.isfinite(total):
                    raise ValidationError(f"Timestamp value overflow in '{cleaned}'", field="timestamp")
                return total

            else:  # MM:SS
                mm = int(parts[0])
                ss = float(parts[1])

                if not math.isfinite(ss):
                    raise ValidationError(
                        f"Seconds component must be a finite number in '{cleaned}'", field="timestamp"
                    )

                if mm < 0:
                    raise ValidationError(f"Minutes component cannot be negative in '{cleaned}'", field="timestamp")
                if ss < 0.0 or ss >= 60.0:
                    raise ValidationError(
                        f"Seconds component must be less than 60 in MM:SS format: '{cleaned}'",
                        field="timestamp",
                    )

                total = mm * 60.0 + ss
                if not math.isfinite(total):
                    raise ValidationError(f"Timestamp value overflow in '{cleaned}'", field="timestamp")
                return total

        except ValueError as exc:
            raise ValidationError(f"Invalid numeric components in timestamp: '{cleaned}'", field="timestamp") from exc

    # Raw seconds float/int string
    try:
        val = float(cleaned)
        if not math.isfinite(val):
            raise ValidationError(f"Timestamp must be a finite number: '{cleaned}'", field="timestamp")
        if val < 0:
            raise ValidationError(f"Timestamp cannot be negative: {val}", field="timestamp")
        return val
    except ValueError as exc:
        raise ValidationError(f"Invalid timestamp format: '{cleaned}'", field="timestamp") from exc


def validate_time_range(
    start_str: Union[str, float, int, None] = None,
    end_str: Union[str, float, int, None] = None,
    duration_str: Union[str, float, int, None] = None,
) -> tuple[float, float]:
    """Compute and validate start and end time seconds.

    Ensures 0 <= start < end.
    Enforces mutual exclusivity between end_str and duration_str.

    Args:
        start_str: Optional start timestamp (default 0.0 if None/empty).
        end_str: Optional end timestamp.
        duration_str: Optional clip duration timestamp.

    Returns:
        Tuple of (start_seconds, end_seconds) as floats.

    Raises:
        ValidationError: If range is invalid, negative, non-finite, or if both
            end_str and duration_str are specified.
    """
    if isinstance(start_str, bool) or isinstance(end_str, bool) or isinstance(duration_str, bool):
        raise ValidationError("Boolean values are not valid timestamps", field="time_range")

    has_end = end_str is not None and (not isinstance(end_str, str) or bool(end_str.strip()))
    has_duration = duration_str is not None and (not isinstance(duration_str, str) or bool(duration_str.strip()))

    if has_end and has_duration:
        raise ValidationError("Cannot specify both end time and duration parameters", field="time_range")

    # Compute start
    if start_str is None or (isinstance(start_str, str) and not start_str.strip()):
        start = 0.0
    else:
        start = parse_timestamp(start_str)

    # Compute end
    if has_end:
        end = parse_timestamp(end_str)  # type: ignore[arg-type]
    elif has_duration:
        duration = parse_timestamp(duration_str)  # type: ignore[arg-type]
        if duration <= 0.0:
            raise ValidationError("Clip duration must be strictly greater than zero", field="duration")
        end = start + duration
    else:
        raise ValidationError("Either end time (--end) or duration (--duration) must be specified", field="time_range")

    if not math.isfinite(start):
        raise ValidationError(f"Start timestamp must be a finite number: {start}", field="start")

    if not math.isfinite(end):
        raise ValidationError(f"End timestamp must be a finite number: {end}", field="end")

    if start < 0.0:
        raise ValidationError(f"Start timestamp cannot be negative: {start}", field="start")

    if start >= end:
        raise ValidationError(
            f"Start time ({start}s) must be strictly less than end time ({end}s)",
            field="time_range",
        )

    return (start, end)


def is_youtube_url(input_str: str) -> bool:
    """Check if input_str matches a supported YouTube URL format.

    Args:
        input_str: The string to test.

    Returns:
        True if input_str is a valid YouTube video URL, False otherwise.
    """
    if not input_str or not isinstance(input_str, str):
        return False
    return bool(_YOUTUBE_URL_REGEX.match(input_str.strip()))


def validate_input_source(input_str: str) -> str:
    """Validate input video source string.

    Must be either a valid YouTube URL or an existing local video file.

    Args:
        input_str: The input source string.

    Returns:
        The normalized input source string.

    Raises:
        ValidationError: If input_str is empty or neither a valid YouTube
            URL nor an existing local file.
    """
    if not input_str or not isinstance(input_str, str):
        raise ValidationError("Input source cannot be empty", field="input")

    clean_input = input_str.strip()
    if not clean_input:
        raise ValidationError("Input source cannot be empty", field="input")

    # Check if YouTube URL
    if is_youtube_url(clean_input):
        return clean_input

    # Check if existing local file
    file_path = Path(clean_input)
    if file_path.exists():
        if file_path.is_dir():
            raise ValidationError(f"Input source is a directory, not a video file: '{clean_input}'", field="input")
        return clean_input

    raise ValidationError(
        f"Invalid input source: '{clean_input}'. Must be a valid YouTube URL or an existing local video file.",
        field="input",
    )

