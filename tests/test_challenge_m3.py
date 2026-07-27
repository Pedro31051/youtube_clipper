"""Adversarial stress and edge-case challenge test suite for Milestone 3 (Stages 5-8).

Empirically tests:
1. Cut (Stage 5): Invalid timestamps (start >= end, start < 0), missing video, clip size guardrails (>1024 bytes).
2. Subtitles (Stage 6): Empty transcript words, timestamp shifting, pysubs2 ASS format compliance.
3. Audio (Stage 7): 2-pass loudnorm target LUFS (-14.0 LUFS) strictly inside [-16.0, -13.0] LUFS.
4. Render (Stage 8): Vertical resolution 1080x1920, subtitle burning, file size guardrails (>1024 bytes).
5. Zero-Trust Verification (verify.py): Full pipeline run verification via cortes.verify.
"""

import json
import pathlib
import pytest
import pysubs2

from cortes.cut import cut_clip_stage, run_cut
from cortes.subtitles import generate_subtitles_stage, run_subtitles
from cortes.audio import process_audio_loudnorm, run_audio, parse_loudnorm_pass1_stderr
from cortes.render import build_render_filtergraph, process_vertical_render, run_render
from cortes.report import run_report
from cortes.verify import verify_run, measure_audio_loudness_lufs
from cortes.log import set_run_id, get_run_dir, run_cmd
from youtube_clipper.exceptions import ProcessingError


@pytest.fixture
def synthetic_source_media(tmp_path):
    """Generate a synthetic 25-second MP4 source video with video and audio streams."""
    vid_path = tmp_path / "source_test_media.mp4"
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
    return vid_path


# ============================================================================
# 1. CUT STAGE (Stage 5) ADVERSARIAL TESTS
# ============================================================================

def test_cut_invalid_timestamp_start_greater_than_end(synthetic_source_media):
    """Verify cut stage raises ProcessingError when start_sec >= end_sec."""
    with pytest.raises(ProcessingError, match="Invalid clip timestamp range"):
        cut_clip_stage(
            input_video_path=synthetic_source_media,
            start_sec=4.0,
            end_sec=2.0,
        )


def test_cut_invalid_timestamp_negative_start(synthetic_source_media):
    """Verify cut stage raises ProcessingError when start_sec < 0."""
    with pytest.raises(ProcessingError, match="Invalid clip timestamp range"):
        cut_clip_stage(
            input_video_path=synthetic_source_media,
            start_sec=-1.0,
            end_sec=2.0,
        )


def test_cut_missing_video_file(tmp_path):
    """Verify cut stage raises ProcessingError when input video file does not exist."""
    missing_vid = tmp_path / "non_existent_video.mp4"
    with pytest.raises(ProcessingError, match="does not exist"):
        cut_clip_stage(
            input_video_path=missing_vid,
            start_sec=0.0,
            end_sec=2.0,
        )


def test_cut_clip_size_guardrails(tmp_path, synthetic_source_media):
    """Verify cut clip produces output > 1024 bytes and valid duration."""
    run_id = f"test_cut_guardrails_{tmp_path.name}"
    set_run_id(run_id)

    out_clip = tmp_path / "guarded_clip.mp4"
    res = cut_clip_stage(
        input_video_path=synthetic_source_media,
        start_sec=1.0,
        end_sec=4.0,
        output_path=out_clip,
        fast_copy=False,
    )

    assert res["status"] == "ok"
    assert out_clip.exists()
    assert out_clip.stat().st_size > 1024

    # Verify ffprobe duration
    probe_cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(out_clip),
    ]
    probe_res = run_cmd(probe_cmd, stage="cut")
    assert probe_res.returncode == 0
    dur = float(probe_res.stdout.strip())
    assert dur > 0.0
    assert abs(dur - 3.0) < 0.5


# ============================================================================
# 2. SUBTITLES STAGE (Stage 6) ADVERSARIAL TESTS
# ============================================================================

def test_subtitles_empty_transcript_words(tmp_path):
    """Verify subtitles stage handles empty transcript words gracefully."""
    run_id = f"test_subs_empty_{tmp_path.name}"
    set_run_id(run_id)

    empty_transcript = {"text": "silent clip", "words": []}
    selection_data = {"start_ms": 1000, "end_ms": 5000}
    out_ass = tmp_path / "empty_subs.ass"

    res = generate_subtitles_stage(
        transcript_path_or_data=empty_transcript,
        selection_path_or_data=selection_data,
        output_path=out_ass,
    )

    assert res["status"] == "ok"
    assert res["total_events"] == 0
    assert out_ass.exists()

    # Load with pysubs2 to verify valid empty ASS structure
    subs = pysubs2.load(str(out_ass), encoding="utf-8")
    assert len(subs.events) == 0
    assert subs.info["PlayResX"] == "1080"
    assert subs.info["PlayResY"] == "1920"


