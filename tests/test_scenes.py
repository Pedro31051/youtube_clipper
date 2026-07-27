"""Unit and integration tests for Stage 3 (scenes)."""

import json
import pathlib
import pytest

from cortes.log import set_run_id, get_run_dir, run_cmd
from cortes.scenes import detect_scenes_stage, run_scenes
from youtube_clipper.exceptions import ProcessingError
from youtube_clipper.processor import detect_scenes_scenedetect


@pytest.fixture
def sample_video(tmp_path):
    """Return path to sample video."""
    repo_sample = pathlib.Path("sample_local.mp4")
    if repo_sample.exists():
        return repo_sample.resolve()

    syn_path = tmp_path / "synthetic_scenes.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=4:size=640x360:rate=30",
        "-c:v",
        "libx264",
        str(syn_path),
    ]
    res = run_cmd(cmd, stage="scenes", audit=False)
    assert res.returncode == 0
    return syn_path


def test_detect_scenes_scenedetect(sample_video, tmp_path):
    """Test PySceneDetect execution and scenes.json generation."""
    out_dir = tmp_path / "scenes_output"
    res = detect_scenes_scenedetect(
        video_path=sample_video,
        output_dir=out_dir,
        threshold=27.0,
        min_scene_len=0.6,
    )

    assert res["status"] == "ok"
    assert "scenes_path" in res
    assert pathlib.Path(res["scenes_path"]).exists()

    scenes_data = json.loads(pathlib.Path(res["scenes_path"]).read_text(encoding="utf-8"))
    assert scenes_data["schema_version"] == "1.0.0"
    assert "total_scenes" in scenes_data
    assert scenes_data["total_scenes"] >= 1
    assert "cut_timestamps_ms" in scenes_data
    assert 0 in scenes_data["cut_timestamps_ms"]


def test_detect_scenes_stage_audited(sample_video, tmp_path, monkeypatch):
    """Test detect_scenes_stage audited entrypoint."""
    run_id = f"test_run_scenes_{tmp_path.name}"
    set_run_id(run_id)
    monkeypatch.chdir(tmp_path)

    res = detect_scenes_stage(video_path=sample_video, run_id=run_id)

    assert res["status"] == "ok"
    assert "scenes_path" in res
    assert pathlib.Path(res["scenes_path"]).exists()

    # Verify audit event in events.jsonl
    events_file = get_run_dir(run_id) / "events.jsonl"
    assert events_file.exists()
    lines = events_file.read_text().splitlines()
    assert len(lines) >= 1
    event_data = json.loads(lines[-1])
    assert event_data["stage"] == "scenes"


def test_detect_scenes_invalid_video_raises_processing_error():
    """Test non-existent video path raises ProcessingError."""
    with pytest.raises(ProcessingError):
        detect_scenes_stage("non_existent_video_path_88.mp4")
