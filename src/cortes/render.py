"""Audited Stage 8 (render) processing module."""

import json
import math
import os
import pathlib
import shutil
from typing import Any, Callable, Dict, Optional, Union

import pysubs2

from cortes.editorial import (
    assert_variant_not_recent,
    parse_loudnorm_measurement,
    recent_template_records,
    validate_template_variant,
)
from cortes.log import audited, compute_sha256, get_run_dir, run_cmd
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

    if subtitles_path is not None:
        sub_p = pathlib.Path(subtitles_path).resolve()
        if not sub_p.exists() or not sub_p.is_file():
            raise ProcessingError(f"Subtitle source does not exist: {sub_p}")
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
    narration_path: Optional[Union[str, pathlib.Path]] = None,
    tts_narration: bool = False,
    require_editorial_transformation: bool = False,
    template_variant: str = "variant_default",
    template_history: Optional[list[Dict[str, Any]]] = None,
    run_dir: Optional[Union[str, pathlib.Path]] = None,
    blur_sigma: float = 12.0,
) -> Dict[str, Any]:
    """Render a vertical video and physically apply the requested T3 transformation."""
    in_p = pathlib.Path(input_media).resolve()
    if not in_p.exists():
        raise ProcessingError(f"Input media for render stage does not exist: {in_p}")

    out_p = pathlib.Path(output_media).resolve()
    meta_p = pathlib.Path(metadata_json).resolve()

    out_p.parent.mkdir(parents=True, exist_ok=True)
    meta_p.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(blur_sigma, bool) or not isinstance(blur_sigma, (int, float)):
        raise ProcessingError("blur_sigma must be a finite number between 0 and 50")
    try:
        normalized_blur_sigma = float(blur_sigma)
    except (TypeError, ValueError) as exc:
        raise ProcessingError(
            "blur_sigma must be a finite number between 0 and 50"
        ) from exc
    if not math.isfinite(normalized_blur_sigma) or not 0.0 <= normalized_blur_sigma <= 50.0:
        raise ProcessingError("blur_sigma must be a finite number between 0 and 50")

    subtitles_p: Optional[pathlib.Path] = None
    subtitle_event_count = 0
    if subtitles_path is not None:
        subtitles_p = pathlib.Path(subtitles_path).resolve()
        if not subtitles_p.exists() or not subtitles_p.is_file():
            raise ProcessingError(f"Subtitle source does not exist: {subtitles_p}")
        try:
            subtitle_file = pysubs2.load(str(subtitles_p), encoding="utf-8")
        except Exception as exc:
            raise ProcessingError(f"Unable to parse subtitle source: {subtitles_p}") from exc
        subtitle_event_count = sum(
            1
            for event in subtitle_file.events
            if event.text.strip() and int(event.end) > int(event.start)
        )
        if subtitle_event_count == 0:
            raise ProcessingError(
                "Subtitle source must contain at least one visible timed event"
            )

    narration_p: Optional[pathlib.Path] = None
    narration_duration_s = 0.0
    if narration_path is not None:
        narration_p = pathlib.Path(narration_path).resolve()
        if not narration_p.exists() or not narration_p.is_file():
            raise ProcessingError(f"Narration source does not exist: {narration_p}")
        probe = run_cmd(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(narration_p),
            ],
            stage="render",
            audit=False,
        )
        try:
            narration_duration_s = float(probe.stdout.strip())
        except (AttributeError, TypeError, ValueError) as exc:
            raise ProcessingError(
                f"Unable to measure narration duration: {probe.stderr}"
            ) from exc
        if probe.returncode != 0 or narration_duration_s < 8.0:
            raise ProcessingError(
                "T3 narration must be a valid audio file with duration >= 8.0 seconds"
            )

    if tts_narration and narration_p is None:
        raise ProcessingError(
            "tts_narration=True requires a physical narration_path; metadata-only narration is forbidden"
        )
    narration_mixed = narration_p is not None
    if require_editorial_transformation and not (
        narration_mixed or analytical_overlay
    ):
        raise ProcessingError(
            "T3 requires narration >= 8 seconds and/or an analytical overlay"
        )
    variant = validate_template_variant(
        template_variant,
        allow_default=not require_editorial_transformation,
    )

    effective_overlay_text = (
        overlay_text or "ANALYTICAL OVERLAY | VIRAL HOOK SCORE: 9.8"
        if analytical_overlay
        else None
    )
    filtergraph = build_render_filtergraph(
        mode=mode,
        subtitles_path=subtitles_p,
        width=width,
        height=height,
        sigma=normalized_blur_sigma,
        analytical_overlay=analytical_overlay,
        overlay_text=effective_overlay_text,
    )

    encoder = detect_h264_encoder()
    vcodec_args = (
        ["-c:v", "h264_nvenc", "-preset", "p4"]
        if encoder == "h264_nvenc"
        else ["-c:v", "libx264", "-preset", "medium", "-crf", "23"]
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-hide_banner",
        "-i",
        str(in_p),
    ]
    if narration_p is not None:
        cmd.extend(["-i", str(narration_p)])
        audio_mix = (
            "[0:a]volume=0.35[base_audio];"
            "[1:a]volume=1.0[narration_audio];"
            "[base_audio][narration_audio]"
            "amix=inputs=2:duration=first:dropout_transition=0:normalize=0"
        )
        loudnorm_preflight = run_cmd(
            [
                "ffmpeg",
                "-y",
                "-nostdin",
                "-hide_banner",
                "-i",
                str(in_p),
                "-i",
                str(narration_p),
                "-filter_complex",
                (
                    f"{audio_mix}[mixed_measure];"
                    "[mixed_measure]"
                    "loudnorm=I=-14.0:LRA=11:TP=-1.0:print_format=json"
                    "[audio_measure]"
                ),
                "-map",
                "[audio_measure]",
                "-f",
                "null",
                "-",
            ],
            stage="render",
        )
        if loudnorm_preflight.returncode != 0:
            raise ProcessingError(
                f"Narration loudness preflight failed: {loudnorm_preflight.stderr}"
            )
        loudnorm_stats = parse_loudnorm_measurement(loudnorm_preflight.stderr)
        measured_loudnorm = (
            "loudnorm=I=-14.0:LRA=11:TP=-1.0:"
            f"measured_I={loudnorm_stats['input_i']}:"
            f"measured_LRA={loudnorm_stats['input_lra']}:"
            f"measured_TP={loudnorm_stats['input_tp']}:"
            f"measured_thresh={loudnorm_stats['input_thresh']}:"
            f"offset={loudnorm_stats['target_offset']}:"
            "linear=true"
        )
        filtergraph = (
            f"{filtergraph}[vout];"
            f"{audio_mix}[mixed_audio];"
            f"[mixed_audio]{measured_loudnorm}[aout]"
        )
        cmd.extend(
            [
                "-filter_complex",
                filtergraph,
                "-map",
                "[vout]",
                "-map",
                "[aout]",
            ]
        )
    else:
        cmd.extend(
            [
                "-filter_complex"
                if ("split" in filtergraph or "draw" in filtergraph)
                else "-vf",
                filtergraph,
            ]
        )
    cmd.extend(
        [
            *vcodec_args,
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-pix_fmt",
            "yuv420p",
            str(out_p),
        ]
    )

    res = run_cmd(cmd, stage="render")
    if res.returncode != 0 and encoder == "h264_nvenc":
        if out_p.exists():
            out_p.unlink()
        fallback_cmd = list(cmd)
        codec_index = fallback_cmd.index("h264_nvenc")
        fallback_cmd[codec_index : codec_index + 3] = [
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
        ]
        res = run_cmd(fallback_cmd, stage="render")
        encoder = "libx264"
    if res.returncode != 0 or not out_p.exists() or out_p.stat().st_size <= 1024:
        raise ProcessingError(f"FFmpeg vertical render failed with returncode {res.returncode}: {res.stderr}")

    subtitles_filter_applied = bool(
        subtitles_p is not None and ",subtitles=" in filtergraph
    )
    run_root = pathlib.Path(run_dir).resolve() if run_dir else None
    narration_source_path: Optional[str] = None
    if narration_p is not None:
        if run_root is not None:
            try:
                narration_source_path = str(narration_p.relative_to(run_root))
            except ValueError as exc:
                raise ProcessingError(
                    "Narration evidence must be copied inside the active run directory"
                ) from exc
        else:
            narration_source_path = str(narration_p)

    meta = {
        "schema_version": "1.0.0",
        "phase": "T3" if require_editorial_transformation else "T2",
        "clip_id": clip_id,
        "width": width,
        "height": height,
        "mode": mode,
        "blur_sigma": (
            normalized_blur_sigma
            if mode in {"blur_background", "split_blur"}
            else None
        ),
        "subtitles_burned": subtitles_filter_applied,
        "subtitles_path": str(subtitles_p) if subtitles_p is not None else None,
        "subtitle_event_count": subtitle_event_count,
        "editorial_transformation_required": require_editorial_transformation,
        "editorial_requirements": [
            requirement
            for requirement, enabled in (
                ("narration", narration_mixed),
                ("analytical_overlay", analytical_overlay),
            )
            if enabled
        ],
        "narration_required": narration_mixed,
        "narration_mixed": narration_mixed,
        "narration_source_path": narration_source_path,
        "narration_source_sha256": (
            compute_sha256(narration_p) if narration_p is not None else None
        ),
        "narration_source_bytes": (
            narration_p.stat().st_size if narration_p is not None else None
        ),
        "narration_duration_s": round(narration_duration_s, 3),
        "analytical_overlay": analytical_overlay,
        "overlay_text": effective_overlay_text,
        "template_variant": variant,
        "template_variant_history": list(template_history or [])[:5],
        "encoder": encoder,
        "output_size_bytes": out_p.stat().st_size,
    }
    meta_p.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    evidence_paths = [str(out_p), str(meta_p)]
    if narration_p is not None:
        evidence_paths.append(str(narration_p))
    return {
        "status": "ok",
        "render_path": str(out_p),
        "metadata_path": str(meta_p),
        "evidence_paths": evidence_paths,
    }


