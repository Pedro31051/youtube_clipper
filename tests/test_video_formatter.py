"""
tests/test_video_formatter.py - Unit and integration tests for VideoFormatter.
Tests 9:16 vertical video filter generation (blur background and center crop)
and FFmpeg conversion execution.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from youtube_clipper.exceptions import ProcessingError
from youtube_clipper.video_formatter import VideoFormatter


class TestVideoFormatterFilterBuilder:
    """Test suite for build_vertical_filter filter graph generation."""

    def test_build_vertical_filter_blur_background(self) -> None:
        """Verify filter string for blur_background mode."""
        filter_str = VideoFormatter.build_vertical_filter(1080, 1920, "blur_background")
        assert "split[bg][fg];" in filter_str
        assert "scale=270:480" in filter_str
        assert "gblur=sigma=12.0" in filter_str
        assert "[fg]scale=1080:-2[scaled_fg];" in filter_str
        assert "overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2" in filter_str

    def test_build_vertical_filter_split_blur_alias(self) -> None:
        """Verify filter string for split_blur mode alias."""
        filter_str = VideoFormatter.build_vertical_filter(1080, 1920, "split_blur")
        assert "split[bg][fg];" in filter_str
        assert "gblur=sigma=12.0" in filter_str

    def test_build_vertical_filter_crop_center(self) -> None:
        """Verify filter string for crop_center mode."""
        filter_str = VideoFormatter.build_vertical_filter(1080, 1920, "crop_center")
        assert "crop=ih*9/16:ih:(iw-ow)/2:0,scale=1080:1920" in filter_str

    def test_build_vertical_filter_custom_dimensions(self) -> None:
        """Verify filter string generation with custom resolution dimensions."""
        filter_str = VideoFormatter.build_vertical_filter(720, 1280, "crop_center")
        assert "scale=720:1280" in filter_str

    def test_build_vertical_filter_string_overload(self) -> None:
        """Verify string overload where mode is passed as first positional parameter."""
        filter_str = VideoFormatter.build_vertical_filter("crop_center")
        assert "crop=ih*9/16:ih:(iw-ow)/2:0,scale=1080:1920" in filter_str

    @pytest.mark.parametrize(
        ("focus", "expected_crop"),
        [
            ("left", "crop=ih*9/16:ih:0:0"),
            ("center", "crop=ih*9/16:ih:(iw-ow)/2:0"),
            ("right", "crop=ih*9/16:ih:iw-ow:0"),
        ],
    )
    def test_build_vertical_filter_crop_focus(
        self, focus: str, expected_crop: str
    ) -> None:
        filter_str = VideoFormatter.build_vertical_filter(
            mode="crop_center", crop_focus=focus
        )
        assert expected_crop in filter_str

    def test_build_vertical_filter_adds_editorial_overlay(self) -> None:
        filter_str = VideoFormatter.build_vertical_filter(
            mode="blur_background",
            overlay_text="Análise: fato, contexto",
            overlay_position="bottom",
        )
        assert "drawbox=" in filter_str
        assert "drawtext=" in filter_str
        assert r"Análise\: fato\, contexto" in filter_str
        assert "y=h-text_h-150" in filter_str

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"crop_focus": "invalid"}, "Crop focus"),
            ({"overlay_position": "middle"}, "Overlay position"),
            ({"sigma": 100}, "Blur sigma"),
        ],
    )
    def test_build_vertical_filter_rejects_invalid_controls(
        self, kwargs: dict[str, object], message: str
    ) -> None:
        with pytest.raises(ValueError, match=message):
            VideoFormatter.build_vertical_filter(**kwargs)

    def test_build_vertical_filter_invalid_mode_raises_value_error(self) -> None:
        """Verify ValueError is raised when an unsupported mode name is provided."""
        with pytest.raises(ValueError, match="Unsupported vertical format mode"):
            VideoFormatter.build_vertical_filter(1080, 1920, "invalid_mode_name")


class TestVideoFormatterConversion:
    """Test suite for convert_to_vertical FFmpeg conversion execution."""

    def test_convert_to_vertical_blur_background(
        self, dummy_video_file: Path, tmp_media_dir: Path, mock_ffmpeg: pytest.FixtureRequest
    ) -> None:
        """Test vertical conversion with blur_background mode returning output path."""
        output_path = str(tmp_media_dir / "vertical_blur.mp4")
        result_path = VideoFormatter.convert_to_vertical(
            input_path=str(dummy_video_file),
            output_path=output_path,
            mode="blur_background",
        )
        assert result_path == output_path
        out_file = Path(result_path)
        assert out_file.exists()
        assert out_file.stat().st_size > 1000

    def test_convert_to_vertical_crop_center(
        self, dummy_video_file: Path, tmp_media_dir: Path, mock_ffmpeg: pytest.FixtureRequest
    ) -> None:
        """Test vertical conversion with crop_center mode returning output path."""
        output_path = str(tmp_media_dir / "vertical_crop.mp4")
        result_path = VideoFormatter.convert_to_vertical(
            input_path=str(dummy_video_file),
            output_path=output_path,
            mode="crop_center",
        )
        assert result_path == output_path
        out_file = Path(result_path)
        assert out_file.exists()
        assert out_file.stat().st_size > 1000

    def test_convert_to_vertical_applies_mute_and_overlay(
        self,
        dummy_video_file: Path,
        tmp_media_dir: Path,
        mock_ffmpeg: pytest.FixtureRequest,
    ) -> None:
        output_path = str(tmp_media_dir / "vertical_muted_overlay.mp4")
        VideoFormatter.convert_to_vertical(
            input_path=str(dummy_video_file),
            output_path=output_path,
            mode="crop_center",
            crop_focus="right",
            include_audio=False,
            overlay_text="Contexto original",
            overlay_position="top",
        )
        command = mock_ffmpeg.last_command
        assert command is not None
        assert "-an" in command
        assert "-c:a" not in command
        filter_str = command[command.index("-vf") + 1]
        assert "crop=ih*9/16:ih:iw-ow:0" in filter_str
        assert "drawtext=" in filter_str
        assert "textfile=" in filter_str
        assert not list(tmp_media_dir.glob(".overlay_*.txt"))

    def test_convert_to_vertical_rejects_non_boolean_audio_control(
        self, dummy_video_file: Path, tmp_media_dir: Path
    ) -> None:
        with pytest.raises(ValueError, match="include_audio must be a boolean"):
            VideoFormatter.convert_to_vertical(
                input_path=str(dummy_video_file),
                output_path=str(tmp_media_dir / "invalid_audio.mp4"),
                include_audio="yes",  # type: ignore[arg-type]
            )

    def test_convert_to_vertical_non_existent_input_raises_file_not_found(
        self, tmp_media_dir: Path
    ) -> None:
        """Test that converting a non-existent input video raises FileNotFoundError."""
        non_existent_path = str(tmp_media_dir / "does_not_exist.mp4")
        output_path = str(tmp_media_dir / "out.mp4")
        with pytest.raises(FileNotFoundError, match="Input file not found"):
            VideoFormatter.convert_to_vertical(
                input_path=non_existent_path,
                output_path=output_path,
                mode="blur_background",
            )

    def test_convert_to_vertical_invalid_mode_raises_value_error(
        self, dummy_video_file: Path, tmp_media_dir: Path
    ) -> None:
        """Test that passing an invalid mode to convert_to_vertical raises ValueError."""
        output_path = str(tmp_media_dir / "out.mp4")
        with pytest.raises(ValueError, match="Unsupported vertical format mode"):
            VideoFormatter.convert_to_vertical(
                input_path=str(dummy_video_file),
                output_path=output_path,
                mode="non_existent_mode",
            )

    def test_convert_to_vertical_ffmpeg_failure_raises_processing_error(
        self, dummy_video_file: Path, tmp_media_dir: Path, mock_ffmpeg: pytest.FixtureRequest
    ) -> None:
        """Test that convert_to_vertical raises ProcessingError when FFmpeg process fails."""
        mock_ffmpeg.simulate_failure(returncode=1, stderr="FFmpeg filter error")
        output_path = str(tmp_media_dir / "failed_out.mp4")
        with pytest.raises(ProcessingError, match="FFmpeg vertical conversion failed"):
            VideoFormatter.convert_to_vertical(
                input_path=str(dummy_video_file),
                output_path=output_path,
                mode="blur_background",
            )

    def test_convert_to_vertical_invalid_timestamp_range_raises_processing_error(
        self, dummy_video_file: Path, tmp_media_dir: Path
    ) -> None:
        """Test that start >= end raises ProcessingError."""
        output_path = str(tmp_media_dir / "invalid_ts.mp4")
        with pytest.raises(ProcessingError, match="Invalid timestamp range"):
            VideoFormatter.convert_to_vertical(
                input_path=str(dummy_video_file),
                output_path=output_path,
                start=10.0,
                end=5.0,
            )
        with pytest.raises(ProcessingError, match="Invalid timestamp range"):
            VideoFormatter.convert_to_vertical(
                input_path=str(dummy_video_file),
                output_path=output_path,
                start=5.0,
                end=5.0,
            )

    def test_auto_nvenc_failure_retries_with_libx264(
        self, dummy_video_file: Path, tmp_media_dir: Path
    ) -> None:
        """Automatic NVENC selection must transparently retry on CPU."""
        output_path = tmp_media_dir / "fallback.mp4"
        commands = []

        def fake_run_cmd(command, **kwargs):
            commands.append(command)
            if len(commands) == 1:
                return SimpleNamespace(returncode=1, stdout="", stderr="NVENC busy")
            output_path.write_bytes(b"fallback" * 256)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with (
            patch(
                "youtube_clipper.video_formatter.detect_h264_encoder",
                return_value="h264_nvenc",
            ),
            patch(
                "youtube_clipper.video_formatter.run_cmd",
                side_effect=fake_run_cmd,
            ),
        ):
            result = VideoFormatter.convert_to_vertical(
                input_path=str(dummy_video_file),
                output_path=str(output_path),
            )

        assert result == str(output_path)
        assert len(commands) == 2
        assert "h264_nvenc" in commands[0]
        assert "libx264" in commands[1]


class TestVideoFormatterConcurrency:
    """Test suite for thread concurrency in VideoFormatter."""

    def test_concurrent_vertical_conversions(
        self, dummy_video_file: Path, tmp_media_dir: Path, mock_ffmpeg: pytest.FixtureRequest
    ) -> None:
        """Test multiple concurrent vertical video conversions using ThreadPoolExecutor."""
        from concurrent.futures import ThreadPoolExecutor

        def convert_task(index: int) -> str:
            out_path = str(tmp_media_dir / f"concurrent_out_{index}.mp4")
            mode = "blur_background" if index % 2 == 0 else "crop_center"
            return VideoFormatter.convert_to_vertical(
                input_path=str(dummy_video_file),
                output_path=out_path,
                mode=mode,
            )

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(convert_task, i) for i in range(8)]
            results = [f.result() for f in futures]

        assert len(results) == 8
        for res_path in results:
            assert Path(res_path).exists()
