"""Unit tests for Stage 6 (subtitles) module cortes.subtitles."""

import json
import pathlib
import pysubs2
import pytest
from cortes.log import set_run_id
from cortes.subtitles import generate_subtitles_stage, run_subtitles
from youtube_clipper.exceptions import ProcessingError


@pytest.fixture
def mock_transcript_and_selection(tmp_path):
    """Create sample transcript and selection dictionary fixtures."""
    transcript_data = {
        "text": "Hello world welcome to youtube clipper test",
        "words": [
            {"word": "Hello", "start_ms": 1000, "end_ms": 1500},
            {"word": "world", "start_ms": 1500, "end_ms": 2000},
            {"word": "welcome", "start_ms": 2000, "end_ms": 2500},
            {"word": "to", "start_ms": 2500, "end_ms": 2800},
            {"word": "youtube", "start_ms": 2800, "end_ms": 3500},
            {"word": "clipper", "start_ms": 3500, "end_ms": 4000},
            {"word": "test", "start_ms": 4000, "end_ms": 4500},
        ],
    }
    selection_data = {
        "start_ms": 2000,
        "end_ms": 4000,
    }
    return transcript_data, selection_data


def test_generate_subtitles_stage_success(tmp_path, mock_transcript_and_selection):
    """Test subtitle generation creates ASS file with correct clip-relative timestamps."""
    run_id = f"test_subs_success_{tmp_path.name}"
    set_run_id(run_id)

    transcript, selection = mock_transcript_and_selection
    from cortes.log import get_run_dir
    out_ass = get_run_dir(run_id) / "subtitles.ass"

    res = generate_subtitles_stage(
        transcript_path_or_data=transcript,
        selection_path_or_data=selection,
        output_path=out_ass,
    )

    assert res["status"] == "ok"
    assert pathlib.Path(res["subtitles_path"]).exists()
    assert res["total_events"] == 4  # "welcome", "to", "youtube", "clipper"

    subs = pysubs2.load(str(out_ass), encoding="utf-8")
    assert subs.info["PlayResX"] == "1080"
    assert subs.info["PlayResY"] == "1920"
    assert "Default" in subs.styles

    style = subs.styles["Default"]
    assert style.fontsize == 80
    assert style.alignment == pysubs2.Alignment.BOTTOM_CENTER
    assert style.marginv == 400

    # Verify first word ("welcome"): original 2000ms -> clip-relative 0ms
    first_event = subs.events[0]
    assert first_event.text == "welcome"
    assert first_event.start == 0
    assert first_event.end == 500


def test_generate_subtitles_missing_artifact(tmp_path):
    """Test missing transcript artifact raises ProcessingError."""
    missing = tmp_path / "missing_transcript.json"
    selection = {"start_ms": 0, "end_ms": 1000}
    with pytest.raises(ProcessingError, match="missing for subtitles stage"):
        generate_subtitles_stage(
            transcript_path_or_data=missing,
            selection_path_or_data=selection,
        )


def test_run_subtitles_callback_delegation():
    """Test run_subtitles delegates to callback action."""
    called = []

    def dummy_action(val):
        called.append(val)
        return "subs_result"

    res = run_subtitles(dummy_action, "test_val")
    assert res == "subs_result"
    assert called == ["test_val"]
