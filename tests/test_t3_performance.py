"""
tests/test_t3_performance.py - Test suite for Phase 3 (T3) performance optimizations.

Validates:
1. Low-res gaussian blur filter construction and customizable sigma parameter.
2. Hardware NVENC encoder auto-detection via detect_h264_encoder.
3. Single-pass video cutting and vertical layout transformation.
4. Empirical rendering speed and valid MP4 output properties (resolution 1080x1920, st_size > 1024, duration ~5s).
"""

from __future__ import annotations

from pathlib import Path
import shutil
import time
from unittest.mock import patch

import pytest

from cortes.log import run_cmd
from youtube_clipper.pipeline import run_pipeline
from youtube_clipper.video_formatter import VideoFormatter, detect_h264_encoder


def _create_synthetic_1080p_video(output_path: Path, duration: int = 5) -> Path:
    """Helper to generate a real 1080p synthetic MP4 video file for performance testing."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        pytest.skip("ffmpeg binary not available on system")

    cmd = [
        ffmpeg_bin,
        "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=1920x1080:rate=30",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    res = run_cmd(cmd, audit=False)
    assert res.returncode == 0, f"FFmpeg synthetic video creation failed: {res.stderr}"
    assert output_path.exists()
    return output_path


def test_build_vertical_filter_low_res_blur_and_sigma() -> None:
    """Verify build_vertical_filter uses low-resolution scale and configurable gblur sigma."""
    filter_1080 = VideoFormatter.build_vertical_filter(1080, 1920, mode="blur_background", sigma=15.0)
    assert "scale=270:480" in filter_1080
    assert "gblur=sigma=15.0" in filter_1080
    assert "scale=1080:1920" in filter_1080

    filter_720 = VideoFormatter.build_vertical_filter(720, 1280, mode="split_blur", sigma=8.5)
    assert "scale=180:320" in filter_720
    assert "gblur=sigma=8.5" in filter_720
    assert "scale=720:1280" in filter_720


def test_detect_h264_encoder() -> None:
    """Verify detect_h264_encoder returns 'h264_nvenc' or 'libx264' on system."""
    encoder = detect_h264_encoder()
    assert encoder in ("h264_nvenc", "libx264")

    # Test fallback when ffmpeg binary does not support nvenc
    with patch("youtube_clipper.video_formatter.run_cmd") as mock_run_cmd:
        mock_run_cmd.return_value.returncode = 1
        detect_h264_encoder.cache_clear()
        fallback_encoder = detect_h264_encoder()
        assert fallback_encoder == "libx264"
        detect_h264_encoder.cache_clear()


def test_single_pass_convert_to_vertical(tmp_path: Path) -> None:
    """Verify single-pass convert_to_vertical applies start and end timestamps directly."""
    source_video = tmp_path / "source_10s.mp4"
    _create_synthetic_1080p_video(source_video, duration=10)

    out_clip = tmp_path / "single_pass_out.mp4"
    start_time = time.time()
    res_path = VideoFormatter.convert_to_vertical(
        input_path=str(source_video),
        output_path=str(out_clip),
        mode="blur_background",
        start=2.0,
        end=7.0,
    )
    elapsed = time.time() - start_time
    encoder = detect_h264_encoder()

    assert res_path == str(out_clip)
    assert out_clip.exists()
    assert out_clip.stat().st_size > 1024

    # Verify duration using ffprobe
    ffprobe_bin = shutil.which("ffprobe") or "ffprobe"
    dur_cmd = [
        ffprobe_bin, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(out_clip)
    ]
    res_dur = run_cmd(dur_cmd, audit=False)
    assert res_dur.returncode == 0
    duration = float(res_dur.stdout.strip())
    assert abs(duration - 5.0) < 0.5, f"Expected duration ~5.0s, got {duration}s"

    # Verify 1080x1920 resolution
    res_cmd = [
        ffprobe_bin, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0", str(out_clip)
    ]
    res_res = run_cmd(res_cmd, audit=False)
    assert res_res.returncode == 0
    assert "1080" in res_res.stdout and "1920" in res_res.stdout

    # The contractual <5s threshold is only meaningful on an operational NVENC
    # host. CPU fallback remains a portability path, not a performance proof.
    if encoder == "h264_nvenc":
        assert elapsed < 5.0, f"NVENC render time {elapsed:.2f}s exceeded 5s"


def test_pipeline_vertical_single_pass_integration(tmp_path: Path) -> None:
    """Verify run_pipeline executes vertical conversion in single pass for local source."""
    source_video = tmp_path / "source_8s.mp4"
    _create_synthetic_1080p_video(source_video, duration=8)

    output_path = tmp_path / "pipeline_vert_out.mp4"
    start_time = time.time()
    res_path = run_pipeline(
        input_source=str(source_video),
        start=1.0,
        end=6.0,
        output=output_path,
        vertical=True,
    )
    elapsed = time.time() - start_time
    encoder = detect_h264_encoder()

    assert res_path == str(output_path)
    assert output_path.exists()
    assert output_path.stat().st_size > 1024
    if encoder == "h264_nvenc":
        assert elapsed < 5.0, (
            f"NVENC pipeline render time {elapsed:.2f}s exceeded 5s"
        )
