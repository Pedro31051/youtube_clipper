"""
tests/test_regression_media.py - Baseline anti-regression & media output verification test suite.

Covers:
1. test_synthetic_mp4_generation_and_properties:
   Generates a synthetic MP4 clip using FFmpeg lavfi filters, validates st_size > 1024,
   ffprobe duration (~5s), and resolution (640x360).
2. test_double_cut_scenario_raises_processing_error:
   Calls cut_media with out-of-bounds start/end timestamps (e.g. 60s to 70s on a 5s source),
   asserting ProcessingError is raised.
3. test_small_or_corrupt_file_raises_processing_error:
   Verifies cut_media validation rejects small (<=1024 bytes) or empty media files.
4. test_pipeline_youtube_offset_normalization:
   Verifies pipeline segment offset handling for YouTube URLs (normalized to cut_start=0,
   cut_end=duration) vs local media files (cut_start=start_sec, cut_end=end_sec).
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from youtube_clipper.exceptions import ProcessingError
from youtube_clipper.pipeline import run_pipeline
from youtube_clipper.processor import FFmpegProcessor


def _create_real_synthetic_video(output_path: Path, duration: int = 5, size: str = "640x360", rate: int = 30) -> Path:
    """Helper to generate a real synthetic MP4 video file via ffmpeg lavfi filters."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        pytest.skip("ffmpeg binary not available on system")

    cmd = [
        ffmpeg_bin,
        "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate={rate}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    assert res.returncode == 0, f"FFmpeg synthetic video creation failed: {res.stderr}"
    assert output_path.exists()
    return output_path


def test_synthetic_mp4_generation_and_properties(tmp_path: Path) -> None:
    """Validate synthetic MP4 generation, file size > 1024 bytes, ffprobe duration (~5s), and resolution (640x360)."""
    video_path = tmp_path / "synthetic_5s.mp4"
    _create_real_synthetic_video(video_path, duration=5, size="640x360", rate=30)

    # 1. File size check
    assert video_path.stat().st_size > 1024, f"File size {video_path.stat().st_size} is not > 1024 bytes"

    # 2. ffprobe duration check
    ffprobe_bin = shutil.which("ffprobe") or "ffprobe"
    dur_cmd = [
        ffprobe_bin, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)
    ]
    res_dur = subprocess.run(dur_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    assert res_dur.returncode == 0
    duration = float(res_dur.stdout.strip())
    assert abs(duration - 5.0) < 0.5, f"Expected duration ~5.0s, got {duration}s"

    # 3. ffprobe resolution check
    res_cmd = [
        ffprobe_bin, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0", str(video_path)
    ]
    res_res = subprocess.run(res_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    assert res_res.returncode == 0
    dimensions = res_res.stdout.strip()
    assert "640" in dimensions and "360" in dimensions, f"Expected 640x360 resolution, got {dimensions}"


def test_double_cut_scenario_raises_processing_error(tmp_path: Path) -> None:
    """Verify out-of-bounds secondary cutting (e.g. start=60, end=70 on a 5s file) raises ProcessingError."""
    source_video = tmp_path / "short_5s.mp4"
    _create_real_synthetic_video(source_video, duration=5)

    processor = FFmpegProcessor()
    output_clip = tmp_path / "double_cut_out.mp4"

    # Attempting to cut start=60.0, end=70.0 from a 5s source file
    with pytest.raises(ProcessingError) as exc_info:
        processor.cut_media(input_path=source_video, start=60.0, end=70.0, output_path=output_clip)

    assert exc_info.value.exit_code == 4
    assert (
        "invalid or corrupt" in exc_info.value.message.lower()
        or "completed with code 0 but output file" in exc_info.value.message.lower()
        or "empty or undersized" in exc_info.value.message.lower()
    )


def test_small_or_corrupt_file_raises_processing_error(tmp_path: Path) -> None:
    """Verify cut_media validation rejects small (<= 1024 bytes) or empty output files with ProcessingError."""
    processor = FFmpegProcessor()
    dummy_input = tmp_path / "dummy_in.mp4"
    _create_real_synthetic_video(dummy_input, duration=2)

    small_output = tmp_path / "small_out.mp4"

    # Mock subprocess.run to simulate FFmpeg creating a 262-byte corrupted file
    def mock_corrupt_ffmpeg(cmd: list[str] | str, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        cmd_list = cmd if isinstance(cmd, list) else [str(cmd)]
        if cmd_list and ("ffprobe" in cmd_list[0] or Path(cmd_list[0]).name == "ffprobe"):
            return subprocess.CompletedProcess(args=cmd_list, returncode=0, stdout="0.0\n", stderr="")
        if cmd_list and len(cmd_list) > 1 and not cmd_list[-1].startswith("-"):
            out_p = Path(cmd_list[-1])
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_bytes(b"\x00" * 262)
        return subprocess.CompletedProcess(args=cmd_list, returncode=0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=mock_corrupt_ffmpeg):
        with pytest.raises(ProcessingError) as exc_info:
            processor.cut_media(dummy_input, start=0.0, end=2.0, output_path=small_output)

        assert exc_info.value.exit_code == 4
        assert (
            "<= 1024 bytes" in exc_info.value.message
            or "duration <= 0" in exc_info.value.message
            or "empty or undersized" in exc_info.value.message.lower()
        )


def test_pipeline_youtube_offset_normalization(tmp_path: Path) -> None:
    """Verify run_pipeline normalizes offsets (cut_start=0.0, cut_end=end-start) for YouTube vs local files."""
    local_video = tmp_path / "local_source.mp4"
    _create_real_synthetic_video(local_video, duration=5)

    recorded_cuts: list[dict[str, Any]] = []

    # Intercept cut_media calls to inspect start/end timestamps passed by pipeline
    def mock_cut_media(input_path: Any, start: float, end: float, output_path: Any, **kwargs: Any) -> str:
        recorded_cuts.append({
            "input_path": str(input_path),
            "start": float(start),
            "end": float(end),
            "output_path": str(output_path),
        })
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048)
        return str(out_p)

    # 1. Local file test: start=1.0, end=4.0 -> cut_media should receive start=1.0, end=4.0
    with patch("youtube_clipper.processor.FFmpegProcessor.cut_media", side_effect=mock_cut_media):
        out_local = tmp_path / "out_local.mp4"
        run_pipeline(input_source=str(local_video), start=1.0, end=4.0, output=out_local)

    assert len(recorded_cuts) == 1
    assert recorded_cuts[0]["start"] == 1.0
    assert recorded_cuts[0]["end"] == 4.0

    recorded_cuts.clear()

    # 2. YouTube URL test: start=60.0, end=75.0 (duration=15.0) -> cut_media should receive cut_start=0.0, cut_end=15.0
    yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    temp_yt_file = tmp_path / "yt_downloaded_segment.mp4"
    temp_yt_file.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048)

    with patch("youtube_clipper.downloader.YouTubeDownloader.download_segment", return_value=str(temp_yt_file)), \
         patch("youtube_clipper.processor.FFmpegProcessor.cut_media", side_effect=mock_cut_media):
        out_yt = tmp_path / "out_yt.mp4"
        run_pipeline(input_source=yt_url, start=60.0, end=75.0, output=out_yt)

    assert len(recorded_cuts) == 1
    assert recorded_cuts[0]["start"] == 0.0
    assert recorded_cuts[0]["end"] == 15.0
