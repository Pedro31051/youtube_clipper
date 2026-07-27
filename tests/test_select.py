"""Unit and integration tests for Stage 4 (select)."""

import json
import pathlib
import pytest

from cortes.log import set_run_id, get_run_dir
from cortes.select import run_select, select_clip_stage
from youtube_clipper.analyzer import SpeechDensityAnalyzer
from youtube_clipper.exceptions import ProcessingError


@pytest.fixture
def mock_transcript():
    """Return synthetic transcript data with word-level timestamps."""
    return {
        "schema_version": "1.0.0",
        "language": "pt",
        "duration": 60.0,
        "text": "Olá mundo este é um teste de seleção por densidade de fala.",
        "words": [
            {"word": "Olá", "start": 1.0, "end": 1.5, "start_ms": 1000, "end_ms": 1500},
            {"word": "mundo", "start": 1.6, "end": 2.2, "start_ms": 1600, "end_ms": 2200},
            {"word": "este", "start": 5.0, "end": 5.4, "start_ms": 5000, "end_ms": 5400},
            {"word": "é", "start": 5.5, "end": 5.7, "start_ms": 5500, "end_ms": 5700},
            {"word": "um", "start": 5.8, "end": 6.0, "start_ms": 5800, "end_ms": 6000},
            {"word": "teste", "start": 6.1, "end": 6.8, "start_ms": 6100, "end_ms": 6800},
            {"word": "de", "start": 6.9, "end": 7.1, "start_ms": 6900, "end_ms": 7100},
            {"word": "seleção", "start": 7.2, "end": 8.0, "start_ms": 7200, "end_ms": 8000},
            {"word": "por", "start": 8.1, "end": 8.3, "start_ms": 8100, "end_ms": 8300},
            {"word": "densidade", "start": 8.4, "end": 9.2, "start_ms": 8400, "end_ms": 9200},
            {"word": "de", "start": 9.3, "end": 9.5, "start_ms": 9300, "end_ms": 9500},
            {"word": "fala.", "start": 9.6, "end": 10.2, "start_ms": 9600, "end_ms": 10200},
            {"word": "Mais", "start": 25.0, "end": 25.4, "start_ms": 25000, "end_ms": 25400},
            {"word": "palavras", "start": 25.5, "end": 26.2, "start_ms": 25500, "end_ms": 26200},
            {"word": "aqui", "start": 26.3, "end": 26.8, "start_ms": 26300, "end_ms": 26800},
            {"word": "para", "start": 26.9, "end": 27.2, "start_ms": 26900, "end_ms": 27200},
            {"word": "completar", "start": 27.3, "end": 28.1, "start_ms": 27300, "end_ms": 28100},
            {"word": "a", "start": 28.2, "end": 28.4, "start_ms": 28200, "end_ms": 28400},
            {"word": "janela", "start": 28.5, "end": 29.2, "start_ms": 28500, "end_ms": 29200},
        ],
    }


@pytest.fixture
def mock_scenes():
    """Return synthetic scene detection data."""
    return {
        "schema_version": "1.0.0",
        "video_duration_sec": 60.0,
        "total_scenes": 3,
        "cut_timestamps_sec": [0.0, 5.0, 30.0, 60.0],
        "cut_timestamps_ms": [0, 5000, 30000, 60000],
        "scenes": [
            {"scene_id": 1, "start_ms": 0, "end_ms": 5000},
            {"scene_id": 2, "start_ms": 5000, "end_ms": 30000},
            {"scene_id": 3, "start_ms": 30000, "end_ms": 60000},
        ],
    }


