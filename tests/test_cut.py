"""Unit tests for Stage 5 (cut) module cortes.cut."""

import json
import pathlib
import pytest
from cortes.cut import cut_clip_stage, run_cut
from cortes.log import run_cmd, set_run_id
from cortes.log import run_cmd, set_run_id, get_run_dir
from youtube_clipper.exceptions import ProcessingError


@pytest.fixture
def synthetic_video(tmp_path):
    """Generate a valid 8-second synthetic MP4 video file with 640x480 resolution."""
    run_id = f"test_setup_{tmp_path.name}"
    set_run_id(run_id)
    vid_path = get_run_dir(run_id) / "test_input.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi", "-i", "testsrc=size=640x480:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-t", "8",
        "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        str(vid_path),
    ]
    res = run_cmd(cmd, stage="cut")
    assert res.returncode == 0
    assert vid_path.exists()
    return vid_path


def test_cut_clip_stage_success(tmp_path, synthetic_video):
    """Test successful cutting of media clip using start/end seconds."""
    run_id = f"test_cut_success_{tmp_path.name}"
    set_run_id(run_id)

    from cortes.log import get_run_dir
    out_clip = get_run_dir(run_id) / "cut_output.mp4"
    res = cut_clip_stage(
        input_video_path=synthetic_video,
        start_sec=1.0,
        end_sec=3.5,
        output_path=out_clip,
        fast_copy=False,
    )

    assert res["status"] == "ok"
    assert pathlib.Path(res["cut_path"]).exists()
    assert res["start_sec"] == 1.0
    assert res["end_sec"] == 3.5
    assert res["duration_sec"] == 2.5
    assert pathlib.Path(res["cut_path"]).stat().st_size > 1024


def test_cut_clip_stage_with_selection_data(tmp_path, synthetic_video):
    """Test cut stage resolving start/end from selection dictionary."""
    run_id = f"test_cut_sel_{tmp_path.name}"
    set_run_id(run_id)

    sel_data = {
        "start_ms": 1000,
        "end_ms": 4000,
    }
    res = cut_clip_stage(
        input_video_path=synthetic_video,
        selection_path_or_data=sel_data,
        run_id=run_id,
        fast_copy=False,
    )

    assert res["status"] == "ok"
    assert res["duration_sec"] == 3.0
    assert pathlib.Path(res["clip_path"]).exists()


def test_cut_clip_stage_invalid_timestamps(synthetic_video):
    """Test cut stage raises ProcessingError for invalid timestamp range."""
    with pytest.raises(ProcessingError, match="Invalid clip timestamp range"):
        cut_clip_stage(
            input_video_path=synthetic_video,
            start_sec=4.0,
            end_sec=2.0,
        )


def test_cut_clip_stage_missing_video(tmp_path):
    """Test cut stage raises ProcessingError for missing input video."""
    missing_vid = tmp_path / "non_existent.mp4"
    with pytest.raises(ProcessingError, match="does not exist"):
        cut_clip_stage(
            input_video_path=missing_vid,
            start_sec=0.0,
            end_sec=2.0,
        )


def test_run_cut_callback_delegation():
    """Test run_cut delegates to action callback when first arg is callable."""
    called = []

    def dummy_action(val):
        called.append(val)
        return "dummy_result"

    res = run_cut(dummy_action, "test_val")
    assert res == "dummy_result"
    assert called == ["test_val"]
