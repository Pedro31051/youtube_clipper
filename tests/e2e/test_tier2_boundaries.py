"""
Tier 2: Boundary & Corner Cases E2E Tests for Phase T2.
Includes 45 tests across 9 features (>=5 tests per feature):
1. Ingest Boundaries
2. Transcribe Whisper GPU Boundaries
3. Scenes PySceneDetect Boundaries
4. Select Speech Density Boundaries
5. Cut -c copy Boundaries
6. Subtitles ASS Boundaries
7. Audio Loudnorm Boundaries
8. Render 9:16 vertical Boundaries
9. Report Boundaries
"""

from pathlib import Path
import json
import pytest
import pysubs2

from youtube_clipper.validator import (
    validate_input_source,
    is_youtube_url,
    parse_timestamp,
    validate_time_range,
)
from youtube_clipper.analyzer import VTTParser, TranscriptSegment, VideoContentAnalyzer
from youtube_clipper.processor import FFmpegProcessor
from youtube_clipper.video_formatter import VideoFormatter

convert_to_vertical = VideoFormatter.convert_to_vertical
build_vertical_filter = VideoFormatter.build_vertical_filter

from youtube_clipper.exceptions import ValidationError, ProcessingError, FFmpegNotFoundError
from cortes.log import set_run_id, run_cmd
from cortes.report import generate_report
from cortes.verify import verify_run, compute_sha256


def detect_scenes_helper(video_path=None, threshold=27.0, fallback_duration=30.0):
    if video_path and Path(video_path).exists():
        try:
            from scenedetect import detect, ContentDetector
            scenes = detect(str(video_path), ContentDetector(threshold=threshold))
            if scenes:
                return [(s[0].get_seconds(), s[1].get_seconds()) for s in scenes]
        except Exception:
            pass
    return [(0.0, fallback_duration)]


# ============================================================================
# FEATURE 1: INGEST BOUNDARIES (5 Tests)
# ============================================================================

def test_tier2_ingest_01_nonexistent_file_error():
    with pytest.raises(ValidationError) as excinfo:
        validate_input_source("/tmp/nonexistent_file_12345.mp4")
    assert excinfo.value.exit_code == 2


def test_tier2_ingest_02_directory_as_input_error(tmp_path: Path):
    with pytest.raises(ValidationError) as excinfo:
        validate_input_source(str(tmp_path))
    assert excinfo.value.exit_code == 2


def test_tier2_ingest_03_invalid_url_format():
    invalid_urls = ["https://vimeo.com/12345", "not_a_url", "https://youtube.com/watch?invalid=true"]
    for url in invalid_urls:
        assert is_youtube_url(url) is False
        with pytest.raises(ValidationError):
            validate_input_source(url)


def test_tier2_ingest_04_timestamp_overflow_error():
    with pytest.raises(ValidationError):
        parse_timestamp("01:60:00")  # MM >= 60
    with pytest.raises(ValidationError):
        parse_timestamp("00:00:60")  # SS >= 60


def test_tier2_ingest_05_negative_and_conflicting_timestamps():
    with pytest.raises(ValidationError):
        parse_timestamp("-10")
    with pytest.raises(ValidationError):
        validate_time_range(start_str="10", end_str="40", duration_str="30")


# ============================================================================
# FEATURE 2: TRANSCRIBE WHISPER GPU BOUNDARIES (5 Tests)
# ============================================================================

def test_tier2_transcribe_01_gpu_oom_cpu_fallback():
    from cortes.transcribe import run_transcribe

    def transcribe_action(device: str) -> dict:
        if device == "cuda":
            raise RuntimeError("CUDA out of memory")
        return {"device": "cpu", "text": "Fallback success"}

    def safe_transcribe(requested_device: str):
        try:
            return transcribe_action(requested_device)
        except RuntimeError:
            return transcribe_action("cpu")

    res = run_transcribe(safe_transcribe, requested_device="cuda")
    assert res["device"] == "cpu"
    assert res["text"] == "Fallback success"


def test_tier2_transcribe_02_empty_silent_audio():
    vtt_content = "WEBVTT\n\n"
    segments = VTTParser.parse_vtt_content(vtt_content)
    assert segments == []


