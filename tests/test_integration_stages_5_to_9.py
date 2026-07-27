"""Integration tests for Stages 5 through 9 and full pipeline orchestration."""

import json
import pathlib
import pytest

from cortes.audio import run_audio
from cortes.cut import run_cut
from cortes.log import get_run_dir, run_cmd, set_run_id
from cortes.pipeline import run_full_pipeline
from cortes.render import run_render
from cortes.report import run_report
from cortes.subtitles import run_subtitles


@pytest.fixture
def integration_fixtures(tmp_path):
    """Create input video, transcript, and selection fixtures for integration test."""
    vid_path = tmp_path / "source_input.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-t", "25",
        "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        str(vid_path),
    ]
    res = run_cmd(cmd, stage="env")
    assert res.returncode == 0
    assert vid_path.exists()

    transcript_data = {
        "text": "Hello world welcome to integration testing stage five to nine running end to end test",
        "words": [
            {"word": "Hello", "start_ms": 500, "end_ms": 1000},
            {"word": "world", "start_ms": 1000, "end_ms": 1500},
            {"word": "welcome", "start_ms": 1500, "end_ms": 2000},
            {"word": "to", "start_ms": 2000, "end_ms": 2300},
            {"word": "integration", "start_ms": 2300, "end_ms": 3000},
            {"word": "testing", "start_ms": 3000, "end_ms": 3500},
            {"word": "stage", "start_ms": 3500, "end_ms": 4000},
            {"word": "five", "start_ms": 4000, "end_ms": 4500},
            {"word": "to", "start_ms": 4500, "end_ms": 4800},
            {"word": "nine", "start_ms": 4800, "end_ms": 5300},
            {"word": "running", "start_ms": 5300, "end_ms": 6000},
            {"word": "end", "start_ms": 6000, "end_ms": 10000},
            {"word": "to", "start_ms": 10000, "end_ms": 15000},
            {"word": "end", "start_ms": 15000, "end_ms": 20000},
            {"word": "test", "start_ms": 20000, "end_ms": 24000},
        ],
    }

    selection_data = {
        "start_ms": 1000,
        "end_ms": 22000,
    }

    return vid_path, transcript_data, selection_data


def test_integration_stages_5_to_9_sequential(tmp_path, integration_fixtures):
    """Test sequential execution of Stages 5 through 9."""
    run_id = f"test_integration_5_9_{tmp_path.name}"
    set_run_id(run_id)

    vid_path, transcript_data, selection_data = integration_fixtures

    # Save selection fixture inside run_dir
    run_dir = get_run_dir(run_id)
    sel_dir = run_dir / "artifacts" / "select"
    sel_dir.mkdir(parents=True, exist_ok=True)
    sel_path = sel_dir / "selection.json"
    sel_path.write_text(json.dumps(selection_data, indent=2), encoding="utf-8")

    # Stage 5: Cut
    cut_res = run_cut(vid_path, selection_path_or_data=selection_data, run_id=run_id, fast_copy=False)
    assert cut_res["status"] == "ok"
    cut_path = cut_res["cut_path"]
    assert pathlib.Path(cut_path).exists()

    # Stage 6: Subtitles
    sub_res = run_subtitles(transcript_data, selection_path_or_data=selection_data, run_id=run_id)
    assert sub_res["status"] == "ok"
    sub_path = sub_res["subtitles_path"]
    assert pathlib.Path(sub_path).exists()

    # Stage 7: Audio
    audio_res = run_audio(cut_path, run_id=run_id)
    assert audio_res["status"] == "ok"
    audio_path = audio_res["audio_path"]
    assert pathlib.Path(audio_path).exists()

    # Stage 8: Render
    render_res = run_render(audio_path, subtitles_path=sub_path, run_id=run_id, mode="blur_background")
    assert render_res["status"] == "ok"
    render_path = render_res["render_path"]
    assert pathlib.Path(render_path).exists()

    # Stage 9: Report
    report_res = run_report(run_dir_or_action=run_dir, run_id=run_id)
    assert report_res["status"] == "ok"
    report_path = report_res["report_path"]
    assert pathlib.Path(report_path).exists()

    # Validate report.md content
    report_text = pathlib.Path(report_path).read_text(encoding="utf-8")
    assert f"Execution & Verification Report — Run `{run_id}`" in report_text
    assert "UNVERIFIED" in report_text or "PASSED" in report_text

    # Validate events.jsonl sequence continuity
    events_file = run_dir / "events.jsonl"
    assert events_file.exists()
    lines = [l for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) >= 5

    seqs = [json.loads(l)["seq"] for l in lines]
    assert seqs == list(range(1, len(seqs) + 1))


def test_run_full_pipeline_mock_backend(tmp_path, integration_fixtures, monkeypatch):
    """Test full pipeline orchestration (run_full_pipeline) end to end."""
    run_id = f"test_full_pipeline_{tmp_path.name}"
    vid_path, transcript_data, selection_data = integration_fixtures

    run_dir = get_run_dir(run_id)
    mock_t = run_dir / "artifacts" / "transcribe" / "transcript.json"
    mock_t.parent.mkdir(parents=True, exist_ok=True)
    mock_t.write_text(json.dumps(transcript_data), encoding="utf-8")

    mock_s = run_dir / "artifacts" / "scenes" / "scenes.json"
    mock_s.parent.mkdir(parents=True, exist_ok=True)
    mock_s.write_text(json.dumps([{"start": 0.0, "end": 25.0}]), encoding="utf-8")

    mock_sel = run_dir / "artifacts" / "select" / "selection.json"
    mock_sel.parent.mkdir(parents=True, exist_ok=True)
    mock_sel.write_text(json.dumps(selection_data), encoding="utf-8")

    # Patch functions imported into cortes.pipeline
    monkeypatch.setattr(
        "cortes.pipeline.run_transcribe",
        lambda video_path, run_id=None, **kw: {
            "status": "ok",
            "transcript_path": str(mock_t),
            "evidence_paths": [str(mock_t)],
        },
    )

    monkeypatch.setattr(
        "cortes.pipeline.detect_scenes_stage",
        lambda video_path, run_id=None: {
            "status": "ok",
            "scenes_path": str(mock_s),
            "evidence_paths": [str(mock_s)],
        },
    )

    monkeypatch.setattr(
        "cortes.pipeline.select_clip_stage",
        lambda transcript_path, scenes_path, run_id=None: {
            "status": "ok",
            "selection_path": str(mock_sel),
            "evidence_paths": [str(mock_sel)],
        },
    )

    res = run_full_pipeline(
        input_source=vid_path,
        run_id=run_id,
        vertical_mode="blur_background",
    )

    assert res["status"] == "ok"
    assert pathlib.Path(res["cut_path"]).exists()
    assert pathlib.Path(res["subtitles_path"]).exists()
    assert pathlib.Path(res["audio_path"]).exists()
    assert pathlib.Path(res["render_path"]).exists()
    assert pathlib.Path(res["report_path"]).exists()
