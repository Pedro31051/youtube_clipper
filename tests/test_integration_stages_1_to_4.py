"""Integration test for sequential execution of Stages 1-4.

Verifies end-to-end flow:
Stage 1: Ingest (probe_video_metadata & run_ingest)
Stage 2: Transcribe (extract_audio_wav & transcribe_with_faster_whisper & run_transcribe)
Stage 3: Scenes (detect_scenes_stage & PySceneDetect)
Stage 4: Select (select_clip_stage & SpeechDensityAnalyzer)

Checks:
1. commands.log records sub-process executions via cortes.log.run_cmd().
2. events.jsonl follows schema 1.0.0 with monotonic sequence numbers.
3. Artifacts metadata.json, transcript.json, scenes.json, selection.json are generated and valid.
"""

import json
import pathlib
import pytest

from cortes.ingest import run_ingest
from cortes.log import (
    compute_sha256,
    get_run_dir,
    run_cmd,
    set_run_id,
    validate_event_dict,
)
from cortes.scenes import detect_scenes_stage
from cortes.select import select_clip_stage
from cortes.transcribe import run_transcribe


@pytest.fixture
def synthetic_sample_video(tmp_path):
    """Generate a synthetic 30-second MP4 test video with audio and scene cut."""
    video_path = tmp_path / "synthetic_e2e_sample.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=30:size=640x360:rate=30",
        "-f",
        "lavfi",
        "-i",
        (
            "flite=text=Reliable video processing requires accurate word "
            "timestamps for scene aligned selection and subtitle verification"
        ),
        "-af",
        "apad",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-pix_fmt",
        "yuv420p",
        "-t",
        "30",
        str(video_path),
    ]
    res = run_cmd(cmd, stage="env", audit=False)
    assert res.returncode == 0, f"FFmpeg synthetic video generation failed: {res.stderr}"
    assert video_path.exists() and video_path.stat().st_size > 1024
    return video_path