def test_speech_density_analyzer(mock_transcript, mock_scenes):
    """Test SpeechDensityAnalyzer selects clip within 20s-58s duration bounds."""
    selection = SpeechDensityAnalyzer.select_best_clip(
        transcript_data=mock_transcript,
        scenes_data=mock_scenes,
        min_duration_ms=20000,
        max_duration_ms=58000,
    )

    assert "start_ms" in selection
    assert "end_ms" in selection
    assert "duration_ms" in selection
    assert "start_formatted" in selection
    assert "end_formatted" in selection
    assert "score" in selection

    assert 20000 <= selection["duration_ms"] <= 58000
    assert selection["end_ms"] > selection["start_ms"]
    assert selection["score"] >= 0.0


def test_select_clip_stage_audited(mock_transcript, mock_scenes, tmp_path, monkeypatch):
    """Test select_clip_stage audited entrypoint creates selection.json inside runs/<run_id>/."""
    run_id = f"test_run_select_{tmp_path.name}"
    set_run_id(run_id)
    monkeypatch.chdir(tmp_path)

    run_dir = get_run_dir(run_id)
    t_file = run_dir / "artifacts" / "transcribe" / "transcript.json"
    s_file = run_dir / "artifacts" / "scenes" / "scenes.json"
    t_file.parent.mkdir(parents=True, exist_ok=True)
    s_file.parent.mkdir(parents=True, exist_ok=True)

    t_file.write_text(json.dumps(mock_transcript), encoding="utf-8")
    s_file.write_text(json.dumps(mock_scenes), encoding="utf-8")

    res = select_clip_stage(
        transcript_path=t_file,
        scenes_path=s_file,
        run_id=run_id,
    )

    out_file = pathlib.Path(res["selection_path"])
    assert res["status"] == "ok"
    assert out_file.exists()
    assert len(res["evidence_paths"]) == 1

    # Verify evidence path is relative to runs/<run_id>/
    assert out_file.resolve().is_relative_to(run_dir.resolve())

    selection_content = json.loads(out_file.read_text(encoding="utf-8"))
    assert selection_content.get("schema_version") == "1.0.0"
    assert 20000 <= selection_content["duration_ms"] <= 58000

    # Verify audit log event
    events_file = run_dir / "events.jsonl"
    assert events_file.exists()
    lines = events_file.read_text().splitlines()
    assert len(lines) >= 1
    event_data = json.loads(lines[-1])
    assert event_data["stage"] == "select"
    assert event_data["evidence"]["paths"] == ["artifacts/select/selection.json"]


def test_select_invalid_paths_raises_processing_error():
    """Test non-existent input files raise ProcessingError."""
    with pytest.raises(ProcessingError):
        select_clip_stage(
            transcript_path="missing_t.json",
            scenes_path="missing_s.json",
        )


def test_speech_density_analyzer_short_video_raises_processing_error():
    """Test video shorter than 20s raises ProcessingError."""
    short_transcript = {
        "words": [
            {"word": "Short", "start_ms": 0, "end_ms": 5000}
        ]
    }
    short_scenes = {"cut_timestamps_ms": [0, 5000, 10000]}
    with pytest.raises(ProcessingError, match="Cannot select clip: duration must be between 20.0s and 58.0s"):
        SpeechDensityAnalyzer.select_best_clip(short_transcript, short_scenes)


def test_speech_density_analyzer_empty_inputs_raises_processing_error():
    """Test empty transcript and zero scene cuts raises ProcessingError."""
    with pytest.raises(ProcessingError, match="Cannot select clip: duration must be between 20.0s and 58.0s"):
        SpeechDensityAnalyzer.select_best_clip({}, {})


def test_speech_density_analyzer_parameter_clamping(mock_transcript, mock_scenes):
    """Test min_duration_ms and max_duration_ms overrides are clamped to [20s, 58s]."""
    # Passing 10s min duration should clamp to 20s minimum
    selection = SpeechDensityAnalyzer.select_best_clip(
        transcript_data=mock_transcript,
        scenes_data=mock_scenes,
        min_duration_ms=10000,
        max_duration_ms=15000,
    )
    assert selection["schema_version"] == "1.0.0"
    assert 20000 <= selection["duration_ms"] <= 58000
