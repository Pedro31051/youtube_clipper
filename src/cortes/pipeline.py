"""End-to-end 9-stage pipeline orchestrator for YouTube Clipper."""

import pathlib
from typing import Any, Dict, Optional, Union

from cortes.audio import run_audio
from cortes.cut import run_cut
from cortes.editorial import build_clip_id
from cortes.ingest import run_ingest
from cortes.log import (
    action_span,
    emit_skipped,
    get_run_dir,
    run_context,
)
from cortes.render import run_render
from cortes.report import run_report
from cortes.scenes import detect_scenes_stage
from cortes.select import select_clip_stage
from cortes.subtitles import run_subtitles
from cortes.transcribe import run_transcribe


def run_full_pipeline(
    input_source: Union[str, pathlib.Path],
    run_id: Optional[str] = None,
    whisper_model: str = "small",
    device: str = "cuda",
    vertical_mode: str = "blur_background",
    *,
    request_id: Optional[str] = None,
    language: Optional[str] = None,
    scene_threshold: float = 27.0,
    min_scene_len: float = 0.6,
    subtitle_font_name: str = "Roboto",
    subtitle_font_size: int = 80,
    subtitle_margin_v: int = 400,
    blur_sigma: float = 12.0,
    analytical_overlay: bool = False,
    overlay_text: Optional[str] = None,
    narration_path: Optional[Union[str, pathlib.Path]] = None,
    template_variant: str = "variant_default",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Execute full 9-stage pipeline sequentially (Stages 1 through 9)."""
    plan = [
        {"action": "pipeline.ingest", "stage": "ingest"},
        {"action": "pipeline.transcribe", "stage": "transcribe", "depends_on": "pipeline.ingest"},
        {"action": "pipeline.scenes", "stage": "scenes", "depends_on": "pipeline.ingest"},
        {"action": "pipeline.select", "stage": "select", "depends_on": "pipeline.transcribe,pipeline.scenes"},
        {"action": "pipeline.cut", "stage": "cut", "depends_on": "pipeline.select"},
        {"action": "pipeline.subtitles", "stage": "subtitles", "depends_on": "pipeline.select"},
        {"action": "pipeline.audio", "stage": "audio", "depends_on": "pipeline.cut"},
        {"action": "pipeline.render", "stage": "render", "depends_on": "pipeline.audio,pipeline.subtitles"},
        {"action": "pipeline.report", "stage": "report", "depends_on": "pipeline.render"},
    ]
    completed = set()

    with run_context(
        run_id=run_id,
        request_id=request_id,
        actions=plan,
        component="cortes.pipeline",
    ) as active_run_id:
        try:
            with action_span("ingest", "pipeline.ingest", next_action="pipeline.transcribe", next_stage="transcribe"):
                ingest_res = run_ingest(input_source, run_id=active_run_id)
                video_path = ingest_res["video_path"]
            completed.add("pipeline.ingest")

            with action_span("transcribe", "pipeline.transcribe", next_action="pipeline.scenes", next_stage="scenes"):
                transcribe_res = run_transcribe(
                    video_path,
                    run_id=active_run_id,
                    model_size=whisper_model,
                    device=device,
                    language=language,
                )
                transcript_path = transcribe_res["transcript_path"]
            completed.add("pipeline.transcribe")

            with action_span("scenes", "pipeline.scenes", next_action="pipeline.select", next_stage="select"):
                scenes_res = detect_scenes_stage(
                    video_path,
                    run_id=active_run_id,
                    threshold=scene_threshold,
                    min_scene_len=min_scene_len,
                )
                scenes_path = scenes_res["scenes_path"]
            completed.add("pipeline.scenes")

            with action_span("select", "pipeline.select", next_action="pipeline.cut", next_stage="cut"):
                select_res = select_clip_stage(
                    transcript_path, scenes_path, run_id=active_run_id
                )
                selection_path = select_res["selection_path"]
                selection_bytes = pathlib.Path(selection_path).read_bytes()
                clip_id = build_clip_id(selection_bytes, template_variant)
            completed.add("pipeline.select")

            with action_span("cut", "pipeline.cut", clip_id=clip_id, next_action="pipeline.subtitles", next_stage="subtitles"):
                cut_res = run_cut(
                    video_path,
                    selection_path_or_data=selection_path,
                    run_id=active_run_id,
                    clip_id=clip_id,
                )
                cut_path = cut_res.get("cut_path") or cut_res.get("clip_path")
            completed.add("pipeline.cut")

            with action_span("subtitles", "pipeline.subtitles", clip_id=clip_id, next_action="pipeline.audio", next_stage="audio"):
                sub_res = run_subtitles(
                    transcript_path,
                    selection_path_or_data=selection_path,
                    run_id=active_run_id,
                    clip_id=clip_id,
                    font_name=subtitle_font_name,
                    font_size=subtitle_font_size,
                    margin_v=subtitle_margin_v,
                )
                subtitles_path = sub_res["subtitles_path"]
            completed.add("pipeline.subtitles")

            with action_span("audio", "pipeline.audio", clip_id=clip_id, next_action="pipeline.render", next_stage="render"):
                audio_res = run_audio(cut_path, run_id=active_run_id)
                audio_path = audio_res["audio_path"]
            completed.add("pipeline.audio")

            with action_span("render", "pipeline.render", clip_id=clip_id, next_action="pipeline.report", next_stage="report"):
                render_res = run_render(
                    audio_path,
                    subtitles_path=subtitles_path,
                    run_id=active_run_id,
                    clip_id=clip_id,
                    mode=vertical_mode,
                    blur_sigma=blur_sigma,
                    analytical_overlay=analytical_overlay,
                    overlay_text=overlay_text,
                    narration_path=narration_path,
                    tts_narration=kwargs.get("tts_narration", False),
                    require_editorial_transformation=kwargs.get(
                        "require_editorial_transformation",
                        bool(
                            analytical_overlay
                            or narration_path
                            or kwargs.get("tts_narration", False)
                        ),
                    ),
                    template_variant=template_variant,
                )
                render_path = render_res["render_path"]
            completed.add("pipeline.render")

            with action_span("report", "pipeline.report"):
                run_dir = get_run_dir(active_run_id)
                report_res = run_report(run_dir_or_action=run_dir, run_id=active_run_id)
                report_path = report_res["report_path"]
            completed.add("pipeline.report")
        except BaseException as exc:
            remaining = [item for item in plan if item["action"] not in completed]
            # The failing action already has a failed terminal event; only actions
            # after it are explicitly marked as not started.
            for item in remaining[1:]:
                emit_skipped(
                    item["stage"],
                    item["action"],
                    f"dependency did not complete because {type(exc).__name__}: {exc}",
                    component="cortes.pipeline",
                )
            raise

        return {
            "status": "ok",
            "run_id": active_run_id,
            "clip_id": clip_id,
            "video_path": video_path,
            "transcript_path": transcript_path,
            "scenes_path": scenes_path,
            "selection_path": selection_path,
            "cut_path": cut_path,
            "subtitles_path": subtitles_path,
            "audio_path": audio_path,
            "render_path": render_path,
            "report_path": report_path,
        }
