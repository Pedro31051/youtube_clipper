"""Audited ingest stage implementation for YouTube Clipper."""

import json
import pathlib
import shutil
from typing import Any, Callable, Dict, Optional, Union

from cortes.log import audited, compute_sha256, get_run_dir, run_cmd
from youtube_clipper.downloader import YouTubeDownloader
from youtube_clipper.exceptions import ProcessingError, ValidationError
from youtube_clipper.validator import is_youtube_url, validate_input_source


@audited(stage="ingest")
def probe_video_metadata(video_path: pathlib.Path) -> Dict[str, Any]:
    """Probe video file metadata using ffprobe via run_cmd."""
    video_path = pathlib.Path(video_path).resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"Video file for metadata probe does not exist: {video_path}")

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(video_path),
    ]
    res = run_cmd(cmd, stage="ingest")
    if res.returncode != 0:
        raise ProcessingError(f"ffprobe failed on {video_path}: {res.stderr}")

    try:
        data = json.loads(res.stdout)
    except Exception as e:
        raise ProcessingError(f"Failed to parse ffprobe json output: {e}") from e

    format_info = data.get("format", {})
    streams = data.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})

    duration = float(format_info.get("duration", 0.0))
    if duration == 0.0 and video_stream:
        duration = float(video_stream.get("duration", 0.0))

    fps_eval = 30.0
    r_fps = video_stream.get("r_frame_rate", "30/1")
    if "/" in r_fps:
        try:
            num, den = r_fps.split("/")
            if float(den) > 0:
                fps_eval = float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            fps_eval = 30.0
    elif r_fps:
        try:
            fps_eval = float(r_fps)
        except ValueError:
            fps_eval = 30.0

    sha256_hash = compute_sha256(video_path)
    file_size = video_path.stat().st_size

    return {
        "schema_version": "1.0.0",
        "duration": round(duration, 3),
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
        "fps": round(fps_eval, 2),
        "video_codec": video_stream.get("codec_name", "unknown"),
        "audio_codec": audio_stream.get("codec_name", "none"),
        "audio_channels": int(audio_stream.get("channels", 0)),
        "sample_rate": int(audio_stream.get("sample_rate", 0)),
        "file_size": file_size,
        "sha256": sha256_hash,
    }


@audited(stage="ingest")
def run_ingest(
    input_source_or_action: Union[str, pathlib.Path, Callable[..., Any]],
    *args: Any,
    run_id: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    """Execute Stage 1 (ingest) pipeline processing or run action callback.

    Validates source, downloads or copies video to runs/<run_id>/artifacts/ingest/source.mp4,
    probes media metadata, writes metadata.json, and returns evidence paths.
    """
    if callable(input_source_or_action):
        return input_source_or_action(*args, **kwargs)

    clean_input = validate_input_source(str(input_source_or_action))
    run_dir = get_run_dir(run_id)
    ingest_dir = run_dir / "artifacts" / "ingest"
    ingest_dir.mkdir(parents=True, exist_ok=True)

    target_video = ingest_dir / "source.mp4"
    metadata_json = ingest_dir / "metadata.json"

    is_yt = is_youtube_url(clean_input)
    if is_yt:
        downloader = YouTubeDownloader()
        downloaded = downloader.download_segment(
            url=clean_input,
            start=0.0,
            end=0.0,
            output_dir=ingest_dir,
        )
        downloaded_path = pathlib.Path(downloaded)
        if downloaded_path.resolve() != target_video.resolve():
            shutil.move(downloaded_path, target_video)
    else:
        src_path = pathlib.Path(clean_input).resolve()
        if not src_path.exists():
            raise ValidationError(f"Local input file does not exist: {src_path}", field="input")
        shutil.copy2(src_path, target_video)

    metadata = probe_video_metadata(target_video)
    metadata["source_input"] = clean_input
    metadata["is_youtube"] = is_yt
    metadata["video_id"] = target_video.stem

    metadata_json.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return {
        "status": "ok",
        "video_path": str(target_video),
        "metadata_path": str(metadata_json),
        "metadata": metadata,
        "evidence_paths": [str(target_video), str(metadata_json)],
    }