def test_integration_stages_1_to_4_e2e(synthetic_sample_video, tmp_path, monkeypatch):
    """Run Stages 1-4 sequentially and verify commands.log, events.jsonl, and artifacts."""
    run_id = f"run_integration_e2e_{tmp_path.name}"
    set_run_id(run_id)
    monkeypatch.chdir(tmp_path)

    # -------------------------------------------------------------------------
    # STAGE 1: INGEST
    # -------------------------------------------------------------------------
    ingest_res = run_ingest(synthetic_sample_video, run_id=run_id)
    assert ingest_res["status"] == "ok"
    ingested_video_path = pathlib.Path(ingest_res["video_path"])
    metadata_path = pathlib.Path(ingest_res["metadata_path"])

    assert ingested_video_path.exists()
    assert metadata_path.exists()

    # -------------------------------------------------------------------------
    # STAGE 2: TRANSCRIBE
    # -------------------------------------------------------------------------
    transcribe_res = run_transcribe(
        ingested_video_path,
        run_id=run_id,
        model_size="tiny",
        device="cpu",
    )
    assert transcribe_res["status"] == "ok"
    audio_path = pathlib.Path(transcribe_res["audio_path"])
    transcript_path = pathlib.Path(transcribe_res["transcript_path"])

    assert audio_path.exists()
    assert transcript_path.exists()

    # -------------------------------------------------------------------------
    # STAGE 3: SCENES
    # -------------------------------------------------------------------------
    scenes_res = detect_scenes_stage(
        video_path=ingested_video_path,
        run_id=run_id,
        threshold=27.0,
        min_scene_len=0.6,
    )
    assert scenes_res["status"] == "ok"
    scenes_path = pathlib.Path(scenes_res["scenes_path"])

    assert scenes_path.exists()

    # -------------------------------------------------------------------------
    # STAGE 4: SELECT
    # -------------------------------------------------------------------------
    select_res = select_clip_stage(
        transcript_path=transcript_path,
        scenes_path=scenes_path,
        run_id=run_id,
    )
    assert select_res["status"] == "ok"
    selection_path = pathlib.Path(select_res["selection_path"])

    assert selection_path.exists()

    # =========================================================================
    # VERIFICATION 1: Sub-process Executions in commands.log
    # =========================================================================
    run_dir = get_run_dir(run_id)
    commands_log = run_dir / "commands.log"
    assert commands_log.exists(), f"commands.log does not exist in {run_dir}"

    commands_text = commands_log.read_text(encoding="utf-8")
    assert len(commands_text.strip()) > 0, "commands.log is empty"

    # Verify key subprocess commands executed during stages 1-3 were logged
    assert "ffprobe" in commands_text, "ffprobe execution missing from commands.log"
    assert "ffmpeg" in commands_text, "ffmpeg execution missing from commands.log"
    assert "scenedetect" in commands_text, "scenedetect execution missing from commands.log"

    # =========================================================================
    # VERIFICATION 2: Stage Events in events.jsonl (Schema 1.0.0 & Monotonic Seq)
    # =========================================================================
    events_file = run_dir / "events.jsonl"
    assert events_file.exists(), f"events.jsonl does not exist in {run_dir}"

    event_lines = [line for line in events_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(event_lines) >= 4, f"Expected at least 4 events, got {len(event_lines)}"

    recorded_stages = []
    expected_seq = 1

    for idx, line in enumerate(event_lines, start=1):
        event_dict = json.loads(line)

        # Strict Schema 1.0.0 validation
        validate_event_dict(event_dict)

        # Monotonic sequence check
        seq = event_dict["seq"]
        assert seq == expected_seq, f"Sequence gap/duplicate at index {idx}: expected {expected_seq}, got {seq}"
        expected_seq += 1

        recorded_stages.append(event_dict["stage"])

        # Check evidence hash validity for ok outcome
        if event_dict["outcome"] == "ok" and event_dict["evidence"]["paths"]:
            for rel_p, declared_hash, declared_bytes in zip(
                event_dict["evidence"]["paths"],
                event_dict["evidence"]["sha256"],
                event_dict["evidence"]["bytes"],
            ):
                abs_p = run_dir / rel_p
                assert abs_p.exists(), f"Declared evidence path missing: {abs_p}"
                actual_hash = compute_sha256(abs_p)
                assert actual_hash == declared_hash, f"Evidence hash mismatch for {rel_p}: expected {declared_hash}, got {actual_hash}"
                assert abs_p.stat().st_size == declared_bytes, f"Evidence size mismatch for {rel_p}"

    # Verify stage progression
    assert "ingest" in recorded_stages
    assert "transcribe" in recorded_stages
    assert "scenes" in recorded_stages
    assert "select" in recorded_stages

    # =========================================================================
    # VERIFICATION 3: Artifacts Generation & Schema Validity
    # =========================================================================

    # 3.1 metadata.json
    metadata_data = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata_data["schema_version"] == "1.0.0"
    assert metadata_data["duration"] > 0.0
    assert metadata_data["width"] > 0
    assert metadata_data["height"] > 0
    assert metadata_data["fps"] > 0.0
    assert metadata_data["file_size"] > 1024
    assert metadata_data["sha256"].startswith("sha256:")
    assert "source_input" in metadata_data

    # 3.2 transcript.json
    transcript_data = json.loads(transcript_path.read_text(encoding="utf-8"))
    assert transcript_data["schema_version"] == "1.0.0"
    assert "language" in transcript_data
    assert "duration" in transcript_data
    assert "text" in transcript_data
    assert "segments" in transcript_data
    assert "words" in transcript_data
    assert isinstance(transcript_data["segments"], list)
    assert isinstance(transcript_data["words"], list)

    # 3.3 scenes.json
    scenes_data = json.loads(scenes_path.read_text(encoding="utf-8"))
    assert scenes_data["schema_version"] == "1.0.0"
    assert scenes_data["total_scenes"] >= 1
    assert "cut_timestamps_ms" in scenes_data
    assert isinstance(scenes_data["cut_timestamps_ms"], list)
    assert 0 in scenes_data["cut_timestamps_ms"]

    # 3.4 selection.json
    selection_data = json.loads(selection_path.read_text(encoding="utf-8"))
    assert "start_ms" in selection_data
    assert "end_ms" in selection_data
    assert "duration_ms" in selection_data
    assert "start_formatted" in selection_data
    assert "end_formatted" in selection_data
    assert "score" in selection_data
    assert selection_data["start_ms"] >= 0
    assert selection_data["end_ms"] > selection_data["start_ms"]
    assert selection_data["duration_ms"] == selection_data["end_ms"] - selection_data["start_ms"]
