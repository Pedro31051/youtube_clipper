"""tests/test_downloader.py - Unit test suite for YouTubeDownloader.

Uses unittest.mock.patch to test YouTubeDownloader offline behavior, option setup,
download_ranges callback hook, progress callback, error wrapping into DownloadError,
and timestamp range validation via ValidationError.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
import yt_dlp.utils

from youtube_clipper.downloader import YouTubeDownloader
from youtube_clipper.exceptions import DownloadError, ValidationError


@pytest.fixture
def mock_ytdl(tmp_path: Path):
    """Fixture mocking yt_dlp.YoutubeDL context manager and methods."""
    with patch("yt_dlp.YoutubeDL") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        mock_instance.__enter__.return_value = mock_instance

        default_info = {
            "id": "dQw4w9WgXcQ",
            "title": "Synthetic Test Video",
            "ext": "mp4",
            "requested_downloads": [{"filepath": str(tmp_path / "dQw4w9WgXcQ_segment.mp4")}],
        }
        mock_instance.extract_info.return_value = default_info

        def extract_info_side_effect(url, download=True):
            ret = mock_instance.extract_info.return_value
            if ret is None:
                return None
            video_id = ret.get("id", "dQw4w9WgXcQ") if isinstance(ret, dict) else "dQw4w9WgXcQ"
            ext = ret.get("ext", "mp4") if isinstance(ret, dict) else "mp4"
            if mock_class.call_args:
                opts = mock_class.call_args[0][0]
                outtmpl = opts.get("outtmpl", "")
                if "%(id)s" in outtmpl:
                    out_path = Path(outtmpl.replace("%(id)s", video_id).replace("%(ext)s", ext))
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512)
            (tmp_path / f"{video_id}_segment.{ext}").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512)
            return ret

        mock_instance.extract_info.side_effect = extract_info_side_effect
        yield mock_class, mock_instance


def test_downloader_init_options() -> None:
    """Test YouTubeDownloader initialization with default and custom options."""
    d1 = YouTubeDownloader()
    assert d1.options == {}

    opts = {"format": "bestvideo", "quiet": False}
    d2 = YouTubeDownloader(options=opts)
    assert d2.options == opts


def test_download_segment_success(mock_ytdl, tmp_path: Path) -> None:
    """Test successful segment download returning absolute file path."""
    mock_class, mock_instance = mock_ytdl
    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    res = downloader.download_segment(url, start=10.0, end=30.0, output_dir=tmp_path)

    assert isinstance(res, str)
    assert Path(res).is_absolute()
    assert Path(res).exists()
    mock_instance.extract_info.assert_called_once_with(url, download=True)


def test_download_segment_range_callback(mock_ytdl, tmp_path: Path) -> None:
    """Test download_ranges callback configuration in ydl_opts."""
    mock_class, _ = mock_ytdl
    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    downloader.download_segment(url, start=15.0, end=45.0, output_dir=tmp_path)

    call_opts = mock_class.call_args[0][0]
    assert "download_ranges" in call_opts
    range_func = call_opts["download_ranges"]
    ranges = range_func({}, None)
    assert ranges == [{"start_time": 15.0, "end_time": 45.0}]


def test_download_segment_progress_callback(mock_ytdl, tmp_path: Path) -> None:
    """Test registering progress callback with yt-dlp."""
    mock_class, _ = mock_ytdl
    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def dummy_cb(d: Dict[str, Any]) -> None:
        pass

    downloader.download_segment(url, start=0.0, end=10.0, output_dir=tmp_path, progress_callback=dummy_cb)

    call_opts = mock_class.call_args[0][0]
    assert "progress_hooks" in call_opts
    assert dummy_cb in call_opts["progress_hooks"]


@pytest.mark.parametrize("start,end", [(10.0, 10.0), (20.0, 10.0), (-5.0, 10.0)])
def test_download_segment_invalid_ranges(start: float, end: float, tmp_path: Path) -> None:
    """Test invalid timestamp ranges raise ValidationError."""
    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    with pytest.raises(ValidationError):
        downloader.download_segment(url, start=start, end=end, output_dir=tmp_path)


def test_download_segment_ytdlp_error(mock_ytdl, tmp_path: Path) -> None:
    """Test catching yt_dlp.utils.DownloadError and wrapping into DownloadError."""
    _, mock_instance = mock_ytdl
    mock_instance.extract_info.side_effect = yt_dlp.utils.DownloadError("Video unavailable")
    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=bad_id"

    with pytest.raises(DownloadError) as exc_info:
        downloader.download_segment(url, start=0.0, end=10.0, output_dir=tmp_path)

    assert exc_info.value.url == url
    assert "unavailable" in str(exc_info.value).lower()


def test_download_segment_network_error(mock_ytdl, tmp_path: Path) -> None:
    """Test network connection error wrapping into DownloadError."""
    _, mock_instance = mock_ytdl
    mock_instance.extract_info.side_effect = ConnectionError("Network unreachable")
    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    with pytest.raises(DownloadError) as exc_info:
        downloader.download_segment(url, start=0.0, end=10.0, output_dir=tmp_path)

    assert exc_info.value.url == url
    assert "network" in str(exc_info.value).lower() or "failed" in str(exc_info.value).lower()


def test_download_segment_none_metadata(mock_ytdl, tmp_path: Path) -> None:
    """Test extract_info returning None raises DownloadError."""
    _, mock_instance = mock_ytdl
    mock_instance.extract_info.return_value = None
    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    with pytest.raises(DownloadError) as exc_info:
        downloader.download_segment(url, start=0.0, end=10.0, output_dir=tmp_path)

    assert exc_info.value.url == url
    assert "metadata" in str(exc_info.value).lower() or "failed" in str(exc_info.value).lower()


def test_download_segment_directory_creation(mock_ytdl, tmp_path: Path) -> None:
    """Test output directory creation if target directory does not exist."""
    new_dir = tmp_path / "new_output_dir"
    assert not new_dir.exists()

    downloader = YouTubeDownloader()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    res = downloader.download_segment(url, start=0.0, end=10.0, output_dir=new_dir)

    assert new_dir.exists()
    assert Path(res).parent == new_dir.resolve()
