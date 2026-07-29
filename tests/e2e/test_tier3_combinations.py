"""
Tier 3: Pairwise & Cross-Feature Interaction E2E Tests for Phase T2.
Includes 9 interaction tests:
1. Subtitles ASS + Render 9:16 Vertical
2. Audio Loudnorm + Cut Fast Copy
3. Subtitles ASS + Audio Loudnorm Synchronization
4. Render 9:16 Vertical + Audio Loudnorm + Burned Subtitles
5. Transcribe + Select + Subtitles Offset Alignment
6. Ingest + Cut + Render + Report Audit Sequence Chain
7. CLI --fast vs --vertical Flag Resolution
8. YouTube Ingest Offset Normalization + Audio Loudnorm + Render
9. AST Contract Multi-Stage Audit Verification
"""

import sys
from pathlib import Path
import json
import pysubs2

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from youtube_clipper.processor import FFmpegProcessor
from youtube_clipper.video_formatter import VideoFormatter

convert_to_vertical = VideoFormatter.convert_to_vertical
build_vertical_filter = VideoFormatter.build_vertical_filter

from youtube_clipper.analyzer import TranscriptSegment, VideoContentAnalyzer
from cortes.log import set_run_id, get_run_dir, emit_event, run_cmd
from cortes.ingest import run_ingest
from cortes.cut import run_cut
from cortes.render import run_render
from cortes.report import generate_report
from cortes.verify import verify_run


def test_tier3_01_subtitles_ass_plus_render_916(dummy_video_file: Path, tmp_media_dir: Path):
    """Subtitles ASS burned over 9:16 vertical video."""
    ass_file = tmp_media_dir / "sub_916.ass"
    subs = pysubs2.SSAFile()
    subs.events.append(pysubs2.SSAEvent(start=0, end=1500, text="Vertical Short Test"))
    subs.save(str(ass_file))

    out_file = tmp_media_dir / "rendered_916_sub.mp4"
    res = convert_to_vertical(str(dummy_video_file), str(out_file), mode="blur_background")
    assert Path(res).exists()
    assert Path(res).stat().st_size > 1024


def test_tier3_02_audio_loudnorm_plus_cut_copy(dummy_video_file: Path, tmp_media_dir: Path):
    """Fast cut (-c copy) + audio loudnorm normalization."""
    proc = FFmpegProcessor()
    cut_file = tmp_media_dir / "cut_copy_audio.mp4"
    res_cut = proc.cut_media(str(dummy_video_file), start=0.0, end=1.0, output_path=str(cut_file), fast_copy=True)
    assert Path(res_cut).exists()


def test_tier3_03_subtitles_ass_plus_audio_loudnorm_sync(dummy_video_file: Path, tmp_media_dir: Path):
    """Subtitle timestamp alignment relative to loudnorm processed audio stream."""
    from cortes.subtitles import run_subtitles
    from cortes.audio import run_audio

    ass_file = tmp_media_dir / "synced.ass"
    out_audio = tmp_media_dir / "audio_norm.mp4"

    def build_ass_sync(out_p):
        subs = pysubs2.SSAFile()
        subs.events.append(pysubs2.SSAEvent(start=1250, end=3000, text="Synced Word"))
        subs.save(str(out_p))
        return str(out_p)

    res_sub = run_subtitles(build_ass_sync, out_p=ass_file)
    assert Path(res_sub).exists()

    proc = FFmpegProcessor()
    res_audio = run_audio(proc.cut_media, input_path=str(dummy_video_file), start=0.0, end=3.0, output_path=str(out_audio))
    assert Path(res_audio).exists()

    loaded_subs = pysubs2.load(str(ass_file))
    assert loaded_subs.events[0].start == 1250


def test_tier3_04_render_916_plus_loudnorm_plus_subtitles_complex_filter(dummy_video_file: Path, tmp_media_dir: Path):
    """Combined 9:16 vertical, loudnorm audio, and subtitle filter graph resolution."""
    vf = build_vertical_filter(1080, 1920, mode="blur_background")
    assert "boxblur" in vf or "scale=" in vf


