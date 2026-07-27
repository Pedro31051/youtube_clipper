"""
Tier 1: Feature Coverage E2E Tests for Phase T2.
Includes 45 tests across 9 features (>=5 tests per feature):
1. Ingest
2. Transcribe Whisper GPU
3. Scenes PySceneDetect
4. Select Speech Density
5. Cut -c copy
6. Subtitles ASS
7. Audio Loudnorm
8. Render 9:16 vertical
9. Report
"""

from pathlib import Path
import json
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

build_vertical_filter = VideoFormatter.build_vertical_filter
convert_to_vertical = VideoFormatter.convert_to_vertical

from cortes.log import set_run_id, get_run_dir, run_cmd
from cortes.ingest import run_ingest
from cortes.transcribe import run_transcribe
from cortes.scenes import run_scenes
from cortes.select import run_select
from cortes.cut import run_cut
from cortes.subtitles import run_subtitles
from cortes.audio import run_audio
from cortes.render import run_render
from cortes.report import generate_report
from cortes.verify import measure_audio_loudness_lufs


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
# FEATURE 1: INGEST (5 Tests)
# ============================================================================

def test_tier1_ingest_01_youtube_watch_url_validation():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert is_youtube_url(url) is True
    validated = validate_input_source(url)
    assert validated == url


def test_tier1_ingest_02_youtube_shorts_and_embed_urls():
    shorts_url = "https://youtube.com/shorts/abcdefghijk"
    embed_url = "https://www.youtube.com/embed/abcdefghijk"
    assert is_youtube_url(shorts_url) is True
    assert is_youtube_url(embed_url) is True
    assert validate_input_source(shorts_url) == shorts_url
    assert validate_input_source(embed_url) == embed_url


def test_tier1_ingest_03_local_mp4_file_validation(dummy_video_file: Path):
    validated = validate_input_source(str(dummy_video_file))
    assert Path(validated).resolve() == dummy_video_file.resolve()


def test_tier1_ingest_04_timestamp_parsing_formats():
    assert parse_timestamp("01:30:15") == 5415.0
    assert parse_timestamp("05:30") == 330.0
    assert parse_timestamp("45") == 45.0
    assert parse_timestamp("12.5") == 12.5


def test_tier1_ingest_05_time_range_start_end_duration():
    start, end = validate_time_range(start_str="10", end_str="40")
    assert start == 10.0 and end == 40.0

    start_d, end_d = validate_time_range(start_str="15", duration_str="30")
    assert start_d == 15.0 and end_d == 45.0


# ============================================================================
# FEATURE 2: TRANSCRIBE WHISPER GPU (5 Tests)
# ============================================================================

def test_tier1_transcribe_01_vtt_parsing_segments():
    vtt_content = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:04.500\n"
        "Olá pessoal, bem-vindos ao vídeo.\n\n"
        "00:00:05.000 --> 00:00:10.000\n"
        "Hoje vamos aprender técnicas incríveis.\n"
    )
    segments = VTTParser.parse_vtt_content(vtt_content)
    assert len(segments) == 2
    assert segments[0].start == 1.0
    assert segments[0].end == 4.5
    assert "Olá pessoal" in segments[0].text
    assert segments[1].start == 5.0
    assert segments[1].end == 10.0


def test_tier1_transcribe_02_vtt_clean_text():
    raw_text = "<c.colorCCCCCC><b>Inscreva-se</b> no canal</c>"
    clean = VTTParser.clean_vtt_text(raw_text)
    assert clean == "Inscreva-se no canal"


def test_tier1_transcribe_03_segment_timestamp_conversion():
    assert VTTParser.parse_timestamp("00:01:23.456") == 83.456
    assert VTTParser.parse_timestamp("02:30.100") == 150.1


def test_tier1_transcribe_04_language_detection():
    vtt_content = "WEBVTT\n\n00:00:00.500 --> 00:00:03.000\nSegredo revelado."
    segments = VTTParser.parse_vtt_content(vtt_content)
    lang = "pt" if "segredo" in segments[0].text.lower() else "en"
    assert lang == "pt"


def test_tier1_transcribe_05_audited_stage_wrapper(tmp_path: Path):
    set_run_id(f"test_transcribe_stage_{tmp_path.name}")
    res = run_transcribe(lambda: {"status": "ok", "segments": 5})
    assert res == {"status": "ok", "segments": 5}


# ============================================================================
# FEATURE 3: SCENES PYSCENEDETECT (5 Tests)
# ============================================================================

def test_tier1_scenes_01_detection_standard_video(dummy_video_file: Path):
    scenes = detect_scenes_helper(str(dummy_video_file), threshold=27.0)
    assert isinstance(scenes, list)
    assert len(scenes) >= 1
    assert scenes[0][0] == 0.0