def test_subtitles_timestamp_shifting(tmp_path):
    """Verify subtitle timestamp shifting from absolute to clip-relative time."""
    run_id = f"test_subs_shift_{tmp_path.name}"
    set_run_id(run_id)

    transcript_data = {
        "text": "Before selection inside selection after selection",
        "words": [
            {"word": "Before", "start_ms": 500, "end_ms": 1500},
            {"word": "inside", "start_ms": 2500, "end_ms": 3500},
            {"word": "selection", "start_ms": 3500, "end_ms": 4500},
            {"word": "after", "start_ms": 5500, "end_ms": 6500},
        ],
    }

    # Clip window: 2000ms to 5000ms (duration 3000ms)
    selection_data = {"start_ms": 2000, "end_ms": 5000}
    out_ass = tmp_path / "shifted_subs.ass"

    res = generate_subtitles_stage(
        transcript_path_or_data=transcript_data,
        selection_path_or_data=selection_data,
        output_path=out_ass,
    )

    assert res["status"] == "ok"
    assert res["total_events"] == 2  # "inside" and "selection"

    subs = pysubs2.load(str(out_ass), encoding="utf-8")
    assert len(subs.events) == 2

    # "inside": original [2500, 3500] -> clip relative [500, 1500]
    ev0 = subs.events[0]
    assert ev0.text == "inside"
    assert ev0.start == 500
    assert ev0.end == 1500

    # "selection": original [3500, 4500] -> clip relative [1500, 2500]
    ev1 = subs.events[1]
    assert ev1.text == "selection"
    assert ev1.start == 1500
    assert ev1.end == 2500


def test_subtitles_pysubs2_ass_format_compliance(tmp_path):
    """Verify ASS subtitle canvas, font, styling, and positioning compliance."""
    run_id = f"test_subs_compliance_{tmp_path.name}"
    set_run_id(run_id)

    transcript_data = {
        "words": [{"word": "ComplianceTest", "start_ms": 1000, "end_ms": 2000}]
    }
    selection_data = {"start_ms": 0, "end_ms": 3000}
    out_ass = tmp_path / "compliance_subs.ass"

    res = generate_subtitles_stage(
        transcript_path_or_data=transcript_data,
        selection_path_or_data=selection_data,
        output_path=out_ass,
        font_name="Roboto",
        font_size=80,
        margin_v=400,
    )

    assert res["status"] == "ok"

    subs = pysubs2.load(str(out_ass), encoding="utf-8")
    assert subs.info["PlayResX"] == "1080"
    assert subs.info["PlayResY"] == "1920"

    assert "Default" in subs.styles
    style = subs.styles["Default"]
    assert style.fontname == "Roboto"
    assert style.fontsize == 80
    assert style.alignment == pysubs2.Alignment.BOTTOM_CENTER
    assert style.marginv == 400


# ============================================================================
# 3. AUDIO STAGE (Stage 7) ADVERSARIAL TESTS
# ============================================================================

def test_audio_loudnorm_lufs_strict_range(tmp_path, synthetic_source_media):
    """Verify 2-pass loudnorm output LUFS is strictly within [-16.0, -13.0] LUFS range."""
    run_id = f"test_audio_lufs_range_{tmp_path.name}"
    set_run_id(run_id)

    out_media = tmp_path / "audio_normalized.mp4"
    stats_json = tmp_path / "audio_stats.json"

    res = process_audio_loudnorm(
        input_media=synthetic_source_media,
        output_media=out_media,
        stats_json=stats_json,
        target_lufs=-14.0,
    )

    assert res["status"] == "ok"
    assert out_media.exists()
    assert out_media.stat().st_size > 1024

    measured_lufs = measure_audio_loudness_lufs(out_media)
    # Target LUFS is -14.0, must be strictly in [-16.0, -13.0]
    assert -16.0 <= measured_lufs <= -13.0, f"Measured LUFS {measured_lufs} outside [-16.0, -13.0]"


# ============================================================================
# 4. RENDER STAGE (Stage 8) ADVERSARIAL TESTS
# ============================================================================