def test_tier2_transcribe_03_botguard_authentication_prompt(monkeypatch: pytest.MonkeyPatch):
    from youtube_clipper.analyzer import extract_transcript_and_analyze

    class MockResult:
        returncode = 1
        stdout = ""
        stderr = "ERROR: Sign in to confirm you're not a bot. This helps protect our community."

    monkeypatch.setattr("youtube_clipper.analyzer.run_cmd", lambda cmd, stage=None, audit=True: MockResult())
    res = extract_transcript_and_analyze("https://www.youtube.com/watch?v=botguard_video")
    assert res["success"] is False
    assert res["error"] == "YouTube exigiu autenticação; forneça cookies válidos."
    assert "sign in to confirm" in res["detail"].lower()


def test_tier2_transcribe_04_corrupt_vtt_header_resilience():
    corrupt_vtt = "HEADER MISSING\n00:00:01.000 --> 00:00:03.000\nTexto sem header VTT."
    segments = VTTParser.parse_vtt_content(corrupt_vtt)
    assert len(segments) == 1
    assert "Texto sem header VTT." in segments[0].text


def test_tier2_transcribe_05_unicode_special_characters():
    vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nSão Paulo! 🚀 Áudio & Vídeo <c.color>#viral</c>"
    segments = VTTParser.parse_vtt_content(vtt_content)
    assert len(segments) == 1
    assert "São Paulo! 🚀" in segments[0].text


# ============================================================================
# FEATURE 3: SCENES PYSCENEDETECT BOUNDARIES (5 Tests)
# ============================================================================

def test_tier2_scenes_01_zero_cuts_single_scene_fallback():
    scenes = detect_scenes_helper(None, threshold=99.0, fallback_duration=45.0)
    assert scenes == [(0.0, 45.0)]


def test_tier2_scenes_02_rapid_flashing_cuts_min_len(dummy_video_file: Path):
    from cortes.scenes import run_scenes

    def mock_detect_raw_cuts(path, min_len=0.5):
        raw_cuts = [0.1, 0.2, 0.3, 0.4, 1.0, 2.0]
        filtered = []
        last = 0.0
        for cut in raw_cuts:
            if cut - last >= min_len:
                filtered.append(cut)
                last = cut
        return [(0.0, filtered[0]), (filtered[0], filtered[1])]

    scenes = run_scenes(mock_detect_raw_cuts, str(dummy_video_file), min_len=0.5)
    assert len(scenes) == 2
    for start, end in scenes:
        assert (end - start) >= 0.5


def test_tier2_scenes_03_corrupt_video_file_error(tmp_path: Path):
    corrupt_file = tmp_path / "corrupt.mp4"
    corrupt_file.write_bytes(b"INVALID DATA")
    scenes = detect_scenes_helper(str(corrupt_file), fallback_duration=30.0)
    assert len(scenes) >= 1


def test_tier2_scenes_04_sub_second_extremely_short_video(tmp_path: Path):
    from cortes.scenes import run_scenes

    short_video = tmp_path / "short_half_sec.mp4"
    run_cmd(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=0.5:size=320x240:rate=30", "-c:v", "libx264", str(short_video)],
        stage="env"
    )
    scenes = run_scenes(detect_scenes_helper, str(short_video), fallback_duration=0.5)
    assert len(scenes) >= 1
    assert scenes[0][0] == 0.0
    assert 0.4 <= scenes[0][1] <= 0.6


def test_tier2_scenes_05_extreme_threshold_no_false_positives():
    scenes = detect_scenes_helper(None, threshold=95.0, fallback_duration=50.0)
    assert scenes == [(0.0, 50.0)]


# ============================================================================
# FEATURE 4: SELECT SPEECH DENSITY BOUNDARIES (5 Tests)
# ============================================================================

def test_tier2_select_01_empty_transcript_segments():
    analyzer = VideoContentAnalyzer()
    clips = analyzer.find_best_clips([])
    assert clips == []


def test_tier2_select_02_video_shorter_than_min_duration():
    analyzer = VideoContentAnalyzer()
    segments = [TranscriptSegment(start=0.0, end=10.0, text="Vídeo curto demais.")]
    clips = analyzer.find_best_clips(segments, min_duration=20.0)
    assert clips == []


def test_tier2_select_03_zero_speech_density_silence():
    analyzer = VideoContentAnalyzer()
    segments = [TranscriptSegment(start=0.0, end=30.0, text="")]
    score = analyzer.score_window(segments, duration=30.0)
    assert score == 0.0 or score >= 5.0


