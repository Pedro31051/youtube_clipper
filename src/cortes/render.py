"""Audited Stage 8 (render) processing module."""

import json
import os
import pathlib
from typing import Any, Callable, Dict, Optional, Union

from cortes.log import audited, get_run_dir, run_cmd
from youtube_clipper.exceptions import ProcessingError


from youtube_clipper.video_formatter import detect_h264_encoder


@audited(stage="render")
def build_render_filtergraph(
    mode: str = "blur_background",
    subtitles_path: Optional[Union[str, pathlib.Path]] = None,
    width: int = 1080,
    height: int = 1920,
    sigma: float = 12.0,
    analytical_overlay: bool = False,
    overlay_text: Optional[str] = None,
) -> str:
    """Build FFmpeg 9:16 vertical video filtergraph with optional burned ASS subtitles and analytical overlay."""
    if mode in ("blur_background", "split_blur"):
        low_w = width // 4
        low_h = height // 4
        v_filter = (
            f"split[bg][fg];"
            f"[bg]scale={low_w}:{low_h}:force_original_aspect_ratio=increase,crop={low_w}:{low_h},gblur=sigma={sigma},scale={width}:{height}[blurred];"
            f"[fg]scale={width}:-2[scaled_fg];"
            f"[blurred][scaled_fg]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2"
        )
    elif mode == "crop_center":
        v_filter = f"crop=ih*9/16:ih:(iw-ow)/2:0,scale={width}:{height}"
    else:
        raise ValueError(f"Unsupported vertical render mode: {mode}")

    if analytical_overlay:
        txt = overlay_text or "ANALYTICAL OVERLAY | VIRAL HOOK SCORE: 9.8"
        esc_txt = txt.replace(":", "\\:").replace("'", "")
        v_filter = f"{v_filter},drawbox=x=40:y=60:w=1000:h=100:color=black@0.6:t=fill,drawtext=text='{esc_txt}':x=60:y=95:fontsize=36:fontcolor=yellow"

    if subtitles_path:
        sub_p = pathlib.Path(subtitles_path).resolve()
        if sub_p.exists():
            esc_sub = str(sub_p).replace("\\", "/").replace(":", "\\:")
            v_filter = f"{v_filter},subtitles={esc_sub}"

    return v_filter


@audited(stage="render")
def process_vertical_render(
    input_media: Union[str, pathlib.Path],
    output_media: Union[str, pathlib.Path],
    metadata_json: Union[str, pathlib.Path],
    subtitles_path: Optional[Union[str, pathlib.Path]] = None,
    mode: str = "blur_background",
    width: int = 1080,
    height: int = 1920,
    clip_id: Optional[str] = None,
    analytical_overlay: bool = False,
    overlay_text: Optional[str] = None,
    tts_narration: bool = False,
    tts_duration_s: float = 0.0,
    template_variant: str = "variant_default",
) -> Dict[str, Any]:
    """Execute 9:16 vertical video rendering with burned ASS subtitles and analytical overlay."""
    in_p = pathlib.Path(input_media).resolve()
    if not in_p.exists():
        raise ProcessingError(f"Input media for render stage does not exist: {in_p}")

    out_p = pathlib.Path(output_media).resolve()
    meta_p = pathlib.Path(metadata_json).resolve()

    out_p.parent.mkdir(parents=True, exist_ok=True)
    meta_p.parent.mkdir(parents=True, exist_ok=True)

    filtergraph = build_render_filtergraph(
        mode=mode,
        subtitles_path=subtitles_path,
        width=width,
        height=height,
        analytical_overlay=analytical_overlay,
        overlay_text=overlay_text,
    )

    encoder = detect_h264_encoder()
    vcodec_args = ["-c:v", "h264_nvenc", "-preset", "p4"] if encoder == "h264_nvenc" else ["-c:v", "libx264", "-preset", "medium", "-crf", "23"]

    cmd = [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-hide_banner",
        "-i",
        str(in_p),
        "-filter_complex" if ("split" in filtergraph or "draw" in filtergraph) else "-vf",
        filtergraph,
        *vcodec_args,
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-pix_fmt",
        "yuv420p",
        str(out_p),
    ]

    res = run_cmd(cmd, stage="render")
    if res.returncode != 0 or not out_p.exists() or out_p.stat().st_size <= 1024:
        raise ProcessingError(f"FFmpeg vertical render failed with returncode {res.returncode}: {res.stderr}")

    sub_exists = bool(subtitles_path and pathlib.Path(subtitles_path).exists())
    meta = {
        "schema_version": "1.0.0",
        "clip_id": clip_id,
        "width": width,
        "height": height,
        "mode": mode,
        "subtitles_burned": sub_exists,
        "subtitles_path": str(subtitles_path) if subtitles_path else None,
        "tts_narration": tts_narration,
        "tts_narration_duration_s": tts_duration_s,
        "analytical_overlay": analytical_overlay,
        "template_variant": template_variant,
        "output_size_bytes": out_p.stat().st_size,
    }
    meta_p.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {
        "status": "ok",
        "render_path": str(out_p),
        "metadata_path": str(meta_p),
        "evidence_paths": [str(out_p), str(meta_p)],
    }


@audited(stage="render")
def run_render(
    input_source_or_action: Union[str, pathlib.Path, Callable[..., Any]],
    *args: Any,
    subtitles_path: Optional[Union[str, pathlib.Path]] = None,
    run_id: Optional[str] = None,
    clip_id: Optional[str] = None,
    mode: str = "blur_background",
    output_path: Optional[Union[str, pathlib.Path]] = None,
    analytical_overlay: bool = False,
    overlay_text: Optional[str] = None,
    tts_narration: bool = False,
    tts_duration_s: float = 0.0,
    template_variant: str = "variant_default",
    **kwargs: Any,
) -> Any:
    """Audited entrypoint for Stage 8 (render). Supports action callback or stage execution."""
    if callable(input_source_or_action):
        callback_kwargs = dict(kwargs)
        if output_path is not None:
            callback_kwargs["output_path"] = output_path
        return input_source_or_action(*args, **callback_kwargs)

    in_p = pathlib.Path(input_source_or_action).resolve()
    if not in_p.exists():
        raise ProcessingError(f"Input media for render stage does not exist: {in_p}")

    run_dir = get_run_dir(run_id)
    render_dir = (
        run_dir / "artifacts" / clip_id
        if clip_id
        else run_dir / "artifacts" / "render"
    )
    out_media = pathlib.Path(output_path).resolve() if output_path else render_dir / "short.mp4"
    meta_json = render_dir / "render_metadata.json"

    result = process_vertical_render(
        input_media=in_p,
        output_media=out_media,
        metadata_json=meta_json,
        subtitles_path=subtitles_path,
        mode=mode,
        clip_id=clip_id,
        analytical_overlay=analytical_overlay,
        overlay_text=overlay_text,
        tts_narration=tts_narration,
        tts_duration_s=tts_duration_s,
        template_variant=template_variant,
    )
    if clip_id:
        # Preserve the historical discovery path without duplicating media.
        compat_dir = run_dir / "artifacts" / "render"
        compat_dir.mkdir(parents=True, exist_ok=True)
        compat_short = compat_dir / "short.mp4"
        compat_meta = compat_dir / "render_metadata.json"
        for link_path, target_path in (
            (compat_short, out_media),
            (compat_meta, meta_json),
        ):
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()
            link_path.symlink_to(os.path.relpath(target_path, link_path.parent))
    return result
