"""Audited clip-selection stage boundary."""

import json
import pathlib
from typing import Any, Callable, Dict, Optional, Union

from cortes.log import audited, get_run_dir
from youtube_clipper.analyzer import SpeechDensityAnalyzer
from youtube_clipper.exceptions import ProcessingError


@audited(stage="select")
def run_select(
    action_or_transcript_path: Union[str, pathlib.Path, Callable[..., Any]],
    *args: Any,
    scenes_path: Optional[Union[str, pathlib.Path]] = None,
    run_id: Optional[str] = None,
    output_path: Optional[Union[str, pathlib.Path]] = None,
    **kwargs: Any,
) -> Any:
    """Audited entrypoint for Stage 4 (select). Supports action callback or stage execution."""
    if callable(action_or_transcript_path):
        return action_or_transcript_path(*args, **kwargs)

    return select_clip_stage(
        transcript_path=action_or_transcript_path,
        scenes_path=scenes_path,
        run_id=run_id,
        output_path=output_path,
    )


@audited(stage="select")
def select_clip_stage(
    transcript_path: Union[str, pathlib.Path],
    scenes_path: Union[str, pathlib.Path],
    run_id: Optional[str] = None,
    output_path: Optional[Union[str, pathlib.Path]] = None,
) -> Dict[str, Any]:
    """Execute Stage 4 (select) clip selection and write selection.json artifact."""
    t_path = pathlib.Path(transcript_path).resolve()
    s_path = pathlib.Path(scenes_path).resolve()

    if not t_path.exists():
        raise ProcessingError(f"Transcript artifact for selection does not exist: {t_path}")
    if not s_path.exists():
        raise ProcessingError(f"Scenes artifact for selection does not exist: {s_path}")

    with open(t_path, "r", encoding="utf-8") as f:
        transcript_data = json.load(f)

    with open(s_path, "r", encoding="utf-8") as f:
        scenes_data = json.load(f)

    selection = SpeechDensityAnalyzer.select_best_clip(transcript_data, scenes_data)

    if output_path:
        out_p = pathlib.Path(output_path).resolve()
    else:
        run_dir = get_run_dir(run_id)
        out_dir = run_dir / "artifacts" / "select"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_p = out_dir / "selection.json"

    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(
        json.dumps(selection, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return {
        "status": "ok",
        "selection_path": str(out_p),
        "evidence_paths": [str(out_p)],
        "selection": selection,
    }