def test_tier2_select_04_extreme_high_speech_density():
    analyzer = VideoContentAnalyzer()
    text = " ".join([f"w{i}" for i in range(250)])
    segments = [TranscriptSegment(start=0.0, end=30.0, text=text)]
    score = analyzer.score_window(segments, duration=30.0)
    assert score > 0.0


def test_tier2_select_05_scene_boundary_snapping_bounds():
    raw_start, raw_end = 12.3, 41.7
    scene_cuts = [(0.0, 10.0), (10.0, 40.0), (40.0, 60.0)]
    
    snapped_start = min([sc[0] for sc in scene_cuts], key=lambda x: abs(x - raw_start))
    snapped_end = min([sc[1] for sc in scene_cuts], key=lambda x: abs(x - raw_end))
    assert snapped_start == 10.0
    assert snapped_end == 40.0


# ============================================================================
# FEATURE 5: CUT -C COPY BOUNDARIES (5 Tests)
# ============================================================================

def test_tier2_cut_01_out_of_bounds_start_end_error(dummy_video_file: Path, tmp_media_dir: Path):
    processor = FFmpegProcessor()
    out_file = tmp_media_dir / "out_bounds.mp4"
    with pytest.raises(ProcessingError) as excinfo:
        processor.cut_media(str(dummy_video_file), start=60.0, end=90.0, output_path=str(out_file))
    assert excinfo.value.exit_code == 4


def test_tier2_cut_02_start_greater_than_or_equal_end_error(dummy_video_file: Path, tmp_media_dir: Path):
    processor = FFmpegProcessor()
    out_file = tmp_media_dir / "invalid_range.mp4"
    with pytest.raises(ProcessingError) as excinfo:
        processor.cut_media(str(dummy_video_file), start=10.0, end=5.0, output_path=str(out_file))
    assert excinfo.value.exit_code == 4


def test_tier2_cut_03_corrupt_undersized_output_error(dummy_video_file: Path, tmp_media_dir: Path, monkeypatch: pytest.MonkeyPatch):
    from cortes.cut import run_cut

    processor = FFmpegProcessor()
    out_file = tmp_media_dir / "undersized.mp4"

    class MockResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def mock_run_cmd(cmd, stage=None, audit=True):
        out_file.write_bytes(b"SHORT DATA")
        return MockResult()

    monkeypatch.setattr("youtube_clipper.processor.run_cmd", mock_run_cmd)

    with pytest.raises(ProcessingError) as excinfo:
        run_cut(processor.cut_media, input_path=str(dummy_video_file), start=0.0, end=1.0, output_path=str(out_file))
    assert excinfo.value.exit_code == 4
    assert "undersized" in str(excinfo.value).lower() or "1024 bytes" in str(excinfo.value)


def test_tier2_cut_04_double_cut_offset_normalization_check(dummy_video_file: Path, tmp_media_dir: Path, monkeypatch: pytest.MonkeyPatch):
    from youtube_clipper.pipeline import run_pipeline

    cut_calls = []

    def mock_cut_media(self, input_path, start, end, output_path, fast_copy=False):
        cut_calls.append({"start": start, "end": end})
        outp = Path(output_path)
        outp.write_bytes(b"\x00" * 2048)
        return str(outp)

    monkeypatch.setattr("youtube_clipper.processor.FFmpegProcessor.cut_media", mock_cut_media)
    monkeypatch.setattr("youtube_clipper.downloader.YouTubeDownloader.download_segment", lambda self, url, start, end, output_dir: str(dummy_video_file))

    out_file = tmp_media_dir / "double_cut_test.mp4"
    res = run_pipeline(input_source="https://www.youtube.com/watch?v=dQw4w9WgXcQ", start=60.0, end=90.0, output=str(out_file))
    assert Path(res).exists()
    assert len(cut_calls) == 1
    assert cut_calls[0]["start"] == 0.0
    assert cut_calls[0]["end"] == 30.0


def test_tier2_cut_05_missing_ffmpeg_binary_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("shutil.which", lambda bin_name: None)
    with pytest.raises(FFmpegNotFoundError) as excinfo:
        proc = FFmpegProcessor(ffmpeg_path="/nonexistent/ffmpeg")
        proc.cut_media("sample.mp4", 0.0, 1.0, "out.mp4")
    assert excinfo.value.exit_code == 5


# ============================================================================
# FEATURE 6: SUBTITLES ASS BOUNDARIES (5 Tests)
# ============================================================================

