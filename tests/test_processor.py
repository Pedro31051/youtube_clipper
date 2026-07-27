"""Unit and Integration test suite for FFmpegProcessor.

Covers:
- FFmpegProcessor initialization and binary lookup (shutil.which).
- FFmpeg command CLI flag generation: fast seeking (-ss before -i), duration (-t),
  re-encoding (-c:v libx264 -c:a aac) vs stream copy (-c copy), overwrite (-y).
- Exception handling: ProcessingError (returncode, stderr, cmd), FFmpegNotFoundError.
- Boundary conditions: non-existent input, invalid timestamp ranges, on-demand directory creation.
- Real system FFmpeg integration cutting synthetic MP4 files.
"""

from __future__ import annotations

import shutil
import subprocess
import json
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from youtube_clipper.exceptions import FFmpegNotFoundError, ProcessingError
from youtube_clipper.processor import FFmpegProcessor


def successful_media_command(cmd: List[str], **_: object) -> subprocess.CompletedProcess:
    """Simulate a valid FFmpeg output and its ffprobe metadata."""
    if Path(cmd[0]).name == "ffprobe":
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=json.dumps(
                {
                    "format": {"duration": "5.0"},
                    "streams": [{"codec_type": "video"}],
                }
            ),
            stderr="",
        )
    Path(cmd[-1]).write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"x" * 2048)
    return subprocess.CompletedProcess(
        args=cmd, returncode=0, stdout="", stderr=""
    )


class TestFFmpegProcessorInit:
    """Unit tests for FFmpegProcessor initialization and binary location."""

    def test_init_default_ffmpeg_found(self) -> None:
        """Verify initialization succeeds when ffmpeg is available in system PATH."""
        processor = FFmpegProcessor()
        assert processor.ffmpeg_bin is not None
        assert Path(processor.ffmpeg_bin).name.startswith("ffmpeg")

    def test_init_custom_ffmpeg_path(self) -> None:
        """Verify custom ffmpeg binary path passed in constructor is stored."""
        custom_path = "/usr/bin/ffmpeg"
        processor = FFmpegProcessor(ffmpeg_path=custom_path)
        assert processor.ffmpeg_bin == custom_path

    def test_init_missing_ffmpeg_raises_error(self) -> None:
        """Verify FFmpegNotFoundError is raised when ffmpeg executable is not found."""
        with patch("shutil.which", return_value=None):
            with pytest.raises(FFmpegNotFoundError) as exc_info:
                FFmpegProcessor()
            assert "FFmpeg executable not found" in exc_info.value.message


