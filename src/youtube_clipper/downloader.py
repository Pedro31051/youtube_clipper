"""YouTube stream downloader module wrapping the yt-dlp Python API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union, cast

import yt_dlp
import yt_dlp.utils

from youtube_clipper.exceptions import DownloadError, ValidationError
from youtube_clipper.validator import validate_time_range


_BROWSER_NAMES = {"chrome", "firefox", "brave", "edge", "safari", "opera"}


class YouTubeDownloader:
    """YouTube media stream downloader wrapping the yt-dlp Python API."""

    def __init__(
        self,
        options: Optional[Dict[str, Any]] = None,
        cookies: Optional[str] = None,
    ) -> None:
        """Initialize with custom yt-dlp options and request-scoped cookies."""
        self.options = options or {}
        self.cookies = cookies

    def _build_options(
        self,
        out_dir: Path,
        suffix: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]],
    ) -> Dict[str, Any]:
        ydl_opts: Dict[str, Any] = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": str(out_dir / f"%(id)s{suffix}.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "extractor_args": {
                "youtube": {"player_client": ["mweb", "android", "ios", "web"]}
            },
        }

        configured_cookies = self.cookies
        if configured_cookies is None:
            configured_cookies = os.environ.get("YOUTUBE_COOKIES_FILE")
        if configured_cookies is None:
            local_cookie_file = Path.cwd() / "cookies.txt"
            if local_cookie_file.exists():
                configured_cookies = str(local_cookie_file)

        if configured_cookies:
            cookie_value = str(configured_cookies).strip()
            if cookie_value.lower() in _BROWSER_NAMES:
                ydl_opts["cookiesfrombrowser"] = (cookie_value.lower(),)
            else:
                cookie_path = Path(cookie_value).expanduser()
                ydl_opts["cookiefile"] = str(cookie_path.resolve())

        ydl_opts.update(self.options)
        # TLS verification is a security invariant, not a caller-overridable default.
        ydl_opts.pop("nocheckcertificate", None)

        if progress_callback:
            hooks = list(ydl_opts.get("progress_hooks", []))
            hooks.append(progress_callback)
            ydl_opts["progress_hooks"] = hooks
        return ydl_opts

    @staticmethod
    def _snapshot(out_dir: Path) -> Dict[Path, tuple[int, int]]:
        return {
            path.resolve(): (path.stat().st_mtime_ns, path.stat().st_size)
            for path in out_dir.iterdir()
            if path.is_file()
        }

    @staticmethod
    def _resolve_output(
        out_dir: Path,
        info: Dict[str, Any],
        suffix: str,
        before: Dict[Path, tuple[int, int]],
        url: str,
    ) -> str:
        video_id = info.get("id") if isinstance(info.get("id"), str) else "downloaded"
        ext = info.get("ext") if isinstance(info.get("ext"), str) else "mp4"
        candidates: List[Path] = [out_dir / f"{video_id}{suffix}.{ext}"]
        for item in info.get("requested_downloads", []) or []:
            if isinstance(item, dict) and item.get("filepath"):
                candidates.append(Path(str(item["filepath"])))
        candidates.extend(sorted(path for path in out_dir.iterdir() if path.is_file()))

        output_root = out_dir.resolve()
        for candidate in candidates:
            resolved = candidate.resolve()
            try:
                resolved.relative_to(output_root)
            except ValueError:
                continue
            if not resolved.exists() or not resolved.is_file():
                continue
            current = (resolved.stat().st_mtime_ns, resolved.stat().st_size)
            if resolved not in before or before[resolved] != current:
                return str(resolved)

        raise DownloadError(
            "yt-dlp completed but no new or changed output file was found",
            url=url,
        )

    def _download(
        self,
        url: str,
        output_dir: Union[str, Path],
        *,
        start_sec: Optional[float] = None,
        end_sec: Optional[float] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> str:
        out_dir = Path(output_dir).resolve()
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            raise DownloadError(
                f"Failed to create output directory {out_dir}: {exc}", url=url
            ) from exc

        suffix = "_segment" if start_sec is not None else "_full"
        before = self._snapshot(out_dir)
        ydl_opts = self._build_options(out_dir, suffix, progress_callback)
        if start_sec is not None and end_sec is not None:
            def range_func(_info_dict: Any, _ydl: Any) -> List[Dict[str, float]]:
                return [{"start_time": start_sec, "end_time": end_sec}]

            ydl_opts["download_ranges"] = range_func

        try:
            with yt_dlp.YoutubeDL(cast(Any, ydl_opts)) as ydl:
                info = ydl.extract_info(url, download=True)
                if not isinstance(info, dict):
                    raise DownloadError(
                        f"Failed to extract video metadata for {url}", url=url
                    )
                return self._resolve_output(
                    out_dir,
                    cast(Dict[str, Any], info),
                    suffix,
                    before,
                    url,
                )
        except (DownloadError, ValidationError):
            raise
        except yt_dlp.utils.YoutubeDLError as exc:
            raise DownloadError(f"yt-dlp download error for {url}: {exc}", url=url) from exc
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise DownloadError(f"Download failed for {url}: {exc}", url=url) from exc
        except Exception as exc:
            raise DownloadError(f"Download failed for {url}: {exc}", url=url) from exc

    def download_segment(
        self,
        url: str,
        start: float,
        end: float,
        output_dir: Union[str, Path],
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> str:
        """Download one validated timestamp segment from a YouTube video."""
        start_sec, end_sec = validate_time_range(start, end)
        return self._download(
            url,
            output_dir,
            start_sec=start_sec,
            end_sec=end_sec,
            progress_callback=progress_callback,
        )

    def download(
        self,
        url: str,
        output_dir: Union[str, Path],
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> str:
        """Download the complete video without manufacturing a 0–0 time range."""
        return self._download(
            url,
            output_dir,
            progress_callback=progress_callback,
        )