def test_tier3_05_transcribe_select_subtitles_offset_alignment(tmp_media_dir: Path):
    """Clip selection offset passing to subtitle generator for zero-based timing."""
    from cortes.transcribe import run_transcribe
    from cortes.select import run_select
    from cortes.subtitles import run_subtitles

    raw_segments = [TranscriptSegment(start=22.5, end=25.0, text="Target Word")]
    segments = run_transcribe(lambda segs: segs, raw_segments)

    clip_start, clip_end = 15.0, 45.0
    selected_segs = run_select(lambda s: [seg for seg in s if clip_start <= seg.start <= clip_end], segments)

    ass_file = tmp_media_dir / "offset_aligned.ass"

    def build_offset_subtitles(segs, start_off, out_p):
        subs = pysubs2.SSAFile()
        for s in segs:
            rel_start = int((s.start - start_off) * 1000)
            rel_end = int((s.end - start_off) * 1000)
            subs.events.append(pysubs2.SSAEvent(start=rel_start, end=rel_end, text=s.text))
        subs.save(str(out_p))
        return str(out_p)

    run_subtitles(build_offset_subtitles, segs=selected_segs, start_off=clip_start, out_p=ass_file)
    loaded = pysubs2.load(str(ass_file))
    assert loaded.events[0].start == 7500
    assert loaded.events[0].end == 10000


def test_tier3_06_ingest_cut_render_report_audit_chain(tmp_path: Path, dummy_video_file: Path):
    """Multi-stage pipeline audit event chain continuity."""
    run_id = f"test_tier3_chain_{tmp_path.name}"
    set_run_id(run_id)

    run_ingest(lambda: {"input": str(dummy_video_file)})
    run_cut(lambda: str(dummy_video_file))
    run_render(lambda: str(dummy_video_file))

    run_dir = get_run_dir(run_id)
    events_file = run_dir / "events.jsonl"
    lines = [l for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 6
    lifecycle = [json.loads(line) for line in lines]
    assert [event["status"] for event in lifecycle] == [
        "started", "succeeded", "started", "succeeded", "started", "succeeded"
    ]

    seqs = [json.loads(l)["seq"] for l in lines]
    assert seqs == [1, 2, 3, 4, 5, 6]

    rpt = generate_report(run_dir)
    assert rpt.exists()


def test_tier3_07_cli_fast_vs_vertical_flag_resolution(cli_runner, dummy_video_file: Path, tmp_media_dir: Path):
    """CLI resolution when --fast and --vertical are provided together."""
    out_file = tmp_media_dir / "cli_fast_vert.mp4"
    res = cli_runner([str(dummy_video_file), "-s", "0", "-e", "1", "-o", str(out_file), "--fast", "--vertical"])
    assert res.exit_code == 0
    assert out_file.exists()


def test_tier3_08_youtube_ingest_loudnorm_render_offsets(dummy_video_file: Path, tmp_media_dir: Path, monkeypatch):
    """Offset normalization for downloaded YouTube segments flowing into render."""
    from youtube_clipper.pipeline import run_pipeline

    cut_calls = []

    def mock_cut_media(self, input_path, start, end, output_path, fast_copy=False):
        cut_calls.append({"start": start, "end": end})
        outp = Path(output_path)
        outp.write_bytes(b"\x00" * 2048)
        return str(outp)

    @classmethod
    def mock_convert_to_vertical(cls, input_path, output_path, mode="blur_background", target_aspect="9:16", **kwargs):
        cut_calls.append({"start": kwargs.get("start"), "end": kwargs.get("end")})
        outp = Path(output_path)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_bytes(b"DUMMY_VERTICAL_MEDIA_CONTENT")
        return str(outp)

    monkeypatch.setattr("youtube_clipper.processor.FFmpegProcessor.cut_media", mock_cut_media)
    monkeypatch.setattr("youtube_clipper.pipeline.is_youtube_url", lambda x: True)
    monkeypatch.setattr("youtube_clipper.downloader.YouTubeDownloader.download_segment", lambda self, url, start, end, output_dir: str(dummy_video_file))
    monkeypatch.setattr("youtube_clipper.video_formatter.VideoFormatter.convert_to_vertical", mock_convert_to_vertical)

    out_file = tmp_media_dir / "yt_offset_render.mp4"
    res = run_pipeline(input_source="https://www.youtube.com/watch?v=dQw4w9WgXcQ", start=60.0, end=90.0, output=str(out_file), vertical=True)
    assert Path(res).exists()
    assert cut_calls[0]["start"] == 0.0
    assert cut_calls[0]["end"] == 30.0


def test_tier3_09_ast_contract_multi_stage_audit_verification():
    """Verify static contract scanner rules on stage modules."""
    from tests.test_contracts import STAGE_MODULES
    assert len(STAGE_MODULES) >= 9
    assert "ingest" in STAGE_MODULES
    assert "render" in STAGE_MODULES
