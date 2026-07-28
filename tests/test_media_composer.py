"""Offline tests for local intro artwork and background music composition."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from youtube_clipper.exceptions import ValidationError
from youtube_clipper.media_composer import (
    MAX_OUTPUT_DURATION_SECONDS,
    build_composition_command,
    compose_media,
    validate_media_options,
)
from youtube_clipper.pipeline import run_pipeline


def _asset(path: Path, payload: bytes = b"local-asset") -> Path:
    path.write_bytes(payload)
    return path


class TestMediaOptionValidation:
    def test_accepts_and_resolves_local_assets(self, tmp_path: Path) -> None:
        music = _asset(tmp_path / "music track.mp3")
        image = _asset(tmp_path / "intro image.png")

        options = validate_media_options(
            background_music_path=music,
            background_music_volume=0.35,
            intro_image_path=image,
            intro_duration=2.5,
            include_audio=True,
        )

        assert options.background_music_path == music.resolve()
        assert options.background_music_volume == 0.35
        assert options.intro_image_path == image.resolve()
        assert options.intro_duration == 2.5
        assert options.enabled is True

    @pytest.mark.parametrize(
        ("override", "field"),
        [
            ({"background_music_volume": -0.01}, "background_music_volume"),
            ({"background_music_volume": 1.01}, "background_music_volume"),
            ({"background_music_volume": float("nan")}, "background_music_volume"),
            ({"background_music_volume": True}, "background_music_volume"),
            ({"intro_duration": -0.01}, "intro_duration"),
            ({"intro_duration": 5.01}, "intro_duration"),
            ({"intro_duration": float("inf")}, "intro_duration"),
            ({"include_audio": "yes"}, "include_audio"),
        ],
    )
    def test_rejects_invalid_values(
        self, override: dict[str, object], field: str
    ) -> None:
        with pytest.raises(ValidationError) as exc_info:
            validate_media_options(**override)  # type: ignore[arg-type]
        assert exc_info.value.field == field

    def test_rejects_remote_or_missing_assets(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="remote URLs"):
            validate_media_options(
                background_music_path="https://example.invalid/music.mp3"
            )
        with pytest.raises(ValidationError, match="does not exist"):
            validate_media_options(intro_image_path=tmp_path / "missing.png")

    def test_positive_intro_duration_requires_image(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            validate_media_options(intro_duration=1.0)
        assert exc_info.value.field == "intro_image_path"

    def test_muted_music_alone_does_not_require_composition(
        self, tmp_path: Path
    ) -> None:
        music = _asset(tmp_path / "music.mp3")
        options = validate_media_options(
            background_music_path=music,
            include_audio=False,
        )
        assert options.enabled is False


class TestCompositionCommand:
    def test_builds_intro_concat_and_looped_music_mix(
        self, tmp_path: Path
    ) -> None:
        source = _asset(tmp_path / "vertical source.mp4")
        music = _asset(tmp_path / "music track.mp3")
        image = _asset(tmp_path / "intro image.png")
        output = tmp_path / "final output.mp4"
        options = validate_media_options(
            background_music_path=music,
            background_music_volume=0.35,
            intro_image_path=image,
            intro_duration=2.5,
        )

        command = build_composition_command(
            source,
            output,
            options=options,
            source_has_audio=True,
        )

        assert isinstance(command, list)
        assert command[0] == "ffmpeg"
        assert str(source.resolve()) in command
        assert str(image.resolve()) in command
        assert str(music.resolve()) in command
        assert "-loop" in command
        assert "-stream_loop" in command
        graph = command[command.index("-filter_complex") + 1]
        assert "trim=duration=57.4" in graph
        assert "concat=n=2:v=1:a=0" in graph
        assert "anullsrc=" in graph
        assert "apad,atrim=" in graph
        assert "volume=0.35" in graph
        assert "amix=inputs=2:duration=first" in graph
        assert command[-4:] == [
            "-t",
            str(MAX_OUTPUT_DURATION_SECONDS),
            "-shortest",
            str(output.resolve()),
        ]

    def test_include_audio_false_omits_original_and_music(
        self, tmp_path: Path
    ) -> None:
        source = _asset(tmp_path / "source.mp4")
        music = _asset(tmp_path / "music.mp3")
        image = _asset(tmp_path / "intro.png")
        output = tmp_path / "muted.mp4"
        options = validate_media_options(
            background_music_path=music,
            intro_image_path=image,
            intro_duration=1.0,
            include_audio=False,
        )

        command = build_composition_command(
            source,
            output,
            options=options,
            source_has_audio=True,
        )

        graph = command[command.index("-filter_complex") + 1]
        assert "-an" in command
        assert str(music.resolve()) not in command
        assert "[0:a]" not in graph
        assert "amix=" not in graph
        assert "concat=n=2:v=1:a=0" in graph

    def test_output_cannot_overwrite_input(self, tmp_path: Path) -> None:
        source = _asset(tmp_path / "source.mp4")
        options = validate_media_options()
        with pytest.raises(ValidationError) as exc_info:
            build_composition_command(
                source,
                source,
                options=options,
                source_has_audio=False,
            )
        assert exc_info.value.field == "output_path"


class TestCompositionExecution:
    def test_ffprobe_and_ffmpeg_use_audited_list_gateway(
        self, tmp_path: Path
    ) -> None:
        source = _asset(tmp_path / "source.mp4")
        music = _asset(tmp_path / "music.mp3")
        output = tmp_path / "output.mp4"
        calls: list[tuple[list[str], dict[str, Any]]] = []

        def fake_run_cmd(
            command: list[str], **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            calls.append((command, kwargs))
            if Path(command[0]).name == "ffprobe":
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=json.dumps(
                        {"streams": [{"codec_type": "audio"}]}
                    ),
                    stderr="",
                )
            output.write_bytes(b"composed" * 256)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with patch(
            "youtube_clipper.media_composer.run_cmd", side_effect=fake_run_cmd
        ):
            result = compose_media(
                source,
                output,
                background_music_path=music,
                background_music_volume=0.25,
            )

        assert result == str(output.resolve())
        assert [Path(command[0]).name for command, _ in calls] == [
            "ffprobe",
            "ffmpeg",
        ]
        assert all(isinstance(command, list) for command, _ in calls)
        assert all(kwargs["stage"] == "transform" for _, kwargs in calls)

    def test_pipeline_preserves_vertical_filter_before_composition(
        self,
        dummy_video_file: Path,
        tmp_path: Path,
        mock_ffmpeg: Any,
    ) -> None:
        music = _asset(tmp_path / "music.mp3")
        image = _asset(tmp_path / "intro.png")
        output = tmp_path / "composed.mp4"

        result = run_pipeline(
            input_source=dummy_video_file,
            start=0,
            end=1,
            output=output,
            vertical=True,
            mode="crop_center",
            crop_focus="right",
            overlay_text="Contexto",
            background_music_path=music,
            background_music_volume=0.3,
            intro_image_path=image,
            intro_duration=1.0,
        )

        ffmpeg_commands = [
            call.args[0]
            for call in mock_ffmpeg.run.call_args_list
            if call.args
            and isinstance(call.args[0], list)
            and Path(call.args[0][0]).name == "ffmpeg"
        ]
        vertical_command = next(
            command for command in ffmpeg_commands if "-vf" in command
        )
        composition_command = next(
            command for command in ffmpeg_commands if "-filter_complex" in command
        )
        vertical_filter = vertical_command[vertical_command.index("-vf") + 1]
        assert "crop=ih*9/16:ih:iw-ow:0" in vertical_filter
        assert "drawtext=" in vertical_filter
        assert "-stream_loop" in composition_command
        assert "concat=n=2:v=1:a=0" in composition_command[
            composition_command.index("-filter_complex") + 1
        ]
        assert result == str(output.resolve())
        assert output.exists()

    def test_pipeline_rejects_composition_that_would_be_truncated(
        self,
        dummy_video_file: Path,
        tmp_path: Path,
    ) -> None:
        image = _asset(tmp_path / "intro.png")

        with pytest.raises(ValidationError) as exc_info:
            run_pipeline(
                input_source=dummy_video_file,
                start=0,
                end=58,
                output=tmp_path / "too-long.mp4",
                vertical=True,
                mode="crop_center",
                overlay_text="Contexto",
                intro_image_path=image,
                intro_duration=2.0,
            )

        assert exc_info.value.field == "time_range"
        assert "59.9" in str(exc_info.value)