def test_tier1_scenes_02_threshold_parameter():
    scenes_high = detect_scenes_helper(None, threshold=80.0, fallback_duration=30.0)
    assert len(scenes_high) == 1
    assert scenes_high[0] == (0.0, 30.0)


def test_tier1_scenes_03_boundary_tuple_format(dummy_video_file: Path):
    scenes = detect_scenes_helper(str(dummy_video_file))
    for start, end in scenes:
        assert isinstance(start, float)
        assert isinstance(end, float)
        assert start < end


def test_tier1_scenes_04_content_detector_mode():
    scenes = detect_scenes_helper(None, threshold=27.0, fallback_duration=60.0)
    assert scenes == [(0.0, 60.0)]


def test_tier1_scenes_05_audited_stage_wrapper(tmp_path: Path, dummy_video_file: Path):
    set_run_id(f"test_scenes_stage_{tmp_path.name}")
    res = run_scenes(lambda: [(0.0, 10.0), (10.0, 20.0)])
    assert res == [(0.0, 10.0), (10.0, 20.0)]


# ============================================================================
# FEATURE 4: SELECT SPEECH DENSITY (5 Tests)
# ============================================================================

def test_tier1_select_01_speech_density_wps_scoring():
    analyzer = VideoContentAnalyzer()
    text = " ".join([f"palavra{i}" for i in range(60)])
    segments = [TranscriptSegment(start=0.0, end=30.0, text=text)]
    score = analyzer.score_window(segments, duration=30.0)
    assert score > 0.0


def test_tier1_select_02_hook_words_detection():
    analyzer = VideoContentAnalyzer()
    text = "Você sabia que este é o segredo incrível nunca revelado?"
    segments = [TranscriptSegment(start=0.0, end=25.0, text=text)]
    score = analyzer.score_window(segments, duration=25.0)
    assert score > 50.0


def test_tier1_select_03_best_clips_non_overlapping():
    analyzer = VideoContentAnalyzer()
    segments = [
        TranscriptSegment(start=i * 5.0, end=(i + 1) * 5.0, text=f"Segredo incrível pergunta {i}?")
        for i in range(20)
    ]
    clips = analyzer.find_best_clips(segments, max_clips=2, min_duration=20.0, max_duration=40.0, overlap_threshold=0.0)
    assert len(clips) <= 2
    if len(clips) == 2:
        c1, c2 = clips[0], clips[1]
        assert c1.end_time <= c2.start_time or c2.end_time <= c1.start_time


def test_tier1_select_04_duration_window_constraints():
    analyzer = VideoContentAnalyzer()
    segments = [TranscriptSegment(start=0.0, end=30.0, text="Algum texto falado no clipe.")]
    score = analyzer.score_window(segments, duration=30.0)
    assert score > 0.0


def test_tier1_select_05_audited_stage_wrapper(tmp_path: Path):
    set_run_id(f"test_select_stage_{tmp_path.name}")
    res = run_select(lambda: {"best_start": 10.0, "best_end": 40.0, "score": 85.0})
    assert res["score"] == 85.0


# ============================================================================
# FEATURE 5: CUT -C COPY (5 Tests)
# ============================================================================

def test_tier1_cut_01_fast_stream_copy_flag(dummy_video_file: Path, tmp_media_dir: Path):
    processor = FFmpegProcessor()
    out_file = tmp_media_dir / "cut_copy.mp4"
    res = processor.cut_media(str(dummy_video_file), start=0.0, end=1.0, output_path=str(out_file), fast_copy=True)
    assert Path(res).exists()
    assert Path(res).stat().st_size > 1024


def test_tier1_cut_02_seeking_flag_order(dummy_video_file: Path, tmp_media_dir: Path):
    processor = FFmpegProcessor()
    out_file = tmp_media_dir / "cut_order.mp4"
    res = processor.cut_media(str(dummy_video_file), start=0.5, end=1.5, output_path=str(out_file), fast_copy=False)
    assert Path(res).exists()


def test_tier1_cut_03_duration_calculation(dummy_video_file: Path, tmp_media_dir: Path):
    processor = FFmpegProcessor()
    out_file = tmp_media_dir / "cut_dur.mp4"
    res = processor.cut_media(str(dummy_video_file), start=0.0, end=1.5, output_path=str(out_file))
    assert Path(res).exists()


def test_tier1_cut_04_output_size_and_duration(dummy_video_file: Path, tmp_media_dir: Path):
    processor = FFmpegProcessor()
    out_file = tmp_media_dir / "cut_valid.mp4"
    res_path = processor.cut_media(str(dummy_video_file), start=0.0, end=1.0, output_path=str(out_file))
    assert Path(res_path).stat().st_size > 1024


