"""Audited low-resolution preview and poster generation for dashboard clips."""

from __future__ import annotations

import pathlib
import shutil
from typing import Any, Optional

from cortes.ingest import probe_video_metadata
from cortes.log import action_span, get_run_dir, run_cmd, run_context
from cortes.render import build_render_filtergraph
from youtube_clipper.downloader import YouTubeDownloader
from youtube_clipper.exceptions import ProcessingError
from youtube_clipper.validator import is_youtube_url
from youtube_clipper.video_formatter import detect_h264_encoder


def generate_clip_preview(
    *,
    input_source: str,
    start_ms: int,
    end_ms: int,
    edit_plan: dict[str, Any],
    clip_id: str,
    run_id: Optional[str] = None,
    request_id: Optional[str] = None,
    profile: str = "preview",
) -> dict[str, Any]:
    """Render one physical preview or final media file from the edit plan."""
    if start_ms < 0 or end_ms <= start_ms:
        raise ProcessingError("Preview interval is invalid")

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

        layout = edit_plan.get("layout") or {}
        audio = edit_plan.get("audio") or {}
        editorial = edit_plan.get("editorial") or {}
        output = edit_plan.get("output") or {}
        dimensions = {
            "9:16": (360, 640),
            "1:1": (480, 480),
            "16:9": (640, 360),
        }
        width, height = dimensions.get(output.get("aspect_ratio", "9:16"), (360, 640))
        overlay_text = (
            editorial.get("overlay_text")
            if editorial.get("overlay_enabled", bool(editorial.get("overlay_text")))
            else None
        )
        filtergraph = build_render_filtergraph(
            mode=layout.get("mode", "blur_background"),
            width=width,
            height=height,
            sigma=float(layout.get("blur_sigma", 12.0)),
            crop_focus=layout.get("crop_focus", "center"),
            overlay_position=layout.get("overlay_position", "top"),
            analytical_overlay=bool(overlay_text),
            overlay_text=overlay_text,
        )
        include_audio = bool(audio.get("include_source", True))
        if profile not in {"preview", "final"}:
            raise ProcessingError("Preview profile must be preview or final")
        if profile == "final":
            resolution = str(output.get("resolution") or "")
            match = {
                "720x1280": (720, 1280),
                "1080x1920": (1080, 1920),
                "720x720": (720, 720),
                "1920x1080": (1920, 1080),
            }.get(resolution)
            if match:
                width, height = match
            elif output.get("aspect_ratio") == "1:1":
                width, height = 1080, 1080
            elif output.get("aspect_ratio") == "16:9":
                width, height = 1920, 1080
            else:
                width, height = 1080, 1920
            filtergraph = build_render_filtergraph(
                mode=layout.get("mode", "blur_background"),
                width=width,
                height=height,
                sigma=float(layout.get("blur_sigma", 12.0)),
                crop_focus=layout.get("crop_focus", "center"),
                overlay_position=layout.get("overlay_position", "top"),
                analytical_overlay=bool(overlay_text),
                overlay_text=overlay_text,
            )
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
                "medium" if profile == "final" else "veryfast",
                "-crf",
                "23" if profile == "final" else "27",
            ]
        )
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
            command.extend(["-map", "0:v:0", "-map", "0:a?", "-c:a", "aac", "-b:a", "96k"])
            if bool(audio.get("normalize", True)):
                command.extend(["-af", "loudnorm=I=-14:LRA=11:TP=-1.0"])
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
            rendered = run_cmd(command, stage="render")
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
            )
            if poster.returncode != 0 or not poster_path.is_file():
                raise ProcessingError(
                    f"Preview poster generation failed: {poster.stderr}"
                )
            span.set_evidence([poster_path])

        metadata = probe_video_metadata(preview_path)
        return {
            "run_id": active_run_id,
            "preview_path": str(preview_path),
            "media_path": str(preview_path),
            "poster_path": str(poster_path),
            "duration_ms": int(round(float(metadata["duration"]) * 1000)),
            "width": int(metadata["width"]),
            "height": int(metadata["height"]),
            "plan_version": int(edit_plan.get("plan_version", 1)),
        }
