"""
tests/test_conftest.py - Verification suite for tests/conftest.py shared fixtures.
"""

from pathlib import Path
import subprocess
import sys
import pytest

from conftest import MockYTDLPContainer, MockFFmpegContainer, CLIRunnerResult


def test_tmp_media_dir_fixture(tmp_media_dir: Path):
    """Verify tmp_media_dir fixture creates an existing directory."""
    assert isinstance(tmp_media_dir, Path)
    assert tmp_media_dir.exists()
    assert tmp_media_dir.is_dir()


def test_dummy_video_file_fixture(dummy_video_file: Path, tmp_media_dir: Path):
    """Verify dummy_video_file fixture creates a non-empty media file inside tmp_media_dir."""
    assert isinstance(dummy_video_file, Path)
    assert dummy_video_file.exists()
    assert dummy_video_file.is_file()
    assert dummy_video_file.stat().st_size > 0
    assert dummy_video_file.parent == tmp_media_dir


def test_mock_yt_dlp_fixture(mock_yt_dlp: MockYTDLPContainer):
    """Verify mock_yt_dlp fixture mocks YoutubeDL metadata extraction and error injection."""
    assert isinstance(mock_yt_dlp, MockYTDLPContainer)
    
    # Verify default extract_info metadata
    info = mock_yt_dlp.ytdl_instance.extract_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert info["id"] == "dQw4w9WgXcQ"
    assert info["duration"] == 180.0
    
    # Test error side effect setting
    mock_yt_dlp.set_extract_info_side_effect(RuntimeError("Network unreachable"))
    with pytest.raises(RuntimeError, match="Network unreachable"):
        mock_yt_dlp.ytdl_instance.extract_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


def test_mock_ffmpeg_fixture(mock_ffmpeg: MockFFmpegContainer, tmp_media_dir: Path):
    """Verify mock_ffmpeg fixture intercepts subprocess calls, records arguments, and supports failure modes."""
    assert isinstance(mock_ffmpeg, MockFFmpegContainer)
    
    out_file = tmp_media_dir / "output.mp4"
    res = subprocess.run(["ffmpeg", "-ss", "00:00:10", "-i", "input.mp4", str(out_file)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    assert res.returncode == 0
    assert mock_ffmpeg.last_command == ["ffmpeg", "-ss", "00:00:10", "-i", "input.mp4", str(out_file)]
    assert mock_ffmpeg.has_arg("-ss")
    assert mock_ffmpeg.has_arg("-i")
    assert out_file.exists()
    
    # Test missing ffmpeg simulation
    mock_ffmpeg.simulate_missing_ffmpeg()
    with pytest.raises(FileNotFoundError):
        subprocess.run(["ffmpeg", "-version"])

    # Test execution failure simulation
    mock_ffmpeg.simulate_failure(returncode=1, stderr="Invalid codec option")
    failed_res = subprocess.run(["ffmpeg", "-invalid"])
    assert failed_res.returncode == 1
    assert "Invalid codec" in failed_res.stderr


def test_cli_runner_fixture(cli_runner):
    """Verify cli_runner captures stdout, stderr, exit codes, and exceptions."""
    def sample_main_success():
        print("CLI Execution Success")
        print("Warning message", file=sys.stderr)

    res_success = cli_runner("--start 00:00:10 --end 00:00:20 input.mp4", target_func=sample_main_success)
    assert res_success.exit_code == 0
    assert "CLI Execution Success" in res_success.stdout
    assert "Warning message" in res_success.stderr
    assert res_success.exception is None

    def sample_main_exit():
        print("Exiting with error", file=sys.stderr)
        sys.exit(2)

    res_exit = cli_runner("--invalid", target_func=sample_main_exit)
    assert res_exit.exit_code == 2
    assert "Exiting with error" in res_exit.stderr

    def sample_main_error():
        raise ValueError("Invalid timestamp range")

    res_error = cli_runner("--start 00:00:20 --end 00:00:10", target_func=sample_main_error)
    assert res_error.exit_code == 1
    assert isinstance(res_error.exception, ValueError)
    assert str(res_error.exception) == "Invalid timestamp range"
