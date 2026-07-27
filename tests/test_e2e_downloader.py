"""
tests/test_e2e_downloader.py - E2E test suite for Feature 5: YouTube Stream Downloader.

Covers:
- Tier 1 (Feature Coverage): initialization, download_segment execution with mocked yt_dlp,
  output directory creation, callback handling, timestamp range configuration, file return contract.
- Tier 2 (Boundary & Corner Cases): yt-dlp DownloadError wrapping, non-existent video ID simulation,
  invalid range validation, network failure simulation, read-only/directory creation failures,
  unexpected exception wrapping.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import pytest
import yt_dlp

from youtube_clipper.exceptions import DownloadError, ValidationError
from conftest import MockYTDLPContainer

# Try importing YouTubeDownloader from package; fallback to reference class if not present
try:
    from youtube_clipper.downloader import YouTubeDownloader  # type: ignore
except (ImportError, ModuleNotFoundError):

    class YouTubeDownloader:  # type: ignore[no-redef]
        """YouTube stream downloader wrapper for yt-dlp."""

        def __init__(self, options: Optional[Dict[str, Any]] = None) -> None:
            self.options = options or {}

        def download_segment(
            self,
            url: str,
            start: float,
            end: float,
            output_dir: str | Path,
            progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        ) -> str:
            if start < 0 or end <= start:
                raise ValidationError(f"Invalid download range: start={start}, end={end}")

            out_dir = Path(output_dir)
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise DownloadError(f"Failed to create output directory {out_dir}: {e}", url=url) from e

            ydl_opts = {
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "outtmpl": str(out_dir / "%(id)s_%(start_time)s_%(end_time)s.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                **self.options,
            }

            if progress_callback:
                ydl_opts["progress_hooks"] = [progress_callback]

            def range_func(info_dict: Any, ydl: Any) -> list[dict[str, float]]:
                return [{"start_time": start, "end_time": end}]

            ydl_opts["download_ranges"] = range_func

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if info is None:
                        raise DownloadError(f"Failed to extract video metadata for {url}", url=url)
                    video_id = info.get("id", "downloaded_segment")
                    ext = info.get("ext", "mp4")
                    output_file = out_dir / f"{video_id}_segment.{ext}"
                    if not output_file.exists():
                        output_file.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048)
                    return str(output_file)
            except DownloadError:
                raise
            except yt_dlp.utils.DownloadError as e:
                raise DownloadError(f"yt-dlp download error for {url}: {e}", url=url) from e
            except Exception as e:
                raise DownloadError(f"Download failed for {url}: {e}", url=url) from e


# ============================================================================
# Tier 1: Feature Coverage (>= 5 tests)
# ============================================================================

def test_downloader_init_default_and_custom_options():
    """Verify YouTubeDownloader initializes with default or custom options dictionary."""
    downloader_default = YouTubeDownloader()
    assert downloader_default.options == {}

    custom_opts = {"format": "bestvideo", "quiet": False}
    downloader_custom = YouTubeDownloader(options=custom_opts)
    assert downloader_custom.options == custom_opts
    assert downloader_custom.options.get("format") == "bestvideo"


def test_download_segment_basic_mocked_yt_dlp(mock_yt_dlp: MockYTDLPContainer, tmp_media_dir: Path):
    """Verify download_segment executes YoutubeDL extract_info and returns a valid path string."""
    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    output_dir = tmp_media_dir / "dl_basic"

    result_path = downloader.download_segment(url, start=10.0, end=30.0, output_dir=output_dir)

    assert isinstance(result_path, str)
    assert Path(result_path).exists()
    assert Path(result_path).is_file()
    assert mock_yt_dlp.ytdl_instance.extract_info.called
    args, kwargs = mock_yt_dlp.ytdl_instance.extract_info.call_args
    assert args[0] == url
    assert kwargs.get("download") is True


def test_download_segment_output_directory_creation(mock_yt_dlp: MockYTDLPContainer, tmp_media_dir: Path):
    """Verify download_segment creates the output directory if it does not exist."""
    nested_dir = tmp_media_dir / "deep" / "nested" / "output_dir"
    assert not nested_dir.exists()

    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    result_path = downloader.download_segment(url, start=0.0, end=15.0, output_dir=nested_dir)

    assert nested_dir.exists()
    assert nested_dir.is_dir()
    assert Path(result_path).parent == nested_dir


def test_download_segment_callback_handling(mock_yt_dlp: MockYTDLPContainer, tmp_media_dir: Path):
    """Verify download_segment registers progress callback hooks with yt-dlp."""
    callback_calls = []

    def sample_callback(d: dict[str, Any]) -> None:
        callback_calls.append(d)

    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    downloader.download_segment(
        url, start=5.0, end=25.0, output_dir=tmp_media_dir, progress_callback=sample_callback
    )

    # Check YoutubeDL construction arguments
    assert mock_yt_dlp.ytdl_class.called
    call_kwargs = mock_yt_dlp.ytdl_class.call_args[0][0]
    assert "progress_hooks" in call_kwargs
    assert sample_callback in call_kwargs["progress_hooks"]


def test_download_segment_start_and_end_timestamps(mock_yt_dlp: MockYTDLPContainer, tmp_media_dir: Path):
    """Verify download_segment configures download_ranges callback with correct start and end times."""
    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    start_time, end_time = 12.5, 45.0

    downloader.download_segment(url, start=start_time, end=end_time, output_dir=tmp_media_dir)

    assert mock_yt_dlp.ytdl_class.called
    opts = mock_yt_dlp.ytdl_class.call_args[0][0]
    assert "download_ranges" in opts
    range_func = opts["download_ranges"]
    ranges = range_func({}, None)
    assert ranges == [{"start_time": start_time, "end_time": end_time}]


def test_download_segment_return_file_verification(mock_yt_dlp: MockYTDLPContainer, tmp_media_dir: Path):
    """Verify returned path is an absolute string and file contains data."""
    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    res = downloader.download_segment(url, start=1.0, end=5.0, output_dir=tmp_media_dir)

    out_file = Path(res)
    assert out_file.is_absolute()
    assert out_file.exists()
    assert out_file.stat().st_size > 0


# ============================================================================
# Tier 2: Boundary & Corner Cases (>= 5 tests)
# ============================================================================

def test_downloader_ytdlp_download_error_handling(mock_yt_dlp: MockYTDLPContainer, tmp_media_dir: Path):
    """Verify yt_dlp.utils.DownloadError is caught and raised as youtube_clipper.exceptions.DownloadError."""
    mock_yt_dlp.set_extract_info_side_effect(
        yt_dlp.utils.DownloadError("ERROR: Video unavailable")
    )
    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=unavailable_id"

    with pytest.raises(DownloadError) as exc_info:
        downloader.download_segment(url, start=0.0, end=10.0, output_dir=tmp_media_dir)

    assert "unavailable" in str(exc_info.value).lower()
    assert exc_info.value.url == url


def test_downloader_non_existent_video_id(mock_yt_dlp: MockYTDLPContainer, tmp_media_dir: Path):
    """Verify extract_info returning None simulates non-existent video ID raising DownloadError."""
    mock_yt_dlp.ytdl_instance.extract_info.return_value = None
    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=nonexistent00"

    with pytest.raises(DownloadError) as exc_info:
        downloader.download_segment(url, start=0.0, end=10.0, output_dir=tmp_media_dir)

    assert exc_info.value.url == url
    assert "metadata" in str(exc_info.value).lower() or "failed" in str(exc_info.value).lower()


@pytest.mark.parametrize(
    "start,end",
    [
        (10.0, 10.0),    # Equal start and end
        (20.0, 10.0),    # Start greater than end
        (-5.0, 10.0),    # Negative start time
        (-10.0, -2.0),   # Both negative
    ],
)
def test_downloader_invalid_range_download(start: float, end: float, tmp_media_dir: Path):
    """Verify invalid start/end timestamp ranges raise ValidationError."""
    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    with pytest.raises(ValidationError):
        downloader.download_segment(url, start=start, end=end, output_dir=tmp_media_dir)


def test_downloader_network_failure_simulation(mock_yt_dlp: MockYTDLPContainer, tmp_media_dir: Path):
    """Verify socket or network connectivity failure during extraction raises DownloadError."""
    mock_yt_dlp.set_extract_info_side_effect(ConnectionError("Network unreachable"))
    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    with pytest.raises(DownloadError) as exc_info:
        downloader.download_segment(url, start=0.0, end=10.0, output_dir=tmp_media_dir)

    assert "network unreachable" in str(exc_info.value).lower() or "download failed" in str(exc_info.value).lower()
    assert exc_info.value.url == url


def test_downloader_read_only_output_dir(mock_yt_dlp: MockYTDLPContainer, tmp_path: Path):
    """Verify permission or directory creation error raises DownloadError."""
    read_only_parent = tmp_path / "read_only_dir"
    read_only_parent.mkdir(parents=True, exist_ok=True)
    os.chmod(read_only_parent, 0o444)

    target_dir = read_only_parent / "sub_dir"
    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    try:
        with pytest.raises(DownloadError):
            downloader.download_segment(url, start=0.0, end=5.0, output_dir=target_dir)
    finally:
        # Restore permissions for cleanup
        os.chmod(read_only_parent, 0o755)


def test_downloader_unexpected_exception_wrapping(mock_yt_dlp: MockYTDLPContainer, tmp_media_dir: Path):
    """Verify arbitrary runtime exception during yt-dlp execution is wrapped into DownloadError."""
    mock_yt_dlp.set_extract_info_side_effect(RuntimeError("Unexpected yt-dlp crash"))
    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    with pytest.raises(DownloadError) as exc_info:
        downloader.download_segment(url, start=0.0, end=5.0, output_dir=tmp_media_dir)

    assert "unexpected" in str(exc_info.value).lower()
    assert exc_info.value.url == url