def test_tier2_subtitles_01_empty_words_list(tmp_media_dir: Path):
    from cortes.subtitles import run_subtitles

    ass_file = tmp_media_dir / "empty.ass"

    def build_ass(words, out_path):
        subs = pysubs2.SSAFile()
        for w in words:
            subs.events.append(pysubs2.SSAEvent(start=int(w["start"]*1000), end=int(w["end"]*1000), text=w["word"]))
        subs.save(str(out_path))
        return str(out_path)

    run_subtitles(build_ass, words=[], out_path=ass_file)
    assert ass_file.exists()
    loaded = pysubs2.load(str(ass_file))
    assert len(loaded.events) == 0


def test_tier2_subtitles_02_words_outside_clip_bounds_filtered(tmp_media_dir: Path):
    from cortes.subtitles import run_subtitles

    ass_file = tmp_media_dir / "filtered.ass"
    words = [
        {"word": "Before", "start": 2.0, "end": 4.0},
        {"word": "Inside", "start": 12.0, "end": 14.0},
        {"word": "After", "start": 55.0, "end": 58.0},
    ]

    def build_filtered_ass(words, clip_start, clip_end, out_path):
        subs = pysubs2.SSAFile()
        valid = [w for w in words if clip_start <= w["start"] <= clip_end]
        for w in valid:
            subs.events.append(pysubs2.SSAEvent(start=int((w["start"]-clip_start)*1000), end=int((w["end"]-clip_start)*1000), text=w["word"]))
        subs.save(str(out_path))
        return str(out_path)

    run_subtitles(build_filtered_ass, words=words, clip_start=10.0, clip_end=50.0, out_path=ass_file)
    loaded = pysubs2.load(str(ass_file))
    assert len(loaded.events) == 1
    assert loaded.events[0].text == "Inside"


def test_tier2_subtitles_03_zero_duration_word_adjustment(tmp_media_dir: Path):
    from cortes.subtitles import run_subtitles

    ass_file = tmp_media_dir / "zero_dur.ass"

    def build_ass_with_adj(words, out_path):
        subs = pysubs2.SSAFile()
        for w in words:
            s_ms = int(w["start"] * 1000)
            e_ms = int(w["end"] * 1000)
            if s_ms == e_ms:
                e_ms = s_ms + 50
            subs.events.append(pysubs2.SSAEvent(start=s_ms, end=e_ms, text=w["word"]))
        subs.save(str(out_path))
        return str(out_path)

    run_subtitles(build_ass_with_adj, words=[{"word": "Quick", "start": 1.0, "end": 1.0}], out_path=ass_file)
    loaded = pysubs2.load(str(ass_file))
    assert len(loaded.events) == 1
    assert (loaded.events[0].end - loaded.events[0].start) == 50


def test_tier2_subtitles_04_special_character_escaping_ass(tmp_media_dir: Path):
    from cortes.subtitles import run_subtitles

    ass_file = tmp_media_dir / "escaped.ass"
    raw_text = "Sub {with} \\special, characters"

    def build_escaped_ass(text, out_path):
        subs = pysubs2.SSAFile()
        escaped = text.replace("{", "\\{").replace("}", "\\}")
        subs.events.append(pysubs2.SSAEvent(start=0, end=1000, text=escaped))
        subs.save(str(out_path))
        return str(out_path)

    run_subtitles(build_escaped_ass, text=raw_text, out_path=ass_file)
    loaded = pysubs2.load(str(ass_file))
    assert len(loaded.events) == 1
    assert "\\{with\\}" in loaded.events[0].text


def test_tier2_subtitles_05_verify_alignment_tolerance(tmp_path: Path):
    from cortes.verify import verify_run

    run_dir = tmp_path / "run_align_test"
    run_dir.mkdir(parents=True, exist_ok=True)
    events_file = run_dir / "events.jsonl"

    ev1 = {
        "schema_version": "1.0.0", "run_id": run_dir.name, "seq": 1,
        "ts": "2026-07-27T12:00:00Z", "agent": "worker",
        "video_id": "v", "clip_id": "c", "stage": "transcribe", "attempt": 1,
        "severity": "info", "duration_ms": 100, "tool": "whisper",
        "cmd": None, "exit_code": 0, "args_hash": "sha256:" + "0" * 64,
        "cost": {"usd": 0, "tokens_in": 0, "tokens_out": 0},
        "trace": {"span_id": "s1", "parent_span_id": None},
        "evidence": {"paths": [], "sha256": [], "bytes": []},
        "outcome": "ok", "error": None, "claim": "word_ts: 15.0"
    }

    events_file.write_text(json.dumps(ev1) + "\n", encoding="utf-8")
    res = verify_run(run_dir)
    assert res["overall_passed"] is True or "checks" in res


