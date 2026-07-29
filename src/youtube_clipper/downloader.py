"""YouTube stream downloader module wrapping yt-dlp Python API.

Provides YouTubeDownloader for extracting video stream segments by timestamp range,
with player_client fallback handling, cookies management, and browser cookies extraction.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import yt_dlp
import yt_dlp.utils

from cortes.log import audited
from youtube_clipper.exceptions import DownloadError, ValidationError
from youtube_clipper.validator import validate_time_range


class YouTubeDownloader:
    """YouTube media stream downloader wrapping the yt-dlp Python API."""

    def __init__(self, options: Optional[Dict[str, Any]] = None) -> None:
        """Initialize YouTubeDownloader with optional custom yt-dlp configuration options."""
        self.options = options or {}

    @audited(
        stage="ingest",
        action="youtube.download_segment",
        component="youtube_clipper.downloader",
    )
    def download_segment(
        self,
        url: str,
        start: float,
        end: float,
        output_dir: Union[str, Path],
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> str:
        """Download a timestamp segment from a YouTube video into output_dir."""
        start_sec, end_sec = validate_time_range(start, end)
        out_dir = Path(output_dir).resolve()

        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise DownloadError(f"Failed to create output directory {out_dir}: {e}", url=url) from e

        # Construct default robust yt-dlp options
        ydl_opts: Dict[str, Any] = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": str(out_dir / "%(id)s_segment.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["mweb", "android", "ios", "web"]
                }
            }
        }

        # Check for cookies file or browser
        cookie_setting = os.environ.get("YOUTUBE_COOKIES_FILE") or os.path.join(os.getcwd(), "cookies.txt")
        if cookie_setting and os.path.exists(cookie_setting):
            ydl_opts["cookiefile"] = cookie_setting
        elif cookie_setting and cookie_setting.lower() in ("chrome", "firefox", "brave", "edge", "safari", "opera"):
            ydl_opts["cookiesfrombrowser"] = (cookie_setting.lower(),)

        # Apply custom options override
        if self.options:
            ydl_opts.update(self.options)

        # Configure progress callback hook
        if progress_callback:
            hooks = list(ydl_opts.get("progress_hooks", []))
            hooks.append(progress_callback)
            ydl_opts["progress_hooks"] = hooks

        # Configure timestamp trimming range callback
        def range_func(info_dict: Any, ydl: Any) -> List[Dict[str, float]]:
            return [{"start_time": start_sec, "end_time": end_sec}]

        ydl_opts["download_ranges"] = range_func

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise DownloadError(f"Failed to extract video metadata for {url}", url=url)

                video_id = "downloaded_segment"
                ext = "mp4"
                if isinstance(info, dict):
                    if isinstance(info.get("id"), str):
                        video_id = info["id"]
                    if isinstance(info.get("ext"), str):
                        ext = info["ext"]

                output_file_path = out_dir / f"{video_id}_segment.{ext}"

                if not output_file_path.exists():
                    found = list(out_dir.glob("*.mp4")) or list(out_dir.glob("*_segment.*"))
                    if found:
                        return str(found[0].resolve())
                    raise DownloadError(f"Downloaded output file was not found at {output_file_path}", url=url)

                return str(output_file_path.resolve())

        except (DownloadError, ValidationError):
            raise
        except yt_dlp.utils.YoutubeDLError as e:
            raise DownloadError(f"yt-dlp download error for {url}: {e}", url=url) from e
        except (ConnectionError, TimeoutError, OSError) as e:
            raise DownloadError(f"Download failed for {url}: {e}", url=url) from e
        except Exception as e:
            raise DownloadError(f"Download failed for {url}: {e}", url=url) from e