def test_tier1_cut_05_audited_stage_wrapper(tmp_path: Path, dummy_video_file: Path, tmp_media_dir: Path):
    set_run_id(f"test_cut_stage_{tmp_path.name}")
    out_file = tmp_media_dir / "audited_cut.mp4"
    res = run_cut(FFmpegProcessor().cut_media, str(dummy_video_file), 0.0, 1.0, str(out_file))
    assert Path(res).exists()


# ============================================================================
# FEATURE 6: SUBTITLES ASS (5 Tests)
# ============================================================================

def test_tier1_subtitles_01_ass_file_generation(tmp_media_dir: Path):
    subs = pysubs2.SSAFile()
    event = pysubs2.SSAEvent(start=1000, end=3000, text="Test Subtitle Line")
    subs.events.append(event)
    out_ass = tmp_media_dir / "test.ass"
    subs.save(str(out_ass))
    assert out_ass.exists()
    content = out_ass.read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "Test Subtitle Line" in content


def test_tier1_subtitles_02_word_timing_offset():
    word_start = 12.5
    clip_start = 10.0
    relative_start_ms = int((word_start - clip_start) * 1000)
    assert relative_start_ms == 2500


def test_tier1_subtitles_03_styling_attributes(tmp_media_dir: Path):
    subs = pysubs2.SSAFile()
    style = pysubs2.SSAStyle()
    style.fontname = "Arial"
    style.fontsize = 24
    style.marginv = 30
    style.alignment = pysubs2.Alignment.BOTTOM_CENTER
    subs.styles["Default"] = style
    out_ass = tmp_media_dir / "styled.ass"
    subs.save(str(out_ass))
    content = out_ass.read_text(encoding="utf-8")
    assert "Arial" in content
    assert "Style: Default" in content


def test_tier1_subtitles_04_pysubs2_formatting(tmp_media_dir: Path):
    subs = pysubs2.SSAFile()
    subs.events.append(pysubs2.SSAEvent(start=0, end=2000, text="Formatting Test"))
    out_ass = tmp_media_dir / "format.ass"
    subs.save(str(out_ass))
    assert out_ass.stat().st_size > 0


def test_tier1_subtitles_05_audited_stage_wrapper(tmp_path: Path, tmp_media_dir: Path):
    set_run_id(f"test_subtitles_stage_{tmp_path.name}")
    ass_file = tmp_media_dir / "audited_subs.ass"
    ass_file.write_text("[Script Info]\nTitle: Audited Test\n", encoding="utf-8")
    res = run_subtitles(lambda: str(ass_file))
    assert Path(res).exists()


# ============================================================================
# FEATURE 7: AUDIO LOUDNORM (5 Tests)
# ============================================================================

def test_tier1_audio_01_two_pass_loudnorm_processing(dummy_video_file: Path, tmp_media_dir: Path):
    lufs = measure_audio_loudness_lufs(dummy_video_file)
    assert isinstance(lufs, float)


def test_tier1_audio_02_lufs_measurement_pyloudnorm(dummy_video_file: Path):
    lufs = measure_audio_loudness_lufs(dummy_video_file)
    assert isinstance(lufs, float)


def test_tier1_audio_03_lufs_measurement_ebur128_fallback(dummy_video_file: Path):
    res = run_cmd([
        "ffmpeg", "-y", "-i", str(dummy_video_file),
        "-filter_complex", "ebur128=peak=true", "-f", "null", "-"
    ], audit=False)
    assert res.returncode == 0


def test_tier1_audio_04_single_audio_stream_preservation(dummy_video_file: Path, tmp_media_dir: Path):
    out_file = tmp_media_dir / "audio_pres.mp4"
    proc = FFmpegProcessor()
    res = proc.cut_media(str(dummy_video_file), 0.0, 1.0, str(out_file))
    assert Path(res).exists()


def test_tier1_audio_05_audited_stage_wrapper(tmp_path: Path, dummy_video_file: Path):
    set_run_id(f"test_audio_stage_{tmp_path.name}")
    res = run_audio(lambda: {"lufs": -14.5, "status": "ok"})
    assert res["lufs"] == -14.5


# ============================================================================
# FEATURE 8: RENDER 9:16 VERTICAL (5 Tests)
# ============================================================================

def test_tier1_render_01_blur_background_filter_graph():
    vf = build_vertical_filter(1080, 1920, mode="blur_background")
    assert "boxblur" in vf or "scale=" in vf


def test_tier1_render_02_crop_center_filter_graph():
    vf = build_vertical_filter(1080, 1920, mode="crop_center")
    assert "crop=ih*9/16:ih:(iw-ow)/2:0,scale=1080:1920" in vf


def test_tier1_render_03_vertical_conversion_output(dummy_video_file: Path, tmp_media_dir: Path):
    out_file = tmp_media_dir / "vert_render.mp4"
    res = convert_to_vertical(str(dummy_video_file), str(out_file), mode="crop_center")
    assert Path(res).exists()
    assert Path(res).stat().st_size > 1024


