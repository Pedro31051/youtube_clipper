"""Tests for physical media output validation."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from youtube_clipper.exceptions import ProcessingError
from youtube_clipper.media_validation import validate_media_output


def _valid_probe(*_args, **_kwargs):
    return SimpleNamespace(
        returncode=0,
        stdout=json.dumps(
            {
                "format": {"duration": "5.0"},
                "streams": [
                    {"codec_type": "video", "width": 1080, "height": 1920},
                    {"codec_type": "audio"},
                ],
            }
        ),
        stderr="",
    )


def _media_file(tmp_path: Path) -> Path:
    path = tmp_path / "output.mp4"
    path.write_bytes(b"media" * 300)
    return path


def test_validate_media_output_returns_measured_metadata(tmp_path: Path) -> None:
    result = validate_media_output(
        _media_file(tmp_path),
        expected_width=1080,
        expected_height=1920,
        expected_duration=5.0,
        require_audio=True,
        command_runner=_valid_probe,
    )

    assert result["duration"] == 5.0
    assert result["width"] == 1080
    assert result["height"] == 1920


def test_validate_media_output_rejects_undersized_file(tmp_path: Path) -> None:
    path = tmp_path / "broken.mp4"
    path.write_bytes(b"tiny")

    with pytest.raises(ProcessingError, match="undersized"):
        validate_media_output(path, command_runner=_valid_probe)


@pytest.mark.parametrize(
    "payload,error",
    [
        ({"format": {"duration": "0"}, "streams": []}, "positive duration"),
        (
            {
                "format": {"duration": "5"},
                "streams": [
                    {"codec_type": "video", "width": 720, "height": 1280}
                ],
            },
            "width is 720",
        ),
    ],
)
def test_validate_media_output_rejects_invalid_probe_metadata(
    tmp_path: Path, payload: dict, error: str
) -> None:
    def probe(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

    with pytest.raises(ProcessingError, match=error):
        validate_media_output(
            _media_file(tmp_path),
            expected_width=1080 if "width" in error else None,
            command_runner=probe,
        )


def test_validate_media_output_rejects_ffprobe_failure(tmp_path: Path) -> None:
    def failed_probe(*_args, **_kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="invalid data")

    with pytest.raises(ProcessingError, match="ffprobe failed"):
        validate_media_output(_media_file(tmp_path), command_runner=failed_probe)


def test_validate_media_output_rejects_truncated_duration(tmp_path: Path) -> None:
    with pytest.raises(ProcessingError, match="expected 12.000s"):
        validate_media_output(
            _media_file(tmp_path),
            expected_duration=12.0,
            duration_tolerance=0.5,
            command_runner=_valid_probe,
        )
