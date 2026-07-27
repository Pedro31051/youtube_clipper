"""Unit tests for Stage 7 (audio) module cortes.audio."""

import json
import pathlib
import pytest
from cortes.audio import parse_loudnorm_pass1_stderr, process_audio_loudnorm, run_audio
from cortes.log import run_cmd, set_run_id
from youtube_clipper.exceptions import ProcessingError


@pytest.fixture
def synthetic_audio_video(tmp_path):
    """Generate a synthetic 6-second MP4 with audio stream and 640x480 resolution."""
    vid_path = tmp_path / "audio_input.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi", "-i", "testsrc=size=640x480:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-t", "6",
        "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        str(vid_path),
    ]
    res = run_cmd(cmd, stage="audio")
    assert res.returncode == 0
    assert vid_path.exists()
    return vid_path


def test_parse_loudnorm_pass1_stderr_success():
    """Test parsing JSON loudnorm stats block from FFmpeg stderr."""
    sample_stderr = """
[Parsed_loudnorm_0 @ 0x55d7f8e87400] 
{
	"input_i" : "-22.50",
	"input_tp" : "-3.10",
	"input_lra" : "6.80",
	"input_thresh" : "-33.10",
	"output_i" : "-14.10",
	"output_tp" : "-1.50",
	"output_lra" : "6.10",
	"output_thresh" : "-24.70",
	"target_offset" : "0.10"
}
[out#0/null @ 0x55d7f8e87000] video:0kB audio:516kB
"""
    parsed = parse_loudnorm_pass1_stderr(sample_stderr)
    assert parsed["input_i"] == "-22.50"
    assert parsed["input_lra"] == "6.80"
    assert parsed["target_offset"] == "0.10"


def test_parse_loudnorm_pass1_stderr_failure():
    """Test parse_loudnorm_pass1_stderr raises ProcessingError on invalid stderr."""
    with pytest.raises(ProcessingError, match="Failed to find loudnorm Pass 1 JSON"):
        parse_loudnorm_pass1_stderr("No json output here")


def test_process_audio_loudnorm_success(tmp_path, synthetic_audio_video):
    """Test 2-pass loudnorm audio processing on synthetic media."""
    run_id = f"test_audio_loudnorm_{tmp_path.name}"
    set_run_id(run_id)

    from cortes.log import get_run_dir
    run_dir = get_run_dir(run_id)
    out_media = run_dir / "audio_normalized.mp4"
    stats_json = run_dir / "audio_stats.json"

    res = process_audio_loudnorm(
        input_media=synthetic_audio_video,
        output_media=out_media,
        stats_json=stats_json,
        target_lufs=-14.0,
    )

    assert res["status"] == "ok"
    assert pathlib.Path(res["audio_path"]).exists()
    assert pathlib.Path(res["stats_path"]).exists()
    assert out_media.stat().st_size > 1024

    stats = json.loads(stats_json.read_text(encoding="utf-8"))
    assert stats["target_lufs"] == -14.0
    assert "pass1_measured" in stats


def test_process_audio_missing_input(tmp_path):
    """Test process_audio_loudnorm raises ProcessingError for non-existent input file."""
    missing = tmp_path / "missing.mp4"
    out_media = tmp_path / "out.mp4"
    stats_json = tmp_path / "stats.json"

    with pytest.raises(ProcessingError, match="does not exist"):
        process_audio_loudnorm(
            input_media=missing,
            output_media=out_media,
            stats_json=stats_json,
        )


def test_run_audio_callback_delegation():
    """Test run_audio delegates to action callback."""
    called = []

    def dummy_action(val):
        called.append(val)
        return "audio_result"

    res = run_audio(dummy_action, "test_val")
    assert res == "audio_result"
    assert called == ["test_val"]
