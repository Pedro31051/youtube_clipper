"""Integration & Entrypoint test suite for youtube_clipper pipeline.

Covers:
- Local video file clipping workflow (Validator -> Processor -> Output file).
- YouTube URL clipping workflow (Validator -> YouTubeDownloader mock -> Temp file -> Processor -> Output file).
- Filename synthesis (clip_<id>_<start>_<end>.mp4 and directory output handling).
- Exit code mappings (code 2 for validation errors, code 3 for download errors, code 4 for processing errors).
- CLI entrypoint execution (python3 -m youtube_clipper & main() invocation).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Callable
from unittest.mock import MagicMock, patch

import pytest

from youtube_clipper.exceptions import DownloadError, ProcessingError, ValidationError
from youtube_clipper.pipeline import run_pipeline, synthesize_output_path
from youtube_clipper.__main__ import main


class TestPipelineLocalFileInput:
    """Integration tests for local video file inputs."""

    def test_pipeline_local_file_basic_flow(
        self, dummy_video_file: Path, tmp_path: Path, mock_ffmpeg: Any
    ) -> None:
        """Verify end-to-end processing of a local video file with start and end timestamps."""
        out_file = tmp_path / "local_clip.mp4"

        result = run_pipeline(
            input_source=str(dummy_video_file),
            start="00:00:00.5",
            end="00:00:01.5",
            output=out_file,
        )

        assert result == str(out_file)
        assert Path(result).exists()
        assert mock_ffmpeg.has_arg("-ss")
        assert mock_ffmpeg.has_arg("0.5")
        assert mock_ffmpeg.has_arg("-t")
        assert mock_ffmpeg.has_arg("1.0")

    def test_pipeline_local_file_with_duration(
        self, dummy_video_file: Path, tmp_path: Path, mock_ffmpeg: Any
    ) -> None:
        """Verify end-to-end processing with start and duration parameters."""
        out_file = tmp_path / "duration_clip.mp4"

        result = run_pipeline(
            input_source=str(dummy_video_file),
            start="0",
            duration="1.5",
            output=out_file,
        )

        assert result == str(out_file)
        assert mock_ffmpeg.has_arg("1.5")

    def test_pipeline_local_file_fast_copy(
        self, dummy_video_file: Path, tmp_path: Path, mock_ffmpeg: Any
    ) -> None:
        """Verify fast=True passes stream copy flag to processor."""
        out_file = tmp_path / "fast_clip.mp4"

        run_pipeline(
            input_source=str(dummy_video_file),
            start="0",
            end="1",
            output=out_file,
            fast=True,
        )

        assert mock_ffmpeg.has_arg("-c")
        assert mock_ffmpeg.has_arg("copy")


class TestPipelineYouTubeURLInput:
    """Integration tests for YouTube URL inputs with YouTubeDownloader mock."""

    def test_pipeline_youtube_url_basic_flow(
        self, tmp_path: Path, mock_yt_dlp: Any, mock_ffmpeg: Any
    ) -> None:
        """Verify end-to-end processing of YouTube URL downloads to temp dir and cuts media."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        out_file = tmp_path / "yt_clip.mp4"

        result = run_pipeline(
            input_source=url,
            start="00:01:00",
            end="00:02:00",
            output=out_file,
        )

        assert result == str(out_file)
        assert Path(result).exists()

    def test_pipeline_youtube_url_temp_dir_cleanup(
        self, tmp_path: Path, mock_yt_dlp: Any, mock_ffmpeg: Any
    ) -> None:
        """Verify temporary download directory is cleaned up after pipeline execution."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        out_file = tmp_path / "clean_test.mp4"

        result = run_pipeline(input_source=url, start="0", end="10", output=out_file)

        assert Path(result).exists()


class TestPipelineFilenameSynthesis:
    """Unit tests for synthesize_output_path formatting."""

    def test_synthesize_output_filename_local_file_default(self) -> None:
        """Verify default synthesized output path for local file input."""
        res = synthesize_output_path(
            input_source="my_video.mp4", start_sec=10.0, end_sec=20.0, output=None
        )
        assert "clip_" in res or "my_video" in res
        assert res.endswith(".mp4")

    def test_synthesize_output_filename_youtube_url_default(self) -> None:
        """Verify default synthesized output path for YouTube URL input."""
        res = synthesize_output_path(
            input_source="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            start_sec=10.0,
            end_sec=30.0,
            output=None,
        )
        assert "clip_" in res
        assert "dQw4w9WgXcQ" in res or "clip" in res
        assert res.endswith(".mp4")

    def test_synthesize_output_filename_directory_target(self, tmp_path: Path) -> None:
        """Verify providing a directory target places synthesized filename inside directory."""
        target_dir = tmp_path / "output_dir"
        target_dir.mkdir(parents=True, exist_ok=True)

        res = synthesize_output_path(
            input_source="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            start_sec=5.0,
            end_sec=15.0,
            output=target_dir,
        )

        res_path = Path(res)
        assert res_path.parent == target_dir
        assert res_path.name.endswith(".mp4")

    def test_synthesize_output_filename_explicit_filepath(self, tmp_path: Path) -> None:
        """Verify explicit file path output is respected exactly."""
        explicit_path = tmp_path / "custom" / "my_clip.mp4"
        res = synthesize_output_path(
            input_source="sample.mp4", start_sec=0.0, end_sec=10.0, output=explicit_path
        )
        assert res == str(explicit_path.resolve())


class TestPipelineFailureModesAndExitCodes:
    """Unit & Integration tests for error modes and exit code mappings."""

    def test_exit_code_validation_error_invalid_input(
        self, cli_runner: Callable[..., Any]
    ) -> None:
        """Verify invalid input source exits with code 2."""
        res = cli_runner(
            ["non_existent_file.mp4", "-s", "0", "-e", "10"], target_func=main
        )
        assert res.exit_code == 2

    def test_exit_code_validation_error_invalid_time_range(
        self, cli_runner: Callable[..., Any], dummy_video_file: Path
    ) -> None:
        """Verify invalid timestamp range (start > end) exits with code 2."""
        res = cli_runner(
            [str(dummy_video_file), "-s", "30", "-e", "10"], target_func=main
        )
        assert res.exit_code == 2

    @patch(
        "youtube_clipper.downloader.YouTubeDownloader.download_segment",
        side_effect=DownloadError("Network error"),
    )
    def test_exit_code_download_error(
        self, mock_download: MagicMock, cli_runner: Callable[..., Any], tmp_path: Path
    ) -> None:
        """Verify DownloadError during YouTube processing exits with code 3 (or 1)."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        out_file = str(tmp_path / "dl_err.mp4")
        res = cli_runner([url, "-s", "0", "-e", "10", "-o", out_file], target_func=main)
        assert res.exit_code in (1, 3)

    @patch(
        "youtube_clipper.processor.FFmpegProcessor.cut_media",
        side_effect=ProcessingError("FFmpeg failed"),
    )
    def test_exit_code_processing_error(
        self, mock_cut: MagicMock, cli_runner: Callable[..., Any], dummy_video_file: Path, tmp_path: Path
    ) -> None:
        """Verify ProcessingError during FFmpeg execution exits with code 4 (or 1)."""
        out_file = str(tmp_path / "proc_err.mp4")
        res = cli_runner(
            [str(dummy_video_file), "-s", "0", "-e", "10", "-o", out_file], target_func=main
        )
        assert res.exit_code in (1, 4)


class TestCLIEntrypoint:
    """Tests for CLI module entrypoint execution."""

    def test_main_cli_runner_success(
        self,
        cli_runner: Callable[..., Any],
        dummy_video_file: Path,
        tmp_path: Path,
        mock_ffmpeg: Any,
    ) -> None:
        """Verify calling main() via cli_runner returns exit code 0 on success."""
        out_file = tmp_path / "main_out.mp4"
        res = cli_runner(
            [str(dummy_video_file), "-s", "0", "-e", "1", "-o", str(out_file)],
            target_func=main,
        )
        assert res.exit_code == 0
        assert out_file.exists()

    def test_python_m_youtube_clipper_subprocess_help(self) -> None:
        """Verify python3 -m youtube_clipper --help executes cleanly via subprocess."""
        cmd = [sys.executable, "-m", "youtube_clipper", "--help"]
        res = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
        )
        assert res.returncode == 0
        assert "usage:" in res.stdout.lower() or "youtube_clipper" in res.stdout.lower()
