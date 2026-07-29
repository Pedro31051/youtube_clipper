"""Audited low-resolution preview and poster generation for dashboard clips."""

from __future__ import annotations

import pathlib
import shutil
import threading
from typing import Any, Optional

from cortes.ingest import probe_video_metadata
from cortes.log import action_span, get_run_dir, run_cmd, run_context
from cortes.panel_audio import measure_loudnorm_filter
from cortes.render import build_render_filtergraph
from youtube_clipper.downloader import YouTubeDownloader
from youtube_clipper.edit_plan import RenderRequest, compile_edit_plan
from youtube_clipper.exceptions import ProcessingError
from youtube_clipper.validator import is_youtube_url
from youtube_clipper.video_formatter import detect_h264_encoder


class PreviewCancelledError(ProcessingError):
    """The job controller cancelled an active physical media process."""


def generate_clip_preview(
    *,
    input_source: str,
    start_ms: int,
    end_ms: int,
    edit_plan: Optional[dict[str, Any]] = None,
    clip_id: str,
    run_id: Optional[str] = None,
    request_id: Optional[str] = None,
    profile: str = "preview",
    cancel_event: Optional[threading.Event] = None,
    render_request: Optional[RenderRequest | dict[str, Any]] = None,
) -> dict[str, Any]:
    """Render one physical preview or final media file from the edit plan."""
    if profile not in {"preview", "final"}:
        raise ProcessingError("Render profile must be preview or final")
    if render_request is None:
        if edit_plan is None:
            raise ProcessingError("An edit plan or compiled render request is required")
        request = compile_edit_plan(
            edit_plan,
            profile=profile,
            clip_id=clip_id,
            start_ms=start_ms,
            end_ms=end_ms,
        )
    else:
        request = RenderRequest.model_validate(render_request)
    if request.profile != profile:
        raise ProcessingError("Compiled render request profile does not match the job")
    if request.clip_id != clip_id:
        raise ProcessingError("Compiled render request belongs to another clip")
    if request.start_ms != start_ms or request.end_ms != end_ms:
        raise ProcessingError("Compiled render request interval does not match the clip")
    start_ms = request.start_ms
    end_ms = request.end_ms

    actions = [
        {"action": "preview.resolve_source", "stage": "ingest"},
        {"action": "preview.render", "stage": "render"},
        {"action": "preview.poster", "stage": "report"},
    ]
    with run_context(
        run_id=run_id,
        request_id=request_id,
        actions=actions,
        component="cortes.preview",
    ) as active_run_id:
        run_dir = get_run_dir(active_run_id)
        artifact_dir = run_dir / "artifacts" / clip_id
        artifact_dir.mkdir(parents=True, exist_ok=True)

        source_start = start_ms / 1000.0
        duration = (end_ms - start_ms) / 1000.0
        with action_span(
            "ingest",
            "preview.resolve_source",
            component="cortes.preview",
            next_action="preview.render",
            next_stage="render",
        ) as span:
            if is_youtube_url(input_source):
                downloaded = pathlib.Path(
                    YouTubeDownloader().download_segment(
                        input_source,
                        source_start,
                        end_ms / 1000.0,
                        artifact_dir,
                    )
                ).resolve()
                source_path = artifact_dir / "source_interval.mp4"
                if downloaded != source_path.resolve():
                    shutil.move(downloaded, source_path)
                source_start = 0.0
            else:
                source_path = pathlib.Path(input_source).expanduser().resolve()
                if not source_path.is_file():
                    raise ProcessingError(
                        f"Preview source does not exist: {source_path}"
                    )
            span.decision = {
                "clip_id": clip_id,
                "start_ms": start_ms,
                "end_ms": end_ms,
            }
            if source_path.is_relative_to(run_dir.resolve()):
                span.set_evidence([source_path])

        width, height = request.width, request.height
        filtergraph = build_render_filtergraph(
            mode=request.layout_mode,
            width=width,
            height=height,
            sigma=request.blur_sigma,
            crop_focus=request.crop_focus,
            overlay_position=request.overlay_position,
            analytical_overlay=bool(request.overlay_text),
            overlay_text=request.overlay_text,
        )
        include_audio = request.include_source_audio
        preview_path = artifact_dir / (
            "render_final.mp4" if profile == "final" else "preview.mp4"
        )
        encoder = detect_h264_encoder()
        video_args = (
            ["-c:v", "h264_nvenc", "-preset", "p4"]
            if encoder == "h264_nvenc"
            else [
                "-c:v",
                "libx264",
                "-preset",
                request.video_preset,
                "-crf",
                str(request.video_crf),
            ]
        )

        normalization_filter: Optional[str] = None
        normalization_mode = "disabled"
        if request.normalize_audio:
            audio_probe = run_cmd(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "stream=index",
                    "-of",
                    "csv=p=0",
                    str(source_path),
                ],
                stage="render",
                cancel_event=cancel_event,
            )
            if cancel_event is not None and cancel_event.is_set():
                raise PreviewCancelledError("Audio probe cancelled by the user")
            if audio_probe.returncode == 0 and audio_probe.stdout.strip():
                if profile == "final":
                    normalization_filter = measure_loudnorm_filter(
                        source_path,
                        start_seconds=source_start,
                        duration_seconds=duration,
                        cancel_event=cancel_event,
                    )
                    normalization_mode = "two_pass"
                else:
                    normalization_filter = "loudnorm=I=-14:LRA=11:TP=-1.0"
                    normalization_mode = "single_pass"

        command = [
            "ffmpeg",
            "-y",
            "-nostdin",
            "-hide_banner",
            "-ss",
            f"{source_start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(source_path),
            "-vf",
            filtergraph,
            *video_args,
            "-pix_fmt",
            "yuv420p",
        ]
        if include_audio:
            command.extend(
                [
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a?",
                    "-c:a",
                    "aac",
                    "-b:a",
                    request.audio_bitrate,
                ]
            )
            if normalization_filter is not None:
                command.extend(["-af", normalization_filter])
        else:
            command.append("-an")
        command.extend(["-movflags", "+faststart", str(preview_path)])

        with action_span(
            "render",
            "preview.render",
            component="cortes.preview",
            next_action="preview.poster",
            next_stage="report",
        ) as span:
            rendered = run_cmd(
                command,
                stage="render",
                cancel_event=cancel_event,
            )
            if cancel_event is not None and cancel_event.is_set():
                preview_path.unlink(missing_ok=True)
                raise PreviewCancelledError("Render cancelled by the user")
            if rendered.returncode != 0 or not preview_path.is_file():
                raise ProcessingError(
                    f"Preview rendering failed: {rendered.stderr}"
                )
            span.set_evidence([preview_path])

        poster_path = artifact_dir / "poster.jpg"
        with action_span(
            "report",
            "preview.poster",
            component="cortes.preview",
        ) as span:
            poster = run_cmd(
                [
                    "ffmpeg",
                    "-y",
                    "-nostdin",
                    "-hide_banner",
                    "-ss",
                    "0.100",
                    "-i",
                    str(preview_path),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "3",
                    str(poster_path),
                ],
                stage="report",
                cancel_event=cancel_event,
            )
            if cancel_event is not None and cancel_event.is_set():
                poster_path.unlink(missing_ok=True)
                preview_path.unlink(missing_ok=True)
                raise PreviewCancelledError("Render cancelled by the user")
            if poster.returncode != 0 or not poster_path.is_file():
                raise ProcessingError(
                    f"Preview poster generation failed: {poster.stderr}"
                )
            span.set_evidence([poster_path])

        probed = probe_video_metadata(preview_path)
        render_metadata = {
            "profile": profile,
            "plan_version": request.plan_version,
            "applied_features": dict(request.applied_features),
            "normalization_mode": normalization_mode,
            "encoder": encoder,
            "aspect_ratio": request.aspect_ratio,
            "requested_resolution": request.requested_resolution,
            "actual_resolution": f"{probed['width']}x{probed['height']}",
            "layout_mode": request.layout_mode,
        }
        return {
            "run_id": active_run_id,
            "preview_path": str(preview_path),
            "media_path": str(preview_path),
            "poster_path": str(poster_path),
            "duration_ms": int(round(float(probed["duration"]) * 1000)),
            "width": int(probed["width"]),
            "height": int(probed["height"]),
            "plan_version": request.plan_version,
            "applied_features": dict(request.applied_features),
            "metadata": render_metadata,
        }