@audited(stage="render")
def run_render(
    input_source_or_action: Union[str, pathlib.Path, Callable[..., Any]],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Audited entrypoint for Stage 8 (render). Supports action callback or stage execution."""
    if callable(input_source_or_action):
        return input_source_or_action(*args, **kwargs)

    subtitles_path = kwargs.pop("subtitles_path", None)
    run_id = kwargs.pop("run_id", None)
    clip_id = kwargs.pop("clip_id", None)
    mode = kwargs.pop("mode", "blur_background")
    blur_sigma = kwargs.pop("blur_sigma", 12.0)
    output_path = kwargs.pop("output_path", None)
    analytical_overlay = bool(kwargs.pop("analytical_overlay", False))
    overlay_text = kwargs.pop("overlay_text", None)
    narration_path = kwargs.pop("narration_path", None)
    tts_narration = bool(kwargs.pop("tts_narration", False))
    require_editorial_transformation = bool(
        kwargs.pop("require_editorial_transformation", False)
    )
    template_variant = kwargs.pop("template_variant", "variant_default")

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

    template_history: list[Dict[str, Any]] = []
    if require_editorial_transformation:
        template_variant = validate_template_variant(template_variant)
        template_history = recent_template_records(
            run_dir.parent,
            current_run_dir=run_dir,
            limit=5,
        )
        assert_variant_not_recent(template_variant, template_history)

    narration_copy: Optional[pathlib.Path] = None
    if narration_path is not None:
        narration_source = pathlib.Path(narration_path).resolve()
        if not narration_source.exists() or not narration_source.is_file():
            raise ProcessingError(f"Narration source does not exist: {narration_source}")
        editorial_dir = run_dir / "artifacts" / "editorial"
        editorial_dir.mkdir(parents=True, exist_ok=True)
        narration_copy = editorial_dir / (
            "narration" + (narration_source.suffix.lower() or ".wav")
        )
        if narration_source != narration_copy.resolve():
            shutil.copy2(narration_source, narration_copy)
        else:
            narration_copy = narration_source

    result = process_vertical_render(
        input_media=in_p,
        output_media=out_media,
        metadata_json=meta_json,
        subtitles_path=subtitles_path,
        mode=mode,
        clip_id=clip_id,
        analytical_overlay=analytical_overlay,
        overlay_text=overlay_text,
        narration_path=narration_copy,
        tts_narration=tts_narration,
        require_editorial_transformation=require_editorial_transformation,
        template_variant=template_variant,
        template_history=template_history,
        run_dir=run_dir,
        blur_sigma=blur_sigma,
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
