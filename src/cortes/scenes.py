"""Audited scene-detection stage boundary."""

import pathlib
from typing import Any, Callable, Dict, Optional, Union

from cortes.log import audited, get_run_dir
from youtube_clipper.exceptions import ProcessingError
from youtube_clipper.processor import detect_scenes_scenedetect


@audited(stage="scenes")
def run_scenes(
    action_or_video_path: Union[str, pathlib.Path, Callable[..., Any]],
    *args: Any,
    run_id: Optional[str] = None,
    threshold: float = 27.0,
    min_scene_len: float = 0.6,
    **kwargs: Any,
) -> Any:
    """Audited entrypoint for Stage 3 (scenes). Supports action callback or video path execution."""
    if callable(action_or_video_path):
        return action_or_video_path(*args, **kwargs)

    vid_p = pathlib.Path(action_or_video_path).resolve()
    if not vid_p.exists():
        raise ProcessingError(f"Input video for scenes stage does not exist: {vid_p}")

    run_dir = get_run_dir(run_id)
    scenes_dir = run_dir / "artifacts" / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    return detect_scenes_scenedetect(
        video_path=vid_p,
        output_dir=scenes_dir,
        threshold=threshold,
        min_scene_len=min_scene_len,
    )


@audited(stage="scenes")
def detect_scenes_stage(
    video_path: Union[str, pathlib.Path],
    run_id: Optional[str] = None,
    threshold: float = 27.0,
    min_scene_len: float = 0.6,
) -> Dict[str, Any]:
    """Execute Stage 3 (scenes) pipeline processing."""
    vid_p = pathlib.Path(video_path).resolve()
    if not vid_p.exists():
        raise ProcessingError(f"Input video for scenes stage does not exist: {vid_p}")

    run_dir = get_run_dir(run_id)
    scenes_dir = run_dir / "artifacts" / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    return detect_scenes_scenedetect(
        video_path=vid_p,
        output_dir=scenes_dir,
        threshold=threshold,
        min_scene_len=min_scene_len,
    )