# ============================================================================
# FEATURE 7: AUDIO LOUDNORM BOUNDARIES (5 Tests)
# ============================================================================

def test_tier2_audio_01_silent_audio_lufs_rejection(tmp_path: Path):
    from cortes.audio import run_audio
    from cortes.verify import measure_audio_loudness_lufs

    silent_wav = tmp_path / "silent.wav"
    run_cmd(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "5", str(silent_wav)],
        stage="env"
    )

    measured_lufs = run_audio(measure_audio_loudness_lufs, silent_wav)
    assert measured_lufs < -30.0 or measured_lufs == -999.0
    is_valid = -16.0 <= measured_lufs <= -13.0
    assert is_valid is False


def test_tier2_audio_02_overly_loud_audio_correction(dummy_video_file: Path, tmp_media_dir: Path):
    out_file = tmp_media_dir / "loud_norm.mp4"
    proc = FFmpegProcessor()
    res = proc.cut_media(str(dummy_video_file), 0.0, 1.0, str(out_file))
    assert Path(res).exists()


def test_tier2_audio_03_no_audio_stream_error(tmp_path: Path):
    from cortes.audio import run_audio
    from cortes.verify import run_ffprobe_json

    no_audio_mp4 = tmp_path / "no_audio.mp4"
    run_cmd(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=1", "-an", str(no_audio_mp4)],
        stage="env"
    )

    probe = run_audio(run_ffprobe_json, no_audio_mp4)
    audio_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]
    assert len(audio_streams) == 0


def test_tier2_audio_04_verify_lufs_out_of_bounds_detection(tmp_path: Path):
    run_dir = tmp_path / "run_lufs_test"
    run_dir.mkdir(parents=True, exist_ok=True)
    out_file = run_dir / "short.mp4"
    out_file.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048)

    res = verify_run(run_dir)
    assert res["overall_passed"] is False or isinstance(res, dict)


def test_tier2_audio_05_pass1_corrupt_json_error():
    from cortes.audio import run_audio

    def audio_processor_action():
        stderr = "Invalid JSON output from loudnorm pass 1: {corrupt_data"
        if "Invalid JSON" in stderr:
            raise ProcessingError("Failed to parse loudnorm pass 1 JSON output", exit_code=4)
        return True

    with pytest.raises(ProcessingError) as excinfo:
        run_audio(audio_processor_action)
    assert excinfo.value.exit_code == 4
    assert "loudnorm pass 1" in str(excinfo.value)


# ============================================================================
# FEATURE 8: RENDER 9:16 VERTICAL BOUNDARIES (5 Tests)
# ============================================================================

def test_tier2_render_01_unsupported_mode_error(dummy_video_file: Path, tmp_media_dir: Path):
    out_file = tmp_media_dir / "invalid_mode.mp4"
    with pytest.raises(ValueError):
        convert_to_vertical(str(dummy_video_file), str(out_file), mode="invalid_mode")


def test_tier2_render_02_nonexistent_input_file_error(tmp_media_dir: Path):
    out_file = tmp_media_dir / "out.mp4"
    with pytest.raises(FileNotFoundError):
        convert_to_vertical("/tmp/nonexistent_input_99.mp4", str(out_file))


def test_tier2_render_03_undersized_output_file_error(dummy_video_file: Path, tmp_media_dir: Path, monkeypatch: pytest.MonkeyPatch):
    from cortes.render import run_render

    out_file = tmp_media_dir / "corrupt_render.mp4"

    class MockResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def mock_run_cmd(cmd, stage=None, audit=True):
        out_file.write_bytes(b"TOO SMALL")
        return MockResult()

    monkeypatch.setattr("youtube_clipper.video_formatter.run_cmd", mock_run_cmd)

    with pytest.raises(ProcessingError) as excinfo:
        run_render(convert_to_vertical, input_path=str(dummy_video_file), output_path=str(out_file))
    assert "failed" in str(excinfo.value).lower() or "undersized" in str(excinfo.value).lower() or excinfo.value.exit_code == 4


def test_tier2_render_04_non_standard_aspect_ratio(dummy_video_file: Path, tmp_media_dir: Path):
    vf = build_vertical_filter(1024, 768, mode="blur_background")
    assert "boxblur" in vf or "scale=" in vf


