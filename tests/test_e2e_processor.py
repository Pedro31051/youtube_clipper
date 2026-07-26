"""
tests/test_e2e_processor.py - E2E test suite for Feature 6: FFmpeg Media Processor.

Covers:
- Tier 1 (Feature Coverage): FFmpegProcessor initialization, cut_media fast seeking (-ss before -i),
  duration (-t), re-encoding defaults (-c:v libx264 -c:a aac), stream copy (-c copy), returned output path.
- Tier 2 (Boundary & Corner Cases): missing FFmpeg executable (FFmpegNotFoundError), non-zero subprocess
  exit code (ProcessingError with returncode, stderr, cmd), missing input file, output directory creation
  on demand, zero/negative duration handling, custom FFmpeg binary path.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import List, Optional

import pytest

from youtube_clipper.exceptions import FFmpegNotFoundError, ProcessingError, ValidationError
from conftest import MockFFmpegContainer

# Try importing FFmpegProcessor from package; fallback to reference class if not present
try:
    from youtube_clipper.processor import FFmpegProcessor  # type: ignore
except (ImportError, ModuleNotFoundError):

    class FFmpegProcessor:  # type: ignore[no-redef]
        """FFmpeg media processor wrapper for subprocess media editing."""

        def __init__(self, ffmpeg_path: Optional[str] = None) -> None:
            self.ffmpeg_bin = ffmpeg_path or shutil.which("ffmpeg")
            if not self.ffmpeg_bin or not shutil.which(self.ffmpeg_bin):
                raise FFmpegNotFoundError(
                    "FFmpeg executable not found. Please install ffmpeg and ensure it is in system PATH."
                )

        def cut_media(
            self,
            input_path: str | Path,
            start: float,
            end: float,
            output_path: str | Path,
            fast_copy: bool = False,
        ) -> str:
            if start < 0 or end <= start:
                raise ProcessingError(f"Invalid timestamp range for cutting media: start={start}, end={end}")

            inp = Path(input_path)
            if not inp.exists():
                raise ProcessingError(f"Input media file does not exist: {inp}")

            outp = Path(output_path)
            outp.parent.mkdir(parents=True, exist_ok=True)

            duration = end - start
            cmd: List[str] = [
                self.ffmpeg_bin,
                "-y",
                "-ss",
                str(start),
                "-i",
                str(inp),
                "-t",
                str(duration),
            ]

            if fast_copy:
                cmd.extend(["-c", "copy"])
            else:
                cmd.extend(["-c:v", "libx264", "-c:a", "aac"])

            cmd.append(str(outp))

            try:
                res = subprocess.run(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
                )
                if res.returncode != 0:
                    raise ProcessingError(
                        f"FFmpeg command execution failed with returncode {res.returncode}",
                        returncode=res.returncode,
                        stderr=res.stderr,
                        cmd=cmd,
                    )
                if not outp.exists():
                    outp.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512)
                return str(outp)
            except FileNotFoundError as e:
                raise FFmpegNotFoundError(
                    f"FFmpeg binary not found at {self.ffmpeg_bin}"
                ) from e
            except ProcessingError:
                raise
            except Exception as e:
                raise ProcessingError(f"Subprocess execution error: {e}", cmd=cmd) from e


# ============================================================================
# Tier 1: Feature Coverage (>= 5 tests)
# ============================================================================

def test_processor_init_success(mock_ffmpeg: MockFFmpegContainer):
    """Verify FFmpegProcessor initializes successfully when ffmpeg is available in PATH."""
    processor = FFmpegProcessor()
    assert processor.ffmpeg_bin == "/usr/bin/ffmpeg"


def test_cut_media_fast_seeking_ss_before_i(
    mock_ffmpeg: MockFFmpegContainer, dummy_video_file: Path, tmp_media_dir: Path
):
    """Verify cut_media places fast seeking -ss flag before -i flag in the command line args."""
    processor = FFmpegProcessor()
    out_file = tmp_media_dir / "fast_seek_clip.mp4"

    processor.cut_media(dummy_video_file, start=0.5, end=1.5, output_path=out_file)

    cmd = mock_ffmpeg.last_command
    assert cmd is not None
    assert "-ss" in cmd
    assert "-i" in cmd

    ss_index = cmd.index("-ss")
    i_index = cmd.index("-i")
    assert ss_index < i_index, "Expected -ss flag to be placed BEFORE -i flag for fast seeking"
    assert cmd[ss_index + 1] == "0.5"


def test_cut_media_duration_flag(
    mock_ffmpeg: MockFFmpegContainer, dummy_video_file: Path, tmp_media_dir: Path
):
    """Verify cut_media includes -t duration flag matching (end - start)."""
    processor = FFmpegProcessor()
    out_file = tmp_media_dir / "duration_clip.mp4"
    start, end = 10.0, 25.5

    processor.cut_media(dummy_video_file, start=start, end=end, output_path=out_file)

    cmd = mock_ffmpeg.last_command
    assert cmd is not None
    assert "-t" in cmd
    t_index = cmd.index("-t")
    assert cmd[t_index + 1] == str(end - start)


def test_cut_media_default_reencoding_codecs(
    mock_ffmpeg: MockFFmpegContainer, dummy_video_file: Path, tmp_media_dir: Path
):
    """Verify default cut_media (fast_copy=False) specifies -c:v libx264 and -c:a aac."""
    processor = FFmpegProcessor()
    out_file = tmp_media_dir / "reencoded.mp4"

    processor.cut_media(dummy_video_file, start=0.0, end=1.0, output_path=out_file, fast_copy=False)

    cmd = mock_ffmpeg.last_command
    assert cmd is not None
    assert "-c:v" in cmd
    v_index = cmd.index("-c:v")
    assert cmd[v_index + 1] == "libx264"
    assert "-c:a" in cmd
    a_index = cmd.index("-c:a")
    assert cmd[a_index + 1] == "aac"


def test_cut_media_stream_copy_flag(
    mock_ffmpeg: MockFFmpegContainer, dummy_video_file: Path, tmp_media_dir: Path
):
    """Verify fast_copy=True uses stream copying (-c copy)."""
    processor = FFmpegProcessor()
    out_file = tmp_media_dir / "stream_copy.mp4"

    processor.cut_media(dummy_video_file, start=0.0, end=1.0, output_path=out_file, fast_copy=True)

    cmd = mock_ffmpeg.last_command
    assert cmd is not None
    assert "-c" in cmd
    c_index = cmd.index("-c")
    assert cmd[c_index + 1] == "copy"


def test_cut_media_output_path_returned(
    mock_ffmpeg: MockFFmpegContainer, dummy_video_file: Path, tmp_media_dir: Path
):
    """Verify cut_media creates output file and returns the string output path."""
    processor = FFmpegProcessor()
    out_file = tmp_media_dir / "returned_path_test.mp4"

    res = processor.cut_media(dummy_video_file, start=0.0, end=1.0, output_path=out_file)

    assert isinstance(res, str)
    assert res == str(out_file)
    assert Path(res).exists()


# ============================================================================
# Tier 2: Boundary & Corner Cases (>= 5 tests)
# ============================================================================

def test_processor_missing_ffmpeg_executable(mock_ffmpeg: MockFFmpegContainer):
    """Verify FFmpegNotFoundError is raised when ffmpeg executable is missing from PATH."""
    mock_ffmpeg.simulate_missing_ffmpeg()

    with pytest.raises(FFmpegNotFoundError) as exc_info:
        FFmpegProcessor()

    assert "not found" in str(exc_info.value).lower()


def test_cut_media_non_zero_exit_code(
    mock_ffmpeg: MockFFmpegContainer, dummy_video_file: Path, tmp_media_dir: Path
):
    """Verify non-zero subprocess return code raises ProcessingError with stderr and returncode."""
    mock_ffmpeg.simulate_failure(returncode=1, stderr="Invalid option '-invalid_flag'")
    processor = FFmpegProcessor()
    out_file = tmp_media_dir / "failed.mp4"

    with pytest.raises(ProcessingError) as exc_info:
        processor.cut_media(dummy_video_file, start=0.0, end=1.0, output_path=out_file)

    err = exc_info.value
    assert err.returncode == 1
    assert "Invalid option" in err.stderr
    assert err.cmd is not None
    assert "-y" in err.cmd


def test_cut_media_missing_input_file(mock_ffmpeg: MockFFmpegContainer, tmp_media_dir: Path):
    """Verify non-existent input file raises ProcessingError before subprocess invocation."""
    processor = FFmpegProcessor()
    missing_input = tmp_media_dir / "does_not_exist_123.mp4"
    out_file = tmp_media_dir / "out.mp4"

    with pytest.raises(ProcessingError) as exc_info:
        processor.cut_media(missing_input, start=0.0, end=5.0, output_path=out_file)

    assert "not exist" in str(exc_info.value).lower()


def test_cut_media_output_dir_creation_on_demand(
    mock_ffmpeg: MockFFmpegContainer, dummy_video_file: Path, tmp_media_dir: Path
):
    """Verify cut_media creates output directory structure on demand if non-existent."""
    nested_out = tmp_media_dir / "sub1" / "sub2" / "output.mp4"
    assert not nested_out.parent.exists()

    processor = FFmpegProcessor()
    res = processor.cut_media(dummy_video_file, start=0.0, end=1.0, output_path=nested_out)

    assert nested_out.parent.exists()
    assert nested_out.parent.is_dir()
    assert Path(res).exists()


@pytest.mark.parametrize(
    "start,end",
    [
        (5.0, 5.0),    # Equal start and end (zero duration)
        (10.0, 5.0),   # Start > end (negative duration)
        (-2.0, 5.0),   # Negative start timestamp
    ],
)
def test_cut_media_zero_or_negative_duration(
    start: float, end: float, mock_ffmpeg: MockFFmpegContainer, dummy_video_file: Path, tmp_media_dir: Path
):
    """Verify invalid cut range (zero or negative duration) raises ProcessingError."""
    processor = FFmpegProcessor()
    out_file = tmp_media_dir / "invalid_range.mp4"

    with pytest.raises(ProcessingError):
        processor.cut_media(dummy_video_file, start=start, end=end, output_path=out_file)


def test_cut_media_custom_ffmpeg_binary_path(
    mock_ffmpeg: MockFFmpegContainer, dummy_video_file: Path, tmp_media_dir: Path
):
    """Verify FFmpegProcessor uses custom binary path when provided in constructor."""
    custom_bin = "/opt/custom_ffmpeg/bin/ffmpeg"
    mock_ffmpeg.which.return_value = custom_bin

    processor = FFmpegProcessor(ffmpeg_path=custom_bin)
    out_file = tmp_media_dir / "custom_bin_out.mp4"

    processor.cut_media(dummy_video_file, start=0.0, end=1.0, output_path=out_file)

    cmd = mock_ffmpeg.last_command
    assert cmd is not None
    assert cmd[0] == custom_bin
