"""Unit and integration tests for Stage 2 (transcribe)."""

import json
import pathlib
import pytest

from cortes.log import set_run_id, get_run_dir, run_cmd
from cortes.transcribe import extract_audio_wav, run_transcribe, transcribe_with_faster_whisper
from youtube_clipper.exceptions import ProcessingError


@pytest.fixture
def sample_video(tmp_path):
    """Return path to sample video."""
    repo_sample = pathlib.Path("sample_local.mp4")
    if repo_sample.exists():
        return repo_sample.resolve()

    syn_path = tmp_path / "synthetic_transcribe.mp4"
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
    res = run_cmd(cmd, stage="transcribe", audit=False)
    assert res.returncode == 0
    return syn_path


def test_extract_audio_wav(sample_video, tmp_path):
    """Test extract_audio_wav produces a 16kHz mono WAV file."""
    output_wav = tmp_path / "test_audio.wav"
    res_wav = extract_audio_wav(sample_video, output_wav)

    assert res_wav.exists()
    assert res_wav.stat().st_size > 100

    # Probe audio format using ffprobe
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=sample_rate,channels,codec_name",
        "-of",
        "json",
        str(res_wav),
    ]
    probe = run_cmd(cmd, stage="transcribe", audit=False)
    assert probe.returncode == 0
    data = json.loads(probe.stdout)
    stream = data["streams"][0]
    assert int(stream["sample_rate"]) == 16000
    assert int(stream["channels"]) == 1
    assert stream["codec_name"] == "pcm_s16le"


def test_run_transcribe_integration(sample_video, tmp_path, monkeypatch):
    """Test run_transcribe executes audio extraction and transcription producing transcript.json."""
    run_id = f"test_run_tx_{tmp_path.name}"
    set_run_id(run_id)
    monkeypatch.chdir(tmp_path)

    res = run_transcribe(
        sample_video,
        run_id=run_id,
        model_size="tiny",
        device="cpu",
    )

    assert res["status"] == "ok"
    assert "audio_path" in res
    assert "transcript_path" in res

    audio_p = pathlib.Path(res["audio_path"])
    tx_p = pathlib.Path(res["transcript_path"])

    assert audio_p.exists()
    assert tx_p.exists()
    assert len(res["evidence_paths"]) == 2

    transcript_content = json.loads(tx_p.read_text(encoding="utf-8"))
    assert transcript_content["schema_version"] == "1.0.0"
    assert "segments" in transcript_content
    assert "words" in transcript_content
    assert transcript_content["duration"] > 0.0

    # Verify audit log event
    events_file = get_run_dir(run_id) / "events.jsonl"
    assert events_file.exists()
    lines = events_file.read_text().splitlines()
    assert len(lines) >= 1
    event_data = json.loads(lines[-1])
    assert event_data["stage"] == "transcribe"


def test_transcribe_invalid_video_raises_processing_error():
    """Test non-existent video path raises ProcessingError."""
    with pytest.raises(ProcessingError):
        run_transcribe("non_existent_video_path_99.mp4")
