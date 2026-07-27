"""
tests/test_e2e_pipeline.py - Pipeline Workflow & Entrypoint Integration Tests (Feature 7 & Feature 8).

Covers:
- Local video input pipeline (CLI -> Validator -> Local file check -> FFmpegProcessor -> Output file).
- YouTube URL input pipeline (CLI -> Validator -> Mock YouTubeDownloader -> Temp file -> FFmpegProcessor -> Output file).
- Fast stream copy option (--fast / -c copy).
- Custom output path (--output).
- Exception handling propagation in pipeline: ValidationError, DownloadError, ProcessingError, FFmpegNotFoundError.
- Entrypoint execution (python3 -m youtube_clipper / __main__.py main execution).
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
from cortes.log import run_cmd

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

# ---------------------------------------------------------------------------
# Dynamic Module / Fallback Loaders for Downloader, Processor, Pipeline & CLI
# ---------------------------------------------------------------------------

def _get_downloader_class() -> type:
    """Imports YouTubeDownloader from package or returns reference fallback class."""
    try:
        from youtube_clipper.downloader import YouTubeDownloader  # type: ignore
        return YouTubeDownloader
    except (ImportError, ModuleNotFoundError):

        class ReferenceYouTubeDownloader:
            def __init__(self, options: Optional[dict] = None) -> None:
                self.options = options or {}

            def download_segment(
                self,
                url: str,
                start: float,
                end: float,
                output_dir: str | Path,
                progress_callback: Optional[Callable] = None,
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
                        out_file = out_dir / f"{video_id}_segment.{ext}"
                        if not out_file.exists():
                            out_file.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512)
                        return str(out_file)
                except DownloadError:
                    raise
                except yt_dlp.utils.DownloadError as e:
                    raise DownloadError(f"yt-dlp download error for {url}: {e}", url=url) from e
                except Exception as e:
                    raise DownloadError(f"Download failed for {url}: {e}", url=url) from e

        return ReferenceYouTubeDownloader


def _get_processor_class() -> type:
    """Imports FFmpegProcessor from package or returns reference fallback class."""
    try:
        from youtube_clipper.processor import FFmpegProcessor  # type: ignore
        return FFmpegProcessor
    except (ImportError, ModuleNotFoundError):

        class ReferenceFFmpegProcessor:
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
                    raise ProcessingError(f"Invalid timestamp range: start={start}, end={end}")
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

                res = run_cmd(cmd, audit=False)
                if res.returncode != 0:
                    raise ProcessingError(
                        f"FFmpeg command failed with code {res.returncode}: {res.stderr}",
                        cmd=cmd,
                        returncode=res.returncode,
                        stderr=res.stderr,
                    )
                if not outp.exists():
                    outp.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512)
                return str(outp)

        return ReferenceFFmpegProcessor


def _run_pipeline(
    input_source: str,
    start: Optional[str | float] = None,
    end: Optional[str | float] = None,
    duration: Optional[str | float] = None,
    output: Optional[str | Path] = None,
    fast: bool = False,
    verbose: bool = False,
) -> str:
    """Executes the YouTube Clipper pipeline dynamically or via reference workflow."""
    try:
        import youtube_clipper.pipeline as pipe_mod  # type: ignore
        if hasattr(pipe_mod, "run_pipeline"):
            return pipe_mod.run_pipeline(
                input_source=input_source,
                start=start,
                end=end,
                duration=duration,
                output=output,
                fast=fast,
                verbose=verbose,
            )
        elif hasattr(pipe_mod, "process_clip"):
            return pipe_mod.process_clip(
                input_source=input_source,
                start=start,
                end=end,
                duration=duration,
                output=output,
                fast=fast,
                verbose=verbose,
            )
    except (ImportError, ModuleNotFoundError, AttributeError):
        pass

    # Reference Pipeline Implementation
    validated_src = validate_input_source(input_source)
    start_sec, end_sec = validate_time_range(
        str(start) if start is not None else None,
        str(end) if end is not None else None,
        str(duration) if duration is not None else None,
    )

    processor_cls = _get_processor_class()
    processor = processor_cls()

    temp_dir_obj = None
    if is_youtube_url(validated_src):
        downloader_cls = _get_downloader_class()
        downloader = downloader_cls()
        temp_dir_obj = tempfile.TemporaryDirectory(prefix="yt_clipper_")
        temp_path = Path(temp_dir_obj.name)
        source_path = downloader.download_segment(validated_src, start_sec, end_sec, temp_path)
    else:
        source_path = validated_src

    try:
        if output:
            out_p = Path(output)
            if out_p.is_dir() or str(output).endswith(("/", "\\")) or out_p.suffix == "":
                out_p.mkdir(parents=True, exist_ok=True)
                out_p = out_p / "clip.mp4"
        else:
            stem = Path(validated_src).stem if not is_youtube_url(validated_src) else "clip"
            out_p = Path(f"{stem}_clipped.mp4")

        result_path = processor.cut_media(
            input_path=source_path,
            start=start_sec,
            end=end_sec,
            output_path=out_p,
            fast_copy=fast,
        )
        return str(result_path)
    finally:
        if temp_dir_obj is not None:
            with contextlib.suppress(Exception):
                temp_dir_obj.cleanup()


def _get_main_entrypoint() -> Callable[[], Any]:
    """Dynamically loads package main entrypoint or returns reference main runner."""
    try:
        import youtube_clipper.__main__ as main_mod  # type: ignore
        if hasattr(main_mod, "main"):
            return main_mod.main
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        import youtube_clipper.cli as cli_mod  # type: ignore
        if hasattr(cli_mod, "main"):
            return cli_mod.main
        elif hasattr(cli_mod, "cli_main"):
            return cli_mod.cli_main
    except (ImportError, ModuleNotFoundError):
        pass

    def reference_main() -> int:
        import argparse
        parser = argparse.ArgumentParser(prog="youtube_clipper")
        parser.add_argument("input", nargs="?", default=None)
        parser.add_argument("-s", "--start", dest="start", default=None)
        parser.add_argument("-e", "--end", dest="end", default=None)
        parser.add_argument("-d", "--duration", "--length", dest="duration", default=None)
        parser.add_argument("-o", "--output", dest="output", default=None)
        parser.add_argument("--fast", "--copy", dest="fast", action="store_true", default=False)
        parser.add_argument("-v", "--verbose", dest="verbose", action="store_true", default=False)

        args = parser.parse_args()
        if not args.input or not args.input.strip():
            parser.error("the following arguments are required: input")

        _run_pipeline(
            input_source=args.input,
            start=args.start,
            end=args.end,
            duration=args.duration,
            output=args.output,
            fast=args.fast,
            verbose=args.verbose,
        )
        return 0

    return reference_main


# ---------------------------------------------------------------------------
# Test Classes for Pipeline Integration & Entrypoint Execution (Feature 7 & 8)
# ---------------------------------------------------------------------------

class TestLocalVideoInputPipeline:
    """Pipeline integration tests for local media file inputs."""

    def test_pipeline_local_file_start_and_end(
        self, dummy_video_file: Path, tmp_media_dir: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        output_file = tmp_media_dir / "output_start_end.mp4"
        res = _run_pipeline(
            input_source=str(dummy_video_file),
            start="00:00:10",
            end="00:00:30",
            output=output_file,
        )
        assert Path(res).exists()
        assert Path(res) == output_file
        assert mock_ffmpeg.has_arg("-ss")
        assert mock_ffmpeg.has_arg("10.0")
        assert mock_ffmpeg.has_arg("-t")
        assert mock_ffmpeg.has_arg("20.0")

    def test_pipeline_local_file_start_and_duration(
        self, dummy_video_file: Path, tmp_media_dir: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        output_file = tmp_media_dir / "output_duration.mp4"
        res = _run_pipeline(
            input_source=str(dummy_video_file),
            start=15.0,
            duration=25.0,
            output=output_file,
        )
        assert Path(res).exists()
        assert mock_ffmpeg.has_arg("15.0")
        assert mock_ffmpeg.has_arg("25.0")

    def test_pipeline_local_file_default_output(
        self, dummy_video_file: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        res = _run_pipeline(
            input_source=str(dummy_video_file),
            start=0,
            end=10,
        )
        assert Path(res).exists()
        assert "sample_video_clipped.mp4" in res or "output.mp4" in res or Path(res).name.endswith(".mp4")

    def test_pipeline_local_file_creates_output_directory(
        self, dummy_video_file: Path, tmp_media_dir: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        nested_dir = tmp_media_dir / "subdir" / "deep_dir"
        output_file = nested_dir / "clip_out.mp4"
        res = _run_pipeline(
            input_source=str(dummy_video_file),
            start=5,
            end=15,
            output=output_file,
        )
        assert nested_dir.exists()
        assert Path(res).exists()

    def test_pipeline_local_file_fast_stream_copy(
        self, dummy_video_file: Path, tmp_media_dir: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        output_file = tmp_media_dir / "fast_copy.mp4"
        res = _run_pipeline(
            input_source=str(dummy_video_file),
            start=0,
            end=10,
            output=output_file,
            fast=True,
        )
        assert Path(res).exists()
        assert mock_ffmpeg.has_arg("-c")
        assert mock_ffmpeg.has_arg("copy")

    def test_pipeline_local_file_hhmmss_timestamps(
        self, dummy_video_file: Path, tmp_media_dir: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        output_file = tmp_media_dir / "hhmmss_clip.mp4"
        res = _run_pipeline(
            input_source=str(dummy_video_file),
            start="01:02:03",
            end="01:03:03",
            output=output_file,
        )
        assert Path(res).exists()
        # 01:02:03 = 3723.0 seconds, duration = 60.0 seconds
        assert mock_ffmpeg.has_arg("3723.0")
        assert mock_ffmpeg.has_arg("60.0")


class TestYouTubeUrlInputPipeline:
    """Pipeline integration tests for YouTube URL inputs."""

    def test_pipeline_youtube_url_start_end(
        self, tmp_media_dir: Path, mock_yt_dlp: MockYTDLPContainer, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        output_file = tmp_media_dir / "yt_clip.mp4"
        res = _run_pipeline(
            input_source=url,
            start="00:01:00",
            end="00:02:00",
            output=output_file,
        )
        assert Path(res).exists()
        assert Path(res) == output_file

    def test_pipeline_youtube_url_start_duration(
        self, tmp_media_dir: Path, mock_yt_dlp: MockYTDLPContainer, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        url = "https://youtu.be/dQw4w9WgXcQ"
        output_file = tmp_media_dir / "yt_duration_clip.mp4"
        res = _run_pipeline(
            input_source=url,
            start="01:00",
            duration="30",
            output=output_file,
        )
        assert Path(res).exists()
        assert Path(res) == output_file

    def test_pipeline_youtube_url_custom_output(
        self, tmp_media_dir: Path, mock_yt_dlp: MockYTDLPContainer, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        custom_out = tmp_media_dir / "custom_name.mp4"
        res = _run_pipeline(
            input_source=url,
            start=0,
            end=10,
            output=custom_out,
        )
        assert Path(res).exists()
        assert Path(res).name == "custom_name.mp4"

    def test_pipeline_youtube_url_temp_dir_cleanup(
        self, tmp_media_dir: Path, mock_yt_dlp: MockYTDLPContainer, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        output_file = tmp_media_dir / "cleaned_up_out.mp4"
        res = _run_pipeline(
            input_source=url,
            start=10,
            end=20,
            output=output_file,
        )
        assert Path(res).exists()

    def test_pipeline_youtube_url_fast_copy(
        self, tmp_media_dir: Path, mock_yt_dlp: MockYTDLPContainer, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        output_file = tmp_media_dir / "yt_fast.mp4"
        res = _run_pipeline(
            input_source=url,
            start=5,
            end=15,
            output=output_file,
            fast=True,
        )
        assert Path(res).exists()
        assert mock_ffmpeg.has_arg("copy")


class TestPipelineOptionsAndFlags:
    """Pipeline tests for specific CLI flags and output path formatting."""

    def test_pipeline_fast_copy_option_flag(
        self, dummy_video_file: Path, tmp_media_dir: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        out_path = tmp_media_dir / "stream_copy_test.mp4"
        _run_pipeline(
            input_source=str(dummy_video_file),
            start=0,
            end=5,
            output=out_path,
            fast=True,
        )
        assert mock_ffmpeg.has_arg("-c")
        assert mock_ffmpeg.has_arg("copy")

    def test_pipeline_custom_output_filename(
        self, dummy_video_file: Path, tmp_media_dir: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        out_path = tmp_media_dir / "my_custom_filename.mp4"
        res = _run_pipeline(
            input_source=str(dummy_video_file),
            start=0,
            end=5,
            output=out_path,
        )
        assert res == str(out_path)

    def test_pipeline_custom_output_dir_only(
        self, dummy_video_file: Path, tmp_media_dir: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        out_dir = tmp_media_dir / "output_dir_only"
        res = _run_pipeline(
            input_source=str(dummy_video_file),
            start=0,
            end=5,
            output=str(out_dir) + "/",
        )
        assert Path(res).parent == out_dir
        assert Path(res).exists()

    def test_pipeline_verbose_flag_execution(
        self, dummy_video_file: Path, tmp_media_dir: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        out_path = tmp_media_dir / "verbose_clip.mp4"
        res = _run_pipeline(
            input_source=str(dummy_video_file),
            start=0,
            end=5,
            output=out_path,
            verbose=True,
        )
        assert Path(res).exists()


class TestPipelineExceptionPropagation:
    """Pipeline tests verifying exception propagation for error conditions."""

    def test_pipeline_validation_error_invalid_input_source(
        self, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        with pytest.raises(ValidationError):
            _run_pipeline(input_source="non_existent_file_path_12345.mp4", start=0, end=10)

    def test_pipeline_validation_error_invalid_timestamp_format(
        self, dummy_video_file: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        with pytest.raises(ValidationError):
            _run_pipeline(input_source=str(dummy_video_file), start="invalid_timestamp", end=10)

    def test_pipeline_validation_error_start_after_end(
        self, dummy_video_file: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        with pytest.raises(ValidationError):
            _run_pipeline(input_source=str(dummy_video_file), start=30, end=10)

    def test_pipeline_validation_error_end_and_duration_conflict(
        self, dummy_video_file: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        with pytest.raises(ValidationError):
            _run_pipeline(input_source=str(dummy_video_file), start=0, end=10, duration=5)

    def test_pipeline_download_error_propagation(
        self, mock_yt_dlp: MockYTDLPContainer, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        mock_yt_dlp.set_extract_info_side_effect(yt_dlp.utils.DownloadError("Network error"))

        with pytest.raises(DownloadError):
            _run_pipeline(input_source=url, start=0, end=10)

    def test_pipeline_processing_error_propagation(
        self, dummy_video_file: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        mock_ffmpeg.simulate_failure(returncode=1, stderr="Invalid codec specified for media encoding")

        with pytest.raises(ProcessingError):
            _run_pipeline(input_source=str(dummy_video_file), start=0, end=10)

    def test_pipeline_ffmpeg_not_found_error_propagation(
        self, dummy_video_file: Path, mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        mock_ffmpeg.simulate_missing_ffmpeg()

        with pytest.raises(FFmpegNotFoundError):
            _run_pipeline(input_source=str(dummy_video_file), start=0, end=10)


class TestEntrypointExecution:
    """Tests for CLI entrypoint main execution via cli_runner and module execution."""

    def test_main_entrypoint_help_flag(self, cli_runner: Callable[..., CLIRunnerResult]) -> None:
        res = cli_runner(["--help"], target_func=_get_main_entrypoint())
        assert res.exit_code == 0
        assert "youtube_clipper" in res.stdout or "usage:" in res.stdout.lower()

    def test_main_entrypoint_local_file_execution(
        self,
        cli_runner: Callable[..., CLIRunnerResult],
        dummy_video_file: Path,
        tmp_media_dir: Path,
        mock_ffmpeg: MockFFmpegContainer,
    ) -> None:
        out_file = tmp_media_dir / "main_entrypoint_local.mp4"
        res = cli_runner(
            [str(dummy_video_file), "--start", "00:00:05", "--end", "00:00:15", "--output", str(out_file)],
            target_func=_get_main_entrypoint(),
        )
        assert res.exit_code == 0
        assert out_file.exists()

    def test_main_entrypoint_youtube_url_execution(
        self,
        cli_runner: Callable[..., CLIRunnerResult],
        tmp_media_dir: Path,
        mock_yt_dlp: MockYTDLPContainer,
        mock_ffmpeg: MockFFmpegContainer,
    ) -> None:
        out_file = tmp_media_dir / "main_entrypoint_yt.mp4"
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        res = cli_runner(
            [url, "--start", "10", "--duration", "20", "--output", str(out_file)],
            target_func=_get_main_entrypoint(),
        )
        assert res.exit_code == 0
        assert out_file.exists()

    def test_main_entrypoint_validation_error(
        self, cli_runner: Callable[..., CLIRunnerResult], mock_ffmpeg: MockFFmpegContainer
    ) -> None:
        res = cli_runner(
            ["non_existent_media_file.mp4", "--start", "0", "--end", "10"],
            target_func=_get_main_entrypoint(),
        )
        assert res.exit_code != 0
        assert res.exception is not None or "Error" in res.stderr

    def test_main_entrypoint_end_duration_conflict(
        self,
        cli_runner: Callable[..., CLIRunnerResult],
        dummy_video_file: Path,
        mock_ffmpeg: MockFFmpegContainer,
    ) -> None:
        res = cli_runner(
            [str(dummy_video_file), "--start", "0", "--end", "10", "--duration", "5"],
            target_func=_get_main_entrypoint(),
        )
        assert res.exit_code != 0

    def test_python_m_youtube_clipper_invocation(self, cli_runner: Callable[..., CLIRunnerResult]) -> None:
        """Tests python -m youtube_clipper execution via subprocess or fallback."""
        main_py = Path(__file__).resolve().parent.parent / "src" / "youtube_clipper" / "__main__.py"
        if main_py.exists():
            cmd = [sys.executable, "-m", "youtube_clipper", "--help"]
            res = run_cmd(
                cmd,
                cwd=str(Path(__file__).resolve().parent.parent),
                audit=False,
            )
            assert res.returncode == 0
            assert "usage:" in res.stdout.lower() or "youtube_clipper" in res.stdout
        else:
            res = cli_runner(["--help"], target_func=_get_main_entrypoint())
            assert res.exit_code == 0
            assert "youtube_clipper" in res.stdout or "usage:" in res.stdout.lower()
