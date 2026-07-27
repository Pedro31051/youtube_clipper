"""
tests/test_e2e_scenarios.py - Tier 3 Cross-Feature & Tier 4 Real-World Application Scenario Tests.

Covers:
- Tier 3: Pairwise feature interactions (Local file + start/duration + custom output; YouTube URL + MM:SS range + fast copy; Shorts URL + float timestamps + verbose; invalid option combinations & error handling).
- Tier 4: Real-world application scenarios (Scenario 1: 30s highlight clipping; Scenario 2: YouTube tutorial extraction; Scenario 3: fast stream copying; Scenario 4: network/download failure recovery; Scenario 5: full CLI execution via cli_runner).
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, List, Optional
from unittest.mock import MagicMock, patch

import pytest
import yt_dlp

from youtube_clipper.exceptions import (
    ClipperError,
    DownloadError,
    FFmpegNotFoundError,
    ProcessingError,
    ValidationError,
)
from youtube_clipper.validator import (
    is_youtube_url,
    parse_timestamp,
    validate_input_source,
    validate_time_range,
)

from conftest import CLIRunnerResult, MockFFmpegContainer, MockYTDLPContainer

# Import pipeline execution helper and entrypoint helper from test_e2e_pipeline
from test_e2e_pipeline import _get_main_entrypoint, _run_pipeline


# ---------------------------------------------------------------------------
# Tier 3: Pairwise Cross-Feature Interactions
# ---------------------------------------------------------------------------

class TestTier3PairwiseCombinations:
    """Pairwise feature interaction tests verifying cross-module flag combinations."""

    def test_pairwise_local_file_start_duration_custom_output(
        self, dummy_video_file: Path, tmp_media_dir: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        """Pairwise: Local file + --start/--duration + custom --output path."""
        out_file = tmp_media_dir / "pairwise_local_out.mp4"
        res = _run_pipeline(
            input_source=str(dummy_video_file),
            start="00:00:10",
            duration="15",
            output=out_file,
        )
        assert Path(res).exists()
        assert Path(res) == out_file
        assert mock_ffmpeg.has_arg("10.0")
        assert mock_ffmpeg.has_arg("15.0")

    def test_pairwise_youtube_url_mmss_range_fast_copy(
        self, tmp_media_dir: Path, mock_yt_dlp: MockYTDLPContainer, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        """Pairwise: YouTube URL + MM:SS timestamp range + --fast stream copy."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        out_file = tmp_media_dir / "pairwise_yt_fast.mp4"
        res = _run_pipeline(
            input_source=url,
            start="01:30",
            end="03:45",
            output=out_file,
            fast=True,
        )
        assert Path(res).exists()
<<<<<<< HEAD
        # The downloader consumes 90s; FFmpeg receives the segment at t=0.
        assert mock_ffmpeg.has_arg("0.0")
=======
        assert mock_ffmpeg.has_arg("0.0")  # YouTube downloaded segment starts at t=0.0
