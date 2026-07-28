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
    assert "scale=270:480" in fg_blur
    assert "gblur=sigma=12.0" in fg_blur
    assert "scale=1080:1920" in fg_blur

    fg_crop = build_render_filtergraph(mode="crop_center", width=1080, height=1920)
    assert "scale=1080:1920:force_original_aspect_ratio=increase" in fg_crop
    assert "crop=1080:1920" in fg_crop


def test_process_vertical_render_success(
    tmp_path, monkeypatch, synthetic_media_and_subtitles
):
    """Test vertical 9:16 render with burned subtitles."""
    monkeypatch.chdir(tmp_path)
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
        blur_sigma=6.5,
        analytical_overlay=True,
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
    assert meta["blur_sigma"] == 6.5
    assert meta["subtitles_burned"] is True
    assert meta["subtitle_event_count"] == 1
    assert meta["overlay_text"] == "ANALYTICAL OVERLAY | VIRAL HOOK SCORE: 9.8"


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


@pytest.mark.parametrize("invalid_sigma", [True, "12", float("nan"), float("inf"), -0.1, 50.1])
def test_process_vertical_render_rejects_invalid_blur_sigma(
    tmp_path, synthetic_media_and_subtitles, invalid_sigma
):
    vid_p, _ = synthetic_media_and_subtitles

    with pytest.raises(ProcessingError, match="blur_sigma"):
        process_vertical_render.__wrapped__(
            input_media=vid_p,
            output_media=tmp_path / "invalid-blur.mp4",
            metadata_json=tmp_path / "invalid-blur.json",
            blur_sigma=invalid_sigma,
        )


def test_process_vertical_render_rejects_missing_or_empty_subtitles(
    tmp_path, synthetic_media_and_subtitles
):
    vid_p, valid_subtitles = synthetic_media_and_subtitles
    missing_subtitles = tmp_path / "missing.ass"

    with pytest.raises(ProcessingError, match="Subtitle source does not exist"):
        process_vertical_render.__wrapped__(
            input_media=vid_p,
            output_media=tmp_path / "missing-subtitles.mp4",
            metadata_json=tmp_path / "missing-subtitles.json",
            subtitles_path=missing_subtitles,
        )

    empty_subtitles = tmp_path / "empty.ass"
    empty_subtitles.write_text(
        "\n".join(
            line
            for line in valid_subtitles.read_text(encoding="utf-8").splitlines()
            if not line.startswith("Dialogue:")
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ProcessingError, match="visible timed event"):
        process_vertical_render.__wrapped__(
            input_media=vid_p,
            output_media=tmp_path / "empty-subtitles.mp4",
            metadata_json=tmp_path / "empty-subtitles.json",
            subtitles_path=empty_subtitles,
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


def test_run_render_callback_preserves_keyword_arguments():
    """Compatibility callbacks receive keywords consumed by the stage API."""

    def dummy_action(*, mode, template_variant):
        return mode, template_variant

    assert run_render(
        dummy_action,
        mode="crop_center",
        template_variant="variant_callback_1",
    ) == ("crop_center", "variant_callback_1")


def test_run_render_physically_mixes_t3_narration(
    tmp_path, monkeypatch, synthetic_media_and_subtitles
):
    """A T3 render must consume a real >=8s narration source via amix."""
    monkeypatch.chdir(tmp_path)
    run_id = "test_t3_narration_mix"
    set_run_id(run_id)
    video_path, subtitles_path = synthetic_media_and_subtitles
    narration_path = tmp_path / "narration.wav"
    narration_result = run_cmd(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:sample_rate=48000",
            "-t",
            "9",
            "-c:a",
            "pcm_s16le",
            str(narration_path),
        ],
        stage="env",
    )
    assert narration_result.returncode == 0

    result = run_render(
        video_path,
        subtitles_path=subtitles_path,
        run_id=run_id,
        clip_id="clip_editorial",
        narration_path=narration_path,
        tts_narration=True,
        analytical_overlay=True,
        overlay_text="ORIGINAL ANALYSIS",
        require_editorial_transformation=True,
        template_variant="variant_editorial_mix",
    )

    metadata = json.loads(
        pathlib.Path(result["metadata_path"]).read_text(encoding="utf-8")
    )
    assert metadata["narration_mixed"] is True
    assert metadata["narration_duration_s"] >= 8.0
    assert metadata["editorial_requirements"] == [
        "narration",
        "analytical_overlay",
    ]
    commands = (
        tmp_path / "runs" / run_id / "commands.log"
    ).read_text(encoding="utf-8")
    assert "amix=inputs=2" in commands