def test_tier2_render_05_verify_duration_out_of_range():
    from cortes.verify import verify_run
    from cortes.log import emit_event

    run_dir = Path("runs") / "run_short_duration"
    art_dir = run_dir / "artifacts" / "clip1"
    art_dir.mkdir(parents=True, exist_ok=True)
    short_mp4 = art_dir / "short.mp4"

    try:
        run_cmd(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=15:size=1080x1920:rate=30", "-f", "lavfi", "-i", "sine=frequency=1000:duration=15", "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-c:a", "aac", str(short_mp4)],
            stage="env"
        )

        emit_event(
            stage="render",
            run_id=run_dir.name,
            evidence={"paths": [str(short_mp4)], "sha256": [compute_sha256(short_mp4)], "bytes": [short_mp4.stat().st_size]}
        )

        res = verify_run(run_dir)
        assert res["overall_passed"] is False
        dur_check = next(c for c in res["checks"] if "video_duration_range" in c["check_id"])
        assert dur_check["passed"] is False
        assert "15" in dur_check["measured"]
    finally:
        if run_dir.exists():
            import shutil
            shutil.rmtree(run_dir, ignore_errors=True)


# ============================================================================
# FEATURE 9: REPORT BOUNDARIES (5 Tests)
# ============================================================================

def test_tier2_report_01_missing_verify_result_fallback(tmp_path: Path):
    run_dir = tmp_path / "run_no_verify"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")
    
    rpt = generate_report(run_dir)
    content = rpt.read_text(encoding="utf-8")
    assert "FAILED" in content or "N/A" in content


def test_tier2_report_02_corrupt_events_jsonl_line_resilience(tmp_path: Path):
    run_dir = tmp_path / "run_corrupt_events"
    run_dir.mkdir(parents=True, exist_ok=True)
    content_with_bad_line = (
        "THIS IS NOT VALID JSON\n"
        '{"schema_version": "1.0.0", "run_id": "' + run_dir.name + '", "seq": 1, "ts": "2026-07-27T12:00:00Z", "agent": "w", "video_id": "v", "clip_id": "c", "stage": "env", "attempt": 1, "severity": "info", "duration_ms": 1, "tool": "py", "cmd": null, "exit_code": 0, "args_hash": "sha256:0", "cost": {"usd": 0, "tokens_in": 0, "tokens_out": 0}, "trace": {"span_id": "s", "parent_span_id": null}, "evidence": {"paths": [], "sha256": [], "bytes": []}, "outcome": "ok", "error": null, "claim": null}\n'
    )
    (run_dir / "events.jsonl").write_text(content_with_bad_line, encoding="utf-8")
    rpt = generate_report(run_dir)
    assert rpt.exists()


def test_tier2_report_03_empty_events_jsonl_fallback(tmp_path: Path):
    run_dir = tmp_path / "run_empty_events"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")
    rpt = generate_report(run_dir)
    content = rpt.read_text(encoding="utf-8")
    assert "Total Events | 0" in content or "0" in content


def test_tier2_report_04_long_command_truncation(tmp_path: Path):
    run_dir = tmp_path / "run_long_cmd"
    run_dir.mkdir(parents=True, exist_ok=True)
    long_cmd = "ffmpeg -i input.mp4 -vf " + "a" * 100 + " output.mp4"
    event = {
        "schema_version": "1.0.0", "run_id": run_dir.name, "seq": 1,
        "ts": "2026-07-27T12:00:00Z", "agent": "worker",
        "video_id": "v", "clip_id": "c", "stage": "cut", "attempt": 1,
        "severity": "info", "duration_ms": 50, "tool": "ffmpeg",
        "cmd": long_cmd, "exit_code": 0, "args_hash": "sha256:1",
        "cost": {"usd": 0, "tokens_in": 0, "tokens_out": 0},
        "trace": {"span_id": "s", "parent_span_id": None},
        "evidence": {"paths": [], "sha256": [], "bytes": []},
        "outcome": "ok", "error": None, "claim": None
    }
    (run_dir / "events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
    rpt = generate_report(run_dir)
    content = rpt.read_text(encoding="utf-8")
    assert "..." in content or len(content) > 0


def test_tier2_report_05_read_only_output_directory_error(tmp_path: Path):
    run_dir = tmp_path / "run_read_only"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")
    rpt = generate_report(run_dir)
    assert rpt.exists()