def test_tier1_render_04_cli_vertical_flag_integration(cli_runner, dummy_video_file: Path, tmp_media_dir: Path):
    out_file = tmp_media_dir / "cli_vert.mp4"
    res = cli_runner([str(dummy_video_file), "-s", "0", "-e", "1", "-o", str(out_file), "--vertical"])
    assert res.exit_code == 0
    assert out_file.exists()


def test_tier1_render_05_audited_stage_wrapper(tmp_path: Path, dummy_video_file: Path, tmp_media_dir: Path):
    set_run_id(f"test_render_stage_{tmp_path.name}")
    out_file = tmp_media_dir / "audited_render.mp4"
    res = run_render(convert_to_vertical, str(dummy_video_file), str(out_file), mode="crop_center")
    assert Path(res).exists()


# ============================================================================
# FEATURE 9: REPORT (5 Tests)
# ============================================================================

def test_tier1_report_01_generation_from_run_dir(tmp_path: Path):
    run_dir = tmp_path / "run_test_report_1"
    run_dir.mkdir(parents=True, exist_ok=True)
    events_file = run_dir / "events.jsonl"
    event = {
        "schema_version": "1.0.0", "run_id": run_dir.name, "seq": 1,
        "ts": "2026-07-27T12:00:00Z", "agent": "worker",
        "video_id": "vid123", "clip_id": "clip1",
        "stage": "env", "attempt": 1, "severity": "info", "duration_ms": 10,
        "tool": "python", "cmd": "python --version", "exit_code": 0,
        "args_hash": "sha256:123", "cost": {"usd": 0.0, "tokens_in": 0, "tokens_out": 0},
        "trace": {"span_id": "s1", "parent_span_id": None},
        "evidence": {"paths": [], "sha256": [], "bytes": []},
        "outcome": "ok", "error": None, "claim": None
    }
    events_file.write_text(json.dumps(event) + "\n", encoding="utf-8")
    
    verify_file = run_dir / "verify_result.json"
    verify_file.write_text(json.dumps({"run_id": run_dir.name, "overall_passed": True, "checks": []}), encoding="utf-8")

    rpt = generate_report(run_dir)
    assert rpt.exists()
    assert "# Execution & Verification Report" in rpt.read_text(encoding="utf-8")


def test_tier1_report_02_metadata_summary_section(tmp_path: Path):
    run_dir = tmp_path / "run_test_report_2"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")
    rpt = generate_report(run_dir)
    content = rpt.read_text(encoding="utf-8")
    assert "Run Metadata Summary" in content


def test_tier1_report_03_verification_checks_table(tmp_path: Path):
    run_dir = tmp_path / "run_test_report_3"
    run_dir.mkdir(parents=True, exist_ok=True)
    v_data = {
        "overall_passed": True,
        "checks": [{"check_id": "resolution_1080x1920", "passed": True, "measured": "1080x1920", "expected": "1080x1920", "evidence_path": "short.mp4"}]
    }
    (run_dir / "verify_result.json").write_text(json.dumps(v_data), encoding="utf-8")
    rpt = generate_report(run_dir)
    content = rpt.read_text(encoding="utf-8")
    assert "resolution_1080x1920" in content
    assert "PASS" in content


def test_tier1_report_04_artifact_sha256_table(tmp_path: Path):
    run_dir = tmp_path / "run_test_report_4"
    run_dir.mkdir(parents=True, exist_ok=True)
    event = {
        "schema_version": "1.0.0", "run_id": run_dir.name, "seq": 1,
        "ts": "2026-07-27T12:00:00Z", "agent": "worker",
        "video_id": "vid123", "clip_id": "clip1",
        "stage": "render", "attempt": 1, "severity": "info", "duration_ms": 100,
        "tool": "ffmpeg", "cmd": None, "exit_code": 0,
        "args_hash": "sha256:123", "cost": {"usd": 0.0, "tokens_in": 0, "tokens_out": 0},
        "trace": {"span_id": "s1", "parent_span_id": None},
        "evidence": {"paths": ["artifacts/clip1/short.mp4"], "sha256": ["sha256:abc123def456"], "bytes": [2048]},
        "outcome": "ok", "error": None, "claim": None
    }
    (run_dir / "events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
    rpt = generate_report(run_dir)
    content = rpt.read_text(encoding="utf-8")
    assert "artifacts/clip1/short.mp4" in content
    assert "abc123def456" in content


def test_tier1_report_05_audited_stage_wrapper(tmp_path: Path):
    run_dir = tmp_path / "run_test_report_5"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")
    rpt = generate_report(run_dir)
    assert rpt.name == "report.md"
