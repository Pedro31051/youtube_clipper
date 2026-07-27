"""End-to-end 9-stage pipeline orchestrator for YouTube Clipper."""

import pathlib
from typing import Any, Dict, Optional, Union

from cortes.audio import run_audio
from cortes.cut import run_cut
from cortes.editorial import build_clip_id
from cortes.ingest import run_ingest
from cortes.log import get_run_dir, set_run_id
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
    **kwargs: Any,
) -> Dict[str, Any]:
    """Execute full 9-stage pipeline sequentially (Stages 1 through 9)."""
    if run_id:
        set_run_id(run_id)

    # Stage 1: Ingest
    ingest_res = run_ingest(input_source, run_id=run_id)
    video_path = ingest_res["video_path"]

    # Stage 2: Transcribe
    transcribe_res = run_transcribe(video_path, run_id=run_id, model_size=whisper_model, device=device)
    transcript_path = transcribe_res["transcript_path"]

    # Stage 3: Scenes
    scenes_res = detect_scenes_stage(video_path, run_id=run_id)
    scenes_path = scenes_res["scenes_path"]

    # Stage 4: Select
    select_res = select_clip_stage(transcript_path, scenes_path, run_id=run_id)
    selection_path = select_res["selection_path"]
    selection_bytes = pathlib.Path(selection_path).read_bytes()
    template_variant = kwargs.get("template_variant", "variant_default")
    clip_id = build_clip_id(selection_bytes, template_variant)

    # Stage 5: Cut
    cut_res = run_cut(
        video_path,
        selection_path_or_data=selection_path,
        run_id=run_id,
        clip_id=clip_id,
    )
    cut_path = cut_res.get("cut_path") or cut_res.get("clip_path")

    # Stage 6: Subtitles
    sub_res = run_subtitles(
        transcript_path,
        selection_path_or_data=selection_path,
        run_id=run_id,
        clip_id=clip_id,
    )
    subtitles_path = sub_res["subtitles_path"]

    # Stage 7: Audio
    audio_res = run_audio(cut_path, run_id=run_id)
    audio_path = audio_res["audio_path"]

    # Stage 8: Render
    render_res = run_render(
        audio_path,
        subtitles_path=subtitles_path,
        run_id=run_id,
        clip_id=clip_id,
        mode=vertical_mode,
        analytical_overlay=kwargs.get("analytical_overlay", False),
        overlay_text=kwargs.get("overlay_text"),
        narration_path=kwargs.get("narration_path"),
        tts_narration=kwargs.get("tts_narration", False),
        require_editorial_transformation=kwargs.get(
            "require_editorial_transformation",
            bool(
                kwargs.get("analytical_overlay", False)
                or kwargs.get("narration_path")
                or kwargs.get("tts_narration", False)
            ),
        ),
        template_variant=template_variant,
    )
    render_path = render_res["render_path"]

    # Stage 9: Report
    run_dir = get_run_dir(run_id)
    report_res = run_report(run_dir_or_action=run_dir, run_id=run_id)
    report_path = report_res["report_path"]

    return {
        "status": "ok",
        "run_id": run_id,
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