>>>>>>> 48c4974 (feat(T1): fix double-cut offset calculation and add media validation guardrails)
        assert mock_ffmpeg.has_arg("135.0")  # 03:45 - 01:30 = 135s duration
        assert mock_ffmpeg.has_arg("copy")

    def test_pairwise_shorts_url_float_timestamps_verbose(
        self, tmp_media_dir: Path, mock_yt_dlp: MockYTDLPContainer, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        """Pairwise: YouTube Shorts URL + float seconds timestamps + --verbose mode."""
        url = "https://www.youtube.com/shorts/abcdefghijk"
        out_file = tmp_media_dir / "shorts_clip.mp4"
        res = _run_pipeline(
            input_source=url,
            start="10.5",
            end="25.25",
            output=out_file,
            verbose=True,
        )
        assert Path(res).exists()
        assert mock_ffmpeg.has_arg("0.0")  # YouTube downloaded segment starts at t=0.0
        assert mock_ffmpeg.has_arg("14.75")

    def test_pairwise_invalid_options_end_and_duration_conflict(
        self, cli_runner: Callable[..., CLIRunnerResult], dummy_video_file: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        """Pairwise error handling: Specifying both --end and --duration options simultaneously."""
        res = cli_runner(
            [str(dummy_video_file), "--start", "10", "--end", "20", "--duration", "10"],
            target_func=_get_main_entrypoint(),
        )
        assert res.exit_code != 0

    def test_pairwise_invalid_timestamp_format_and_youtube_url(
        self, cli_runner: Callable[..., CLIRunnerResult], mock_yt_dlp: MockYTDLPContainer, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        """Pairwise error handling: YouTube URL with invalid timestamp string format."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        res = cli_runner(
            [url, "--start", "invalid_start_time", "--end", "00:01:00"],
            target_func=_get_main_entrypoint(),
        )
        assert res.exit_code != 0

    def test_pairwise_local_file_hhmmss_range_fast_copy(
        self, dummy_video_file: Path, tmp_media_dir: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        """Pairwise: Local file + HH:MM:SS range + fast stream copy mode."""
        out_file = tmp_media_dir / "hhmmss_fast.mp4"
        res = _run_pipeline(
            input_source=str(dummy_video_file),
            start="01:00:00",
            end="01:05:00",
            output=out_file,
            fast=True,
        )
        assert Path(res).exists()
        assert mock_ffmpeg.has_arg("3600.0")  # 01:00:00 = 3600s
        assert mock_ffmpeg.has_arg("300.0")   # duration = 300s
        assert mock_ffmpeg.has_arg("copy")

    def test_pairwise_youtube_url_start_only_custom_output(
        self, tmp_media_dir: Path, mock_yt_dlp: MockYTDLPContainer, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        """Pairwise: YouTube URL + --start timestamp only + custom --output path."""
        url = "https://youtu.be/dQw4w9WgXcQ"
        out_file = tmp_media_dir / "start_only_out.mp4"
        res = _run_pipeline(
            input_source=url,
            start="30",
            end="90",
            output=out_file,
        )
        assert Path(res).exists()
        assert Path(res) == out_file

    def test_pairwise_shorts_url_start_duration_fast_copy(
        self, tmp_media_dir: Path, mock_yt_dlp: MockYTDLPContainer, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        """Pairwise: YouTube Shorts URL + --start/--duration + --fast copy mode."""
        url = "https://www.youtube.com/shorts/12345678901"
        out_file = tmp_media_dir / "shorts_fast.mp4"
        res = _run_pipeline(
            input_source=url,
            start="5",
            duration="15",
            output=out_file,
            fast=True,
        )
        assert Path(res).exists()
        assert mock_ffmpeg.has_arg("copy")

    def test_pairwise_youtube_url_with_timestamp_param_custom_output(
        self, tmp_media_dir: Path, mock_yt_dlp: MockYTDLPContainer, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        """Pairwise: YouTube URL with embedded timestamp parameter (&t=100s) + custom output path."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=100s"
        out_file = tmp_media_dir / "embedded_t_param.mp4"
        res = _run_pipeline(
            input_source=url,
            start="00:01:40",
            end="00:02:40",
            output=out_file,
        )
        assert Path(res).exists()
        assert Path(res) == out_file

    def test_pairwise_nonexistent_local_file_with_valid_timestamps(
        self, cli_runner: Callable[..., CLIRunnerResult]
    ) -> None:
        """Pairwise error handling: Non-existent local file path with valid timestamp arguments."""
        res = cli_runner(
            ["/nonexistent_directory/missing_video.mp4", "--start", "00:00:10", "--end", "00:00:20"],
            target_func=_get_main_entrypoint(),
        )
        assert res.exit_code != 0


# ---------------------------------------------------------------------------
# Tier 4: Real-World Application Scenarios
# ---------------------------------------------------------------------------

class TestTier4RealWorldScenarios:
    """Real-world end-to-end application scenario tests."""

    def test_scenario_1_highlight_clipping_30s(
        self, dummy_video_file: Path, tmp_media_dir: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        """
        Scenario 1: 30s Highlight Clipping.
        Clips a 30-second highlight from a local video starting at 01:15 (75 seconds) until 01:45 (105 seconds).
        Verifies correct interval calculation (75.0s start, 30.0s duration), output file existence, non-empty size.
        """
        out_file = tmp_media_dir / "highlight_30s.mp4"
        result_path = _run_pipeline(
            input_source=str(dummy_video_file),
            start="01:15",
            duration="30",
            output=out_file,
        )

        final_path = Path(result_path)
        assert final_path.exists()
        assert final_path.stat().st_size > 0
        assert mock_ffmpeg.has_arg("-ss")
        assert mock_ffmpeg.has_arg("75.0")
        assert mock_ffmpeg.has_arg("-t")
        assert mock_ffmpeg.has_arg("30.0")

    def test_scenario_2_youtube_tutorial_extraction(
        self, tmp_media_dir: Path, mock_yt_dlp: MockYTDLPContainer, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        """
        Scenario 2: YouTube Tutorial Extraction.
        Extracts a 5-minute explanation segment (00:02:00 to 00:07:00) from a YouTube tutorial video.
        Verifies YoutubeDL range extraction call, temporary path isolation, FFmpeg clipping, and target file creation.
        """
        url = "https://www.youtube.com/watch?v=tutorial123"
        out_file = tmp_media_dir / "tutorial_explanation.mp4"

        result_path = _run_pipeline(
            input_source=url,
            start="00:02:00",
            end="00:07:00",
            output=out_file,
        )

        final_path = Path(result_path)
        assert final_path.exists()
        assert final_path == out_file
<<<<<<< HEAD
        # The downloader consumes 120s; FFmpeg receives the segment at t=0.
=======
        # YouTube downloaded segment starts at t=0.0, duration = 300.0s
>>>>>>> 48c4974 (feat(T1): fix double-cut offset calculation and add media validation guardrails)
        assert mock_ffmpeg.has_arg("0.0")
        assert mock_ffmpeg.has_arg("300.0")

    def test_scenario_3_fast_stream_copying(
        self, dummy_video_file: Path, tmp_media_dir: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        """
        Scenario 3: Fast Stream Copying.
        Extracts a clip using --fast (-c copy) without re-encoding video/audio streams to save processing time and CPU.
        Verifies -c copy is present in FFmpeg arguments, and re-encoding codecs (-c:v libx264) are bypassed.
        """
        out_file = tmp_media_dir / "fast_copy_scenario.mp4"

        result_path = _run_pipeline(
            input_source=str(dummy_video_file),
            start="00:00:10",
            end="00:00:40",
            output=out_file,
            fast=True,
        )

        final_path = Path(result_path)
        assert final_path.exists()
        assert mock_ffmpeg.has_arg("-c")
        assert mock_ffmpeg.has_arg("copy")
        # Ensure re-encoding codec flags were not passed
        assert not mock_ffmpeg.has_arg("libx264")

    def test_scenario_4_download_failure_recovery(
        self, tmp_media_dir: Path, mock_yt_dlp: MockYTDLPContainer, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        """
        Scenario 4: Network / Download Failure Recovery.
        Simulates network drop or yt-dlp failure during video stream extraction.
        Verifies DownloadError is raised with descriptive context, workspace temp files are cleaned up, and no corrupted output file remains.
        """
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        out_file = tmp_media_dir / "corrupted_attempt.mp4"

        # Simulate network drop / download failure in yt-dlp
        mock_yt_dlp.set_extract_info_side_effect(
            yt_dlp.utils.DownloadError("HTTP Error 404: Video unavailable")
        )

        with pytest.raises(DownloadError) as exc_info:
            _run_pipeline(
                input_source=url,
                start=0,
                end=10,
                output=out_file,
            )

        assert "unavailable" in str(exc_info.value).lower() or "download" in str(exc_info.value).lower() or "network" in str(exc_info.value).lower()
        # Verify incomplete output file was not generated
        assert not out_file.exists()

    def test_scenario_5_full_cli_execution_via_runner_youtube_url(
        self,
        cli_runner: Callable[..., CLIRunnerResult],
        tmp_media_dir: Path,
        mock_yt_dlp: MockYTDLPContainer,
        mock_ffmpeg: MockFFmpegContainer,
    ) -> None:
        """
        Scenario 5a: Full CLI Execution via cli_runner with YouTube URL and all options.
        Executes end-to-end CLI command: youtube_clipper <url> --start 00:00:10 --end 00:00:40 -o <path> --fast --verbose.
        """
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        out_file = tmp_media_dir / "scenario5_yt.mp4"

        res = cli_runner(
            [url, "--start", "00:00:10", "--end", "00:00:40", "--output", str(out_file), "--fast", "--verbose"],
            target_func=_get_main_entrypoint(),
        )

        assert res.exit_code == 0
        assert res.exception is None
        assert out_file.exists()

    def test_scenario_5_full_cli_execution_via_runner_local_file(
        self,
        cli_runner: Callable[..., CLIRunnerResult],
        dummy_video_file: Path,
        tmp_media_dir: Path,
        mock_ffmpeg: MockFFmpegContainer,
    ) -> None:
        """
        Scenario 5b: Full CLI Execution via cli_runner with local video file.
        Executes end-to-end CLI command: youtube_clipper <file> --start 15.5 --duration 30 -o <path> --fast.
        """
        out_file = tmp_media_dir / "scenario5_local.mp4"

        res = cli_runner(
            [str(dummy_video_file), "--start", "15.5", "--duration", "30", "--output", str(out_file), "--fast"],
            target_func=_get_main_entrypoint(),
        )

        assert res.exit_code == 0
        assert res.exception is None
        assert out_file.exists()