def test_render_vertical_resolution_1080x1920(tmp_path, synthetic_source_media):
    """Verify render stage produces video with exact 1080x1920 vertical resolution."""
    run_id = f"test_render_res_{tmp_path.name}"
    set_run_id(run_id)

    out_media = tmp_path / "short_1080x1920.mp4"
    meta_json = tmp_path / "render_metadata.json"

    res = process_vertical_render(
        input_media=synthetic_source_media,
        output_media=out_media,
        metadata_json=meta_json,
        mode="blur_background",
        width=1080,
        height=1920,
    )

    assert res["status"] == "ok"
    assert out_media.exists()
    assert out_media.stat().st_size > 1024

    probe_cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        str(out_media),
    ]
    probe_res = run_cmd(probe_cmd, stage="render")
    assert probe_res.returncode == 0
    w_str, h_str = probe_res.stdout.strip().split(",")
    assert int(w_str) == 1080
    assert int(h_str) == 1920


def test_render_subtitle_burning(tmp_path, synthetic_source_media):
    """Verify render stage burns ASS subtitles into output vertical video."""
    run_id = f"test_render_sub_burn_{tmp_path.name}"
    set_run_id(run_id)

    sub_path = tmp_path / "burned_test.ass"
    sub_content = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Roboto,80,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,50,50,400,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:03.00,Default,,0,0,0,,BurnedSubtitleTest
"""
    sub_path.write_text(sub_content, encoding="utf-8")

    out_media = tmp_path / "short_burned.mp4"
    meta_json = tmp_path / "render_metadata.json"

    res = process_vertical_render(
        input_media=synthetic_source_media,
        output_media=out_media,
        metadata_json=meta_json,
        subtitles_path=sub_path,
        mode="blur_background",
    )

    assert res["status"] == "ok"
    assert out_media.exists()

    meta = json.loads(meta_json.read_text(encoding="utf-8"))
    assert meta["subtitles_burned"] is True
    assert meta["subtitles_path"] == str(sub_path)


def test_render_file_size_guardrails(tmp_path, synthetic_source_media):
    """Verify render stage enforces file size guardrail (>1024 bytes)."""
    run_id = f"test_render_guardrail_{tmp_path.name}"
    set_run_id(run_id)

    out_media = tmp_path / "short_guarded.mp4"
    meta_json = tmp_path / "render_metadata.json"

    res = process_vertical_render(
        input_media=synthetic_source_media,
        output_media=out_media,
        metadata_json=meta_json,
        mode="crop_center",
    )

    assert res["status"] == "ok"
    assert out_media.exists()
    assert out_media.stat().st_size > 1024


# ============================================================================
# 5. ZERO-TRUST VERIFICATION ENGINE TESTS
# ============================================================================

def test_zero_trust_verification_passes_on_valid_run(tmp_path, synthetic_source_media):
    """Verify zero-trust verify_run passes on a complete Stages 5-9 run."""
    run_id = f"test_zero_trust_valid_{tmp_path.name}"
    set_run_id(run_id)

    # 1. Save selection fixture
    run_dir = get_run_dir(run_id)
    sel_dir = run_dir / "artifacts" / "select"
    sel_dir.mkdir(parents=True, exist_ok=True)
    sel_data = {"start_ms": 0, "end_ms": 25000}
    (sel_dir / "selection.json").write_text(json.dumps(sel_data), encoding="utf-8")

    # 2. Stage 5: Cut
    cut_res = run_cut(synthetic_source_media, selection_path_or_data=sel_data, run_id=run_id, fast_copy=False)
    cut_path = cut_res["cut_path"]

    # 3. Stage 6: Subtitles
    transcript_data = {
        "text": "Zero trust verification pipeline test",
        "words": [
            {"word": "Zero", "start_ms": 200, "end_ms": 800},
            {"word": "trust", "start_ms": 800, "end_ms": 1400},
            {"word": "verification", "start_ms": 1400, "end_ms": 2500},
            {"word": "pipeline", "start_ms": 2500, "end_ms": 3500},
            {"word": "test", "start_ms": 3500, "end_ms": 4500},
        ],
    }
    sub_res = run_subtitles(transcript_data, selection_path_or_data=sel_data, run_id=run_id)
    sub_path = sub_res["subtitles_path"]

    # 4. Stage 7: Audio
    audio_res = run_audio(cut_path, run_id=run_id)
    audio_path = audio_res["audio_path"]

    # 5. Stage 8: Render
    render_res = run_render(audio_path, subtitles_path=sub_path, run_id=run_id, mode="blur_background")

    # 6. Run zero-trust verification engine
    ver_res = verify_run(run_dir)

    assert ver_res["overall_passed"] is True
    assert ver_res["failed_checks"] == 0
    assert ver_res["passed_checks"] > 0
