"""Unit and integration tests for Stage 1 (ingest)."""

import json
import pathlib
import pytest

from cortes.ingest import probe_video_metadata, run_ingest
from cortes.log import set_run_id, get_run_dir
from youtube_clipper.exceptions import ValidationError, ProcessingError


@pytest.fixture
def sample_video(tmp_path):
    """Return path to existing sample video in repository or generate synthetic video."""
    repo_sample = pathlib.Path("sample_local.mp4")
    if repo_sample.exists():
        return repo_sample.resolve()
    
    # Fallback to generating a synthetic 3-second test video if not present
    from cortes.log import run_cmd
    syn_path = tmp_path / "synthetic_sample.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=3:size=640x360:rate=30",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=3",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        str(syn_path),
    ]
    res = run_cmd(cmd, stage="ingest", audit=False)
    assert res.returncode == 0
    return syn_path


def test_probe_video_metadata(sample_video):
    """Test metadata probe extracts valid width, height, duration, and sha256."""
    meta = probe_video_metadata(sample_video)
    assert meta["schema_version"] == "1.0.0"
    assert meta["duration"] > 0.0
    assert meta["width"] > 0
    assert meta["height"] > 0
    assert meta["fps"] > 0.0
    assert meta["sha256"].startswith("sha256:")
    assert meta["file_size"] > 1024


def test_run_ingest_local_video(sample_video, tmp_path, monkeypatch):
    """Test run_ingest copies video, writes metadata.json, and returns evidence paths."""
    run_id = f"test_run_ingest_{tmp_path.name}"
    set_run_id(run_id)
    monkeypatch.chdir(tmp_path)

    res = run_ingest(sample_video, run_id=run_id)

    assert res["status"] == "ok"
    assert "video_path" in res
    assert "metadata_path" in res

    v_path = pathlib.Path(res["video_path"])
    m_path = pathlib.Path(res["metadata_path"])

    assert v_path.exists()
    assert m_path.exists()
    assert len(res["evidence_paths"]) == 2

    metadata_content = json.loads(m_path.read_text(encoding="utf-8"))
    assert metadata_content["schema_version"] == "1.0.0"
    assert metadata_content["duration"] > 0.0
    assert metadata_content["sha256"] == res["metadata"]["sha256"]

    # Verify events.jsonl recorded ingest event
    events_file = get_run_dir(run_id) / "events.jsonl"
    assert events_file.exists()
    lines = events_file.read_text().splitlines()
    assert len(lines) >= 1
    event_data = json.loads(lines[-1])
    assert event_data["stage"] == "ingest"
    assert len(event_data["evidence"]["paths"]) == 2


def test_run_ingest_invalid_source_raises_validation_error():
    """Test invalid or non-existent source raises ValidationError."""
    with pytest.raises(ValidationError):
        run_ingest("non_existent_file_12345.mp4")

    with pytest.raises(ValidationError):
        run_ingest("")