def _mock_run_ffmpeg_and_ffprobe(cmd: List[str] | str, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    cmd_list = cmd if isinstance(cmd, list) else [str(cmd)]
    if cmd_list and ("ffprobe" in cmd_list[0] or Path(cmd_list[0]).name == "ffprobe"):
        return subprocess.CompletedProcess(args=cmd_list, returncode=0, stdout="10.0\n", stderr="")
    if cmd_list and len(cmd_list) > 1 and not cmd_list[-1].startswith("-"):
        out_path = Path(cmd_list[-1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048)
    return subprocess.CompletedProcess(args=cmd_list, returncode=0, stdout="", stderr="")


class TestFFmpegProcessorCommandGeneration:
    """Unit tests for FFmpeg command line flag construction."""

    @patch("subprocess.run")
    def test_cut_media_flag_ordering_ss_before_i(
        self, mock_run: MagicMock, dummy_video_file: Path, tmp_path: Path
    ) -> None:
        """Verify cut_media places fast-seeking -ss flag BEFORE input -i flag."""
<<<<<<< HEAD
        mock_run.side_effect = successful_media_command
=======
        mock_run.side_effect = _mock_run_ffmpeg_and_ffprobe
>>>>>>> 48c4974 (feat(T1): fix double-cut offset calculation and add media validation guardrails)
        processor = FFmpegProcessor()
        out_file = tmp_path / "out.mp4"

        processor.cut_media(dummy_video_file, start=10.0, end=30.0, output_path=out_file)

        assert mock_run.called
<<<<<<< HEAD
=======
        # Check call args for the ffmpeg command (first call before ffprobe)
>>>>>>> 48c4974 (feat(T1): fix double-cut offset calculation and add media validation guardrails)
        cmd: List[str] = mock_run.call_args_list[0][0][0]

        assert "-ss" in cmd
        assert "-i" in cmd
        ss_idx = cmd.index("-ss")
        i_idx = cmd.index("-i")
        assert ss_idx < i_idx, "Expected -ss flag to appear BEFORE -i flag for fast input seeking"
        assert cmd[ss_idx + 1] == "10.0"
        assert cmd[i_idx + 1] == str(dummy_video_file)

    @patch("subprocess.run")
    def test_cut_media_duration_flag_t(
        self, mock_run: MagicMock, dummy_video_file: Path, tmp_path: Path
    ) -> None:
        """Verify cut_media passes -t flag equal to (end - start)."""
        mock_run.side_effect = successful_media_command
        processor = FFmpegProcessor()
        out_file = tmp_path / "out.mp4"

        processor.cut_media(dummy_video_file, start=5.0, end=20.5, output_path=out_file)

        cmd: List[str] = mock_run.call_args_list[0][0][0]
        assert "-t" in cmd
        t_idx = cmd.index("-t")
        assert cmd[t_idx + 1] == "15.5"

    @patch("subprocess.run")
    def test_cut_media_reencoding_codecs_default(
        self, mock_run: MagicMock, dummy_video_file: Path, tmp_path: Path
    ) -> None:
        """Verify default cut_media (fast_copy=False) specifies libx264 video and aac audio codecs."""
        mock_run.side_effect = successful_media_command
        processor = FFmpegProcessor()
        out_file = tmp_path / "reencoded.mp4"

        processor.cut_media(
            dummy_video_file, start=0.0, end=5.0, output_path=out_file, fast_copy=False
        )

        cmd: List[str] = mock_run.call_args_list[0][0][0]
        assert "-c:v" in cmd
        assert cmd[cmd.index("-c:v") + 1] == "libx264"
        assert "-c:a" in cmd
        assert cmd[cmd.index("-c:a") + 1] == "aac"

    @patch("subprocess.run")
    def test_cut_media_stream_copy_flag(
        self, mock_run: MagicMock, dummy_video_file: Path, tmp_path: Path
    ) -> None:
        """Verify fast_copy=True uses stream copying (-c copy) instead of re-encoding."""
        mock_run.side_effect = successful_media_command
        processor = FFmpegProcessor()
        out_file = tmp_path / "copy.mp4"

        processor.cut_media(
            dummy_video_file, start=0.0, end=5.0, output_path=out_file, fast_copy=True
        )

        cmd: List[str] = mock_run.call_args_list[0][0][0]
        assert "-c" in cmd
        assert cmd[cmd.index("-c") + 1] == "copy"
        assert "-c:v" not in cmd
        assert "-c:a" not in cmd

    @patch("subprocess.run")
    def test_cut_media_output_overwrite_flag(
        self, mock_run: MagicMock, dummy_video_file: Path, tmp_path: Path
    ) -> None:
        """Verify cut_media includes -y flag to overwrite existing output files."""
        mock_run.side_effect = successful_media_command
        processor = FFmpegProcessor()
        out_file = tmp_path / "out.mp4"

        processor.cut_media(dummy_video_file, start=0.0, end=1.0, output_path=out_file)

        cmd: List[str] = mock_run.call_args_list[0][0][0]
        assert "-y" in cmd


class TestFFmpegProcessorErrorsAndBoundaries:
    """Unit tests for exception handling, missing input files, and invalid ranges."""

    def test_cut_media_non_existent_input_file(self, tmp_path: Path) -> None:
        """Verify passing non-existent input media file raises ProcessingError."""
        processor = FFmpegProcessor()
        missing_input = tmp_path / "non_existent_video.mp4"
        out_file = tmp_path / "out.mp4"

        with pytest.raises(ProcessingError) as exc_info:
            processor.cut_media(missing_input, start=0.0, end=5.0, output_path=out_file)
        assert "Input media file does not exist" in exc_info.value.message

    @pytest.mark.parametrize("start,end", [(-1.0, 5.0), (10.0, 5.0), (5.0, 5.0)])
    def test_cut_media_invalid_timestamp_ranges(
        self, start: float, end: float, dummy_video_file: Path, tmp_path: Path
    ) -> None:
        """Verify negative start time or end <= start raises ProcessingError."""
        processor = FFmpegProcessor()
        out_file = tmp_path / "out.mp4"

        with pytest.raises(ProcessingError) as exc_info:
            processor.cut_media(dummy_video_file, start=start, end=end, output_path=out_file)
        assert "Invalid timestamp range" in exc_info.value.message

    @patch("subprocess.run")
    def test_cut_media_ffmpeg_subprocess_failure(
        self, mock_run: MagicMock, dummy_video_file: Path, tmp_path: Path
    ) -> None:
        """Verify non-zero FFmpeg returncode raises ProcessingError with stderr and returncode."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ffmpeg"], returncode=1, stdout="", stderr="Unknown encoder 'libx264'"
        )
        processor = FFmpegProcessor()
        out_file = tmp_path / "out.mp4"

        with pytest.raises(ProcessingError) as exc_info:
            processor.cut_media(dummy_video_file, start=0.0, end=5.0, output_path=out_file)

        err = exc_info.value
        assert err.returncode == 1
        assert "Unknown encoder" in err.stderr
        assert err.cmd is not None

    @patch(
        "subprocess.run",
        side_effect=FileNotFoundError("No such file or directory: 'ffmpeg'"),
    )
    def test_cut_media_missing_ffmpeg_at_runtime(
        self, mock_run: MagicMock, dummy_video_file: Path, tmp_path: Path
    ) -> None:
        """Verify FileNotFoundError during subprocess execution is wrapped into FFmpegNotFoundError."""
        processor = FFmpegProcessor()
        out_file = tmp_path / "out.mp4"

        with pytest.raises(FFmpegNotFoundError) as exc_info:
            processor.cut_media(dummy_video_file, start=0.0, end=5.0, output_path=out_file)
        assert "not found" in exc_info.value.message.lower()

    @patch("subprocess.run")
    def test_cut_media_creates_output_directories(
        self, mock_run: MagicMock, dummy_video_file: Path, tmp_path: Path
    ) -> None:
        """Verify cut_media creates parent output directory structure on demand."""
        mock_run.side_effect = successful_media_command
        processor = FFmpegProcessor()
        nested_out = tmp_path / "nested" / "sub" / "out.mp4"

        assert not nested_out.parent.exists()
        processor.cut_media(dummy_video_file, start=0.0, end=1.0, output_path=nested_out)
        assert nested_out.parent.exists()

    @patch("subprocess.run")
    def test_cut_media_small_file_raises_processing_error(
        self, mock_run: MagicMock, dummy_video_file: Path, tmp_path: Path
    ) -> None:
        """Verify cut_media raises ProcessingError if output file size <= 1024 bytes."""
        def mock_small_run(cmd: List[str] | str, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            cmd_list = cmd if isinstance(cmd, list) else [str(cmd)]
            if cmd_list and len(cmd_list) > 1 and not cmd_list[-1].startswith("-"):
                out_path = Path(cmd_list[-1])
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(b"x" * 262)  # 262 bytes <= 1024
            return subprocess.CompletedProcess(args=cmd_list, returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_small_run
        processor = FFmpegProcessor()
        out_file = tmp_path / "small.mp4"

        with pytest.raises(ProcessingError) as exc_info:
            processor.cut_media(dummy_video_file, start=0.0, end=5.0, output_path=out_file)

        assert exc_info.value.exit_code == 4
        assert "file size 262 bytes <= 1024 bytes" in exc_info.value.message

    @patch("subprocess.run")
    def test_cut_media_zero_duration_raises_processing_error(
        self, mock_run: MagicMock, dummy_video_file: Path, tmp_path: Path
    ) -> None:
        """Verify cut_media raises ProcessingError if ffprobe reports duration <= 0."""
        def mock_zero_duration_run(cmd: List[str] | str, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            cmd_list = cmd if isinstance(cmd, list) else [str(cmd)]
            if cmd_list and ("ffprobe" in cmd_list[0] or Path(cmd_list[0]).name == "ffprobe"):
                return subprocess.CompletedProcess(args=cmd_list, returncode=0, stdout="0.0\n", stderr="")
            if cmd_list and len(cmd_list) > 1 and not cmd_list[-1].startswith("-"):
                out_path = Path(cmd_list[-1])
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(b"x" * 2048)
            return subprocess.CompletedProcess(args=cmd_list, returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_zero_duration_run
        processor = FFmpegProcessor()
        out_file = tmp_path / "zero_dur.mp4"

        with pytest.raises(ProcessingError) as exc_info:
            processor.cut_media(dummy_video_file, start=0.0, end=5.0, output_path=out_file)

        assert exc_info.value.exit_code == 4
        assert "ffprobe duration <= 0" in exc_info.value.message


class TestFFmpegProcessorIntegration:
    """Integration tests running cut_media against real FFmpeg binary."""

    @pytest.mark.skipif(
        not shutil.which("ffmpeg"), reason="FFmpeg binary not available on system"
    )
    def test_real_ffmpeg_cut_media_synthetic_mp4(
        self, dummy_video_file: Path, tmp_path: Path
    ) -> None:
        """Verify real FFmpeg execution cuts synthetic MP4 file and produces output file."""
        processor = FFmpegProcessor()
        out_file = tmp_path / "real_cut.mp4"

        result = processor.cut_media(
            dummy_video_file, start=0.5, end=1.5, output_path=out_file, fast_copy=False
        )

        assert result == str(out_file)
        assert out_file.exists()
        assert out_file.stat().st_size > 0

    @pytest.mark.skipif(
        not shutil.which("ffmpeg"), reason="FFmpeg binary not available on system"
    )
    def test_real_ffmpeg_cut_media_stream_copy(
        self, dummy_video_file: Path, tmp_path: Path
    ) -> None:
        """Verify real FFmpeg execution with stream copy (-c copy) succeeds."""
        processor = FFmpegProcessor()
        out_file = tmp_path / "real_copy.mp4"

        result = processor.cut_media(
            dummy_video_file, start=0.0, end=1.0, output_path=out_file, fast_copy=True
        )

        assert result == str(out_file)
        assert out_file.exists()
        assert out_file.stat().st_size > 0
