"""Audited media-cut stage implementation for YouTube Clipper."""

import json
import pathlib
from typing import Any, Callable, Dict, Optional, Union

from cortes.log import audited, get_run_dir, run_cmd
from youtube_clipper.exceptions import ProcessingError
from youtube_clipper.media_validation import validate_media_output


@audited(stage="cut")
def cut_clip_stage(
    input_video_path: Union[str, pathlib.Path],
    selection_path_or_data: Optional[Union[str, pathlib.Path, Dict[str, Any]]] = None,
    start_sec: Optional[float] = None,
    end_sec: Optional[float] = None,
    run_id: Optional[str] = None,
    clip_id: Optional[str] = None,
    output_path: Optional[Union[str, pathlib.Path]] = None,
    fast_copy: bool = True,
) -> Dict[str, Any]:
    """Execute Stage 5 (cut) media clipping and validate generated clip."""
    vid_p = pathlib.Path(input_video_path).resolve()
    if not vid_p.exists():
        raise ProcessingError(f"Input video for cut stage does not exist: {vid_p}")

    # Measure the source independently so selection bounds can be re-verified.
    source_probe = run_cmd(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(vid_p),
        ],
        stage="cut",
    )
    try:
        source_duration_sec = float(source_probe.stdout.strip())
    except (TypeError, ValueError):
        source_duration_sec = 0.0
    if source_probe.returncode != 0 or source_duration_sec <= 0.0:
        raise ProcessingError(
            f"Unable to measure positive source duration: {source_probe.stderr}"
        )

    # Determine start and end timestamps
    if start_sec is not None and end_sec is not None:
        s_sec = float(start_sec)
        e_sec = float(end_sec)
    elif selection_path_or_data is not None:
        if isinstance(selection_path_or_data, (str, pathlib.Path)):
            sel_p = pathlib.Path(selection_path_or_data).resolve()
            if not sel_p.exists():
                raise ProcessingError(f"Selection artifact does not exist: {sel_p}")
            sel_data = json.loads(sel_p.read_text(encoding="utf-8"))
        else:
            sel_data = selection_path_or_data

        s_sec = float(sel_data["start_ms"]) / 1000.0
        e_sec = float(sel_data["end_ms"]) / 1000.0
    else:
        # Fallback to selection.json in run_dir
        run_dir = get_run_dir(run_id)
        sel_p = run_dir / "artifacts" / "select" / "selection.json"
        if not sel_p.exists():
            raise ProcessingError(f"No selection parameters or selection.json found: {sel_p}")
        sel_data = json.loads(sel_p.read_text(encoding="utf-8"))
        s_sec = float(sel_data["start_ms"]) / 1000.0
        e_sec = float(sel_data["end_ms"]) / 1000.0

    if s_sec < 0 or e_sec <= s_sec:
        raise ProcessingError(f"Invalid clip timestamp range: start={s_sec}, end={e_sec}")
    if e_sec > source_duration_sec + 0.001:
        raise ProcessingError(
            f"Clip end {e_sec}s exceeds source duration {source_duration_sec}s"
        )

    dur_sec = round(e_sec - s_sec, 3)

    if output_path:
        out_p = pathlib.Path(output_path).resolve()
    else:
        run_dir = get_run_dir(run_id)
        out_dir = run_dir / "artifacts" / "cut"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_p = out_dir / "clip.mp4"

    out_p.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(s_sec),
        "-i",
        str(vid_p),
        "-t",
        str(dur_sec),
    ]

    if fast_copy:
        cmd.extend(["-c", "copy", "-avoid_negative_ts", "make_zero"])
    else:
        cmd.extend(["-c:v", "libx264", "-c:a", "aac", "-avoid_negative_ts", "make_zero"])

    cmd.append(str(out_p))

    res = run_cmd(cmd, stage="cut")
    if res.returncode != 0 or not out_p.exists():
        raise ProcessingError(f"FFmpeg cut command failed: {res.stderr}")

    measured = validate_media_output(
        out_p,
        expected_duration=dur_sec,
        duration_tolerance=1.5 if fast_copy else 0.5,
        stage="cut",
        command_runner=run_cmd,
    )
    probed_dur = float(measured["duration"])

    metadata_path = out_p.parent / "cut_metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "clip_id": clip_id,
                "source_duration_ms": int(round(source_duration_sec * 1000)),
                "start_ms": int(round(s_sec * 1000)),
                "end_ms": int(round(e_sec * 1000)),
                "duration_ms": int(round(probed_dur * 1000)),
                "requested_duration_ms": int(round(dur_sec * 1000)),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "status": "ok",
        "cut_path": str(out_p),
        "clip_path": str(out_p),
        "metadata_path": str(metadata_path),
        "evidence_paths": [str(out_p), str(metadata_path)],
        "start_sec": s_sec,
        "end_sec": e_sec,
        "duration_sec": dur_sec,
        "measured_duration_sec": probed_dur,
    }


@audited(stage="cut")
def run_cut(
    action_or_input: Union[str, pathlib.Path, Callable[..., Any]],
    *args: Any,
    selection_path_or_data: Optional[Union[str, pathlib.Path, Dict[str, Any]]] = None,
    start_sec: Optional[float] = None,
    end_sec: Optional[float] = None,
    run_id: Optional[str] = None,
    clip_id: Optional[str] = None,
    output_path: Optional[Union[str, pathlib.Path]] = None,
    fast_copy: bool = True,
    **kwargs: Any,
) -> Any:
    """Audited entrypoint for Stage 5 (cut). Supports action callback or stage execution."""
    if callable(action_or_input):
        callback_kwargs = dict(kwargs)
        if output_path is not None:
            callback_kwargs["output_path"] = output_path
        return action_or_input(*args, **callback_kwargs)

    return cut_clip_stage(
        input_video_path=action_or_input,
        selection_path_or_data=selection_path_or_data,
        start_sec=start_sec,
        end_sec=end_sec,
        run_id=run_id,
        clip_id=clip_id,
        output_path=output_path,
        fast_copy=fast_copy,
    )
