"""Audited subtitle stage implementation for YouTube Clipper."""

import json
import pathlib
from typing import Any, Callable, Dict, List, Optional, Union

import pysubs2
from cortes.log import audited, get_run_dir
from youtube_clipper.exceptions import ProcessingError


@audited(stage="subtitles")
def safe_color(r: int, g: int, b: int, a: int = 0) -> pysubs2.Color:
    """Create pysubs2.Color ensuring all channel values are strictly masked in 0..255 range."""
    return pysubs2.Color(r & 0xFF, g & 0xFF, b & 0xFF, a & 0xFF)



@audited(stage="subtitles")
def generate_subtitles_stage(
    transcript_path_or_data: Union[str, pathlib.Path, Dict[str, Any]],
    selection_path_or_data: Optional[Union[str, pathlib.Path, Dict[str, Any]]] = None,
    run_id: Optional[str] = None,
    clip_id: Optional[str] = None,
    output_path: Optional[Union[str, pathlib.Path]] = None,
    font_name: str = "Roboto",
    font_size: int = 80,
    margin_v: int = 400,
) -> Dict[str, Any]:
    """Execute Stage 6 (subtitles) generating word-level ASS subtitles via pysubs2."""
    if isinstance(transcript_path_or_data, (str, pathlib.Path)):
        t_path = pathlib.Path(transcript_path_or_data).resolve()
        if not t_path.exists():
            raise ProcessingError(f"Transcript artifact missing for subtitles stage: {t_path}")
        transcript_data = json.loads(t_path.read_text(encoding="utf-8"))
    else:
        transcript_data = transcript_path_or_data

    if selection_path_or_data is not None:
        if isinstance(selection_path_or_data, (str, pathlib.Path)):
            s_path = pathlib.Path(selection_path_or_data).resolve()
            if not s_path.exists():
                raise ProcessingError(f"Selection artifact missing for subtitles stage: {s_path}")
            selection_data = json.loads(s_path.read_text(encoding="utf-8"))
        else:
            selection_data = selection_path_or_data
    else:
        run_dir = get_run_dir(run_id)
        s_path = run_dir / "artifacts" / "select" / "selection.json"
        if not s_path.exists():
            raise ProcessingError(f"Selection artifact missing for subtitles stage: {s_path}")
        selection_data = json.loads(s_path.read_text(encoding="utf-8"))

    clip_start_ms = int(selection_data["start_ms"])
    clip_end_ms = int(selection_data["end_ms"])
    clip_duration_ms = clip_end_ms - clip_start_ms

    raw_words: List[Dict[str, Any]] = []
    if "words" in transcript_data and transcript_data["words"]:
        raw_words = transcript_data["words"]
    elif "segments" in transcript_data:
        for seg in transcript_data.get("segments", []):
            if "words" in seg and seg["words"]:
                raw_words.extend(seg["words"])

    words_in_clip: List[Dict[str, Any]] = []
    for w in raw_words:
        raw_start_ms = w.get("start_ms")
        raw_end_ms = w.get("end_ms")
        w_start = (
            int(raw_start_ms)
            if raw_start_ms is not None
            else int(round(float(w["start"]) * 1000))
        )
        w_end = (
            int(raw_end_ms)
            if raw_end_ms is not None
            else int(round(float(w["end"]) * 1000))
        )
        word_str = w.get("word", "").strip()

        if w_end > clip_start_ms and w_start < clip_end_ms and word_str:
            rel_start = max(0, w_start - clip_start_ms)
            rel_end = min(clip_duration_ms, w_end - clip_start_ms)
            if rel_end > rel_start:
                words_in_clip.append({
                    "word": word_str,
                    "rel_start_ms": rel_start,
                    "rel_end_ms": rel_end,
                })

    subs = pysubs2.SSAFile()
    subs.info["PlayResX"] = "1080"
    subs.info["PlayResY"] = "1920"

    style = pysubs2.SSAStyle(
        fontname=font_name,
        fontsize=font_size,
        primarycolor=safe_color(255, 255, 255, 0),
        secondarycolor=safe_color(255, 255, 0, 0),
        outlinecolor=safe_color(0, 0, 0, 0),
        backcolor=safe_color(0, 0, 0, 128),
        bold=True,
        outline=4.0,
        shadow=2.0,
        alignment=pysubs2.Alignment.BOTTOM_CENTER,
        marginl=50,
        marginr=50,
        marginv=margin_v,
    )
    subs.styles["Default"] = style

    for w_obj in words_in_clip:
        event = pysubs2.SSAEvent(
            start=w_obj["rel_start_ms"],
            end=w_obj["rel_end_ms"],
            text=w_obj["word"],
            style="Default",
        )
        subs.events.append(event)

    if output_path:
        out_p = pathlib.Path(output_path).resolve()
    else:
        run_dir = get_run_dir(run_id)
        out_dir = run_dir / "artifacts" / "subtitles"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_p = out_dir / "subtitles.ass"

    out_p.parent.mkdir(parents=True, exist_ok=True)
    subs.save(str(out_p), encoding="utf-8")

    mapping_path = out_p.parent / "subtitle_mapping.json"
    mapping_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "clip_id": clip_id,
                "selection": {
                    "start_ms": clip_start_ms,
                    "end_ms": clip_end_ms,
                },
                "source_words": raw_words,
                "events": [
                    {
                        "word": event.text,
                        "start_ms": int(event.start),
                        "end_ms": int(event.end),
                    }
                    for event in subs.events
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "status": "ok",
        "subtitles_path": str(out_p),
        "mapping_path": str(mapping_path),
        "evidence_paths": [str(out_p), str(mapping_path)],
        "total_events": len(subs.events),
        "clip_start_ms": clip_start_ms,
        "clip_end_ms": clip_end_ms,
    }


@audited(stage="subtitles")
def run_subtitles(
    action_or_transcript: Union[str, pathlib.Path, Dict[str, Any], Callable[..., Any]],
    *args: Any,
    selection_path_or_data: Optional[Union[str, pathlib.Path, Dict[str, Any]]] = None,
    run_id: Optional[str] = None,
    clip_id: Optional[str] = None,
    output_path: Optional[Union[str, pathlib.Path]] = None,
    font_name: str = "Roboto",
    font_size: int = 80,
    margin_v: int = 400,
    **kwargs: Any,
) -> Any:
    """Audited entrypoint for Stage 6 (subtitles). Supports action callback or stage execution."""
    if callable(action_or_transcript):
        return action_or_transcript(*args, **kwargs)

    return generate_subtitles_stage(
        transcript_path_or_data=action_or_transcript,
        selection_path_or_data=selection_path_or_data,
        run_id=run_id,
        clip_id=clip_id,
        output_path=output_path,
        font_name=font_name,
        font_size=font_size,
        margin_v=margin_v,
    )
