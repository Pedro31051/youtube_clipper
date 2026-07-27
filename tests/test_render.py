"""Unit tests for Stage 8 (render) module cortes.render."""

import json
import pathlib
import pytest
from cortes.log import run_cmd, set_run_id
from cortes.render import build_render_filtergraph, process_vertical_render, run_render
from youtube_clipper.exceptions import ProcessingError


@pytest.fixture
def synthetic_media_and_subtitles(tmp_path):
    """Generate synthetic video and ASS subtitles fixtures."""
    vid_path = tmp_path / "render_input.mp4"
    cmd_vid = [
        "ffmpeg",
        "-y",
        "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-t", "3",
        "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        str(vid_path),
    ]
    res_vid = run_cmd(cmd_vid, stage="render")
    assert res_vid.returncode == 0
    assert vid_path.exists()

    sub_path = tmp_path / "test_subs.ass"
    sub_content = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Roboto,80,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,50,50,400,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,Hello Render Test
"""
    sub_path.write_text(sub_content, encoding="utf-8")

    return vid_path, sub_path


def test_build_render_filtergraph():
    """Test filtergraph construction for blur_background and crop_center modes."""
    fg_blur = build_render_filtergraph(mode="blur_background", width=1080, height=1920)
    assert "split[bg][fg]" in fg_blur
    assert "boxblur=20:10" in fg_blur
    assert "scale=1080:1920" in fg_blur

    fg_crop = build_render_filtergraph(mode="crop_center", width=1080, height=1920)
    assert "crop=ih*9/16:ih" in fg_crop
    assert "scale=1080:1920" in fg_crop


def test_process_vertical_render_success(tmp_path, synthetic_media_and_subtitles):
    """Test vertical 9:16 render with burned subtitles."""
    run_id = f"test_render_success_{tmp_path.name}"
    set_run_id(run_id)

    vid_p, sub_p = synthetic_media_and_subtitles
    from cortes.log import get_run_dir
    run_dir = get_run_dir(run_id)
    out_media = run_dir / "short.mp4"
    meta_json = run_dir / "render_metadata.json"

    res = process_vertical_render(
        input_media=vid_p,
        output_media=out_media,
        metadata_json=meta_json,
        subtitles_path=sub_p,
        mode="blur_background",
    )

    assert res["status"] == "ok"
    assert pathlib.Path(res["render_path"]).exists()
    assert out_media.stat().st_size > 1024

    # Probe resolution via ffprobe
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

    meta = json.loads(meta_json.read_text(encoding="utf-8"))
    assert meta["width"] == 1080
    assert meta["height"] == 1920
    assert meta["subtitles_burned"] is True


def test_process_vertical_render_missing_input(tmp_path):
    """Test process_vertical_render raises ProcessingError for non-existent input video."""
    missing = tmp_path / "missing.mp4"
    out_media = tmp_path / "short.mp4"
    meta_json = tmp_path / "meta.json"

    with pytest.raises(ProcessingError, match="does not exist"):
        process_vertical_render(
            input_media=missing,
            output_media=out_media,
            metadata_json=meta_json,
        )


def test_run_render_callback_delegation():
    """Test run_render delegates to action callback."""
    called = []

    def dummy_action(val):
        called.append(val)
        return "render_result"

    res = run_render(dummy_action, "test_val")
    assert res == "render_result"
    assert called == ["test_val"]
