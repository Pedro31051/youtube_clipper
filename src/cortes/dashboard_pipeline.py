"""Canonical audited rendering boundary for an approved dashboard clip."""

from __future__ import annotations

import hashlib
import pathlib
import shutil
from typing import Any, Optional, Union

from cortes.audio import run_audio
from cortes.cut import run_cut
from cortes.ingest import run_ingest
from cortes.log import action_span, get_run_dir, run_context
from cortes.render import run_render
from youtube_clipper.downloader import YouTubeDownloader
from youtube_clipper.media_composer import compose_media, validate_media_options
from youtube_clipper.validator import is_youtube_url, validate_time_range


def run_dashboard_clip_pipeline(
    *,
    input_source: str,
    start: float,
    end: float,
    output: Optional[Union[str, pathlib.Path]] = None,
    mode: str = "blur_background",
    blur_sigma: float = 12.0,
    crop_focus: str = "center",
    include_audio: bool = True,
    background_music_path: Optional[Union[str, pathlib.Path]] = None,
    background_music_volume: float = 0.2,
    intro_image_path: Optional[Union[str, pathlib.Path]] = None,
    intro_duration: float = 0.0,
    overlay_text: Optional[str] = None,
    overlay_position: str = "top",
    run_id: Optional[str] = None,
    request_id: Optional[str] = None,
    clip_id: Optional[str] = None,
    **_: Any,
) -> str:
    """Render one selected interval through audited canonical components."""
    start_sec, end_sec = validate_time_range(start, end, None)
    media_options = validate_media_options(
        background_music_path=background_music_path,
        background_music_volume=background_music_volume,
        intro_image_path=intro_image_path,
        intro_duration=intro_duration,
        include_audio=include_audio,
    )
    if crop_focus not in {"left", "center", "right"}:
        raise ValueError("crop_focus must be left, center, or right")
    if overlay_position not in {"top", "bottom"}:
        raise ValueError("overlay_position must be top or bottom")
    if not overlay_text:
        raise ValueError("overlay_text is required")

    actions = [
        {"action": "dashboard.ingest_interval", "stage": "ingest"},
        {"action": "dashboard.audio", "stage": "audio"},
        {"action": "dashboard.render", "stage": "render"},
        {"action": "dashboard.compose", "stage": "transform"},
        {"action": "dashboard.publish", "stage": "report"},
    ]
    with run_context(
        run_id=run_id,
        request_id=request_id,
        actions=actions,
        component="cortes.dashboard_pipeline",
    ) as active_run_id:
        run_dir = get_run_dir(active_run_id)
        ingest_dir = run_dir / "artifacts" / "ingest"
        ingest_dir.mkdir(parents=True, exist_ok=True)

        with action_span(
            "ingest",
            "dashboard.ingest_interval",
            component="cortes.dashboard_pipeline",
            next_action="dashboard.audio",
            next_stage="audio",
        ) as span:
            if is_youtube_url(input_source):
                downloader = YouTubeDownloader()
                downloaded = pathlib.Path(
                    downloader.download_segment(
                        input_source,
                        start_sec,
                        end_sec,
                        ingest_dir,
                    )
                ).resolve()
                interval_path = ingest_dir / "source_interval.mp4"
                if downloaded != interval_path.resolve():
                    shutil.move(downloaded, interval_path)
            else:
                ingested = run_ingest(input_source, run_id=active_run_id)
                interval_path = pathlib.Path(
                    run_cut(
                        ingested["video_path"],
                        start_sec=start_sec,
                        end_sec=end_sec,
                        run_id=active_run_id,
                        clip_id=clip_id,
                    )["cut_path"]
                )
            span.decision = {
                "start_ms": int(round(start_sec * 1000)),
                "end_ms": int(round(end_sec * 1000)),
                "clip_id": clip_id,
            }
            span.set_evidence([interval_path])

        with action_span(
            "audio",
            "dashboard.audio",
            component="cortes.dashboard_pipeline",
            next_action="dashboard.render",
            next_stage="render",
        ) as span:
            if include_audio:
                audio_result = run_audio(interval_path, run_id=active_run_id)
                render_input = pathlib.Path(audio_result["audio_path"])
                span.set_evidence([render_input])
            else:
                render_input = interval_path
                span.decision = {"audio_normalization": "skipped by user"}

        render_dir = run_dir / "artifacts" / (clip_id or "dashboard_clip")
        render_dir.mkdir(parents=True, exist_ok=True)
        vertical_path = render_dir / "vertical.mp4"
        with action_span(
            "render",
            "dashboard.render",
            component="cortes.dashboard_pipeline",
            next_action="dashboard.compose",
            next_stage="transform",
        ) as span:
            rendered = run_render(
                render_input,
                run_id=active_run_id,
                clip_id=clip_id,
                output_path=vertical_path,
                mode=mode,
                blur_sigma=blur_sigma,
                crop_focus=crop_focus,
                include_audio=include_audio,
                analytical_overlay=True,
                overlay_text=overlay_text,
                overlay_position=overlay_position,
                require_editorial_transformation=True,
                template_variant=f"dashboard_{hashlib.sha256(active_run_id.encode()).hexdigest()[:16]}",
            )
            vertical_path = pathlib.Path(rendered["render_path"])
            span.set_evidence([vertical_path])

        final_artifact = render_dir / "short.mp4"
        with action_span(
            "transform",
            "dashboard.compose",
            component="cortes.dashboard_pipeline",
            next_action="dashboard.publish",
            next_stage="report",
        ) as span:
            if media_options.enabled or not include_audio:
                compose_media(
                    vertical_path,
                    final_artifact,
                    background_music_path=media_options.background_music_path,
                    background_music_volume=media_options.background_music_volume,
                    intro_image_path=media_options.intro_image_path,
                    intro_duration=media_options.intro_duration,
                    include_audio=media_options.include_audio,
                )
            else:
                shutil.copy2(vertical_path, final_artifact)
            span.set_evidence([final_artifact])

        with action_span(
            "report",
            "dashboard.publish",
            component="cortes.dashboard_pipeline",
        ) as span:
            published_path = (
                pathlib.Path(output).expanduser().resolve()
                if output is not None
                else final_artifact
            )
            if published_path != final_artifact.resolve():
                published_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(final_artifact, published_path)
            span.decision = {"published_path": str(published_path)}
            span.set_evidence([final_artifact])

        return str(published_path)
