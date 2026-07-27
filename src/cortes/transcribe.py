"""Audited transcription stage implementation for YouTube Clipper."""

import json
import os
import pathlib
import sys
from typing import Any, Callable, Dict, Optional, Union

from cortes.log import audited, get_run_dir, run_cmd
from youtube_clipper.exceptions import ProcessingError


@audited(stage="transcribe")
def extract_audio_wav(
    video_path: pathlib.Path,
    output_wav: pathlib.Path,
) -> pathlib.Path:
    """Extract 16kHz mono PCM WAV audio using ffmpeg via run_cmd."""
    video_path = pathlib.Path(video_path).resolve()
    output_wav = pathlib.Path(output_wav).resolve()
    output_wav.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output_wav),
    ]
    res = run_cmd(cmd, stage="transcribe")
    if res.returncode != 0 or not output_wav.exists():
        raise ProcessingError(f"Audio extraction failed for {video_path}: {res.stderr}")
    return output_wav


@audited(stage="transcribe")
def transcribe_with_faster_whisper(
    audio_wav: pathlib.Path,
    model_size: str = "small",
    device: str = "cuda",
    compute_type: str = "float16",
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """Transcribe through the audited worker process using the requested device.

    CUDA failures are intentionally not hidden by an implicit CPU fallback:
    T2 requires positive proof that the production transcription used the GPU.
    Callers that explicitly request ``device="cpu"`` remain supported for
    lightweight and portability tests.
    """
    audio_wav = pathlib.Path(audio_wav).resolve()
    if not audio_wav.exists():
        raise FileNotFoundError(f"Audio file for transcription does not exist: {audio_wav}")
    effective_compute_type = compute_type if device == "cuda" else "int8"
    command = [
        sys.executable,
        "-m",
        "cortes.whisper_worker",
        "--audio",
        str(audio_wav),
        "--model",
        model_size,
        "--device",
        device,
        "--compute-type",
        effective_compute_type,
    ]
    if language:
        command.extend(["--language", language])
    worker_env = None
    if device == "cuda":
        nvidia_root = (
            pathlib.Path(sys.prefix)
            / "lib"
            / f"python{sys.version_info.major}.{sys.version_info.minor}"
            / "site-packages"
            / "nvidia"
        )
        cuda_library_dirs = [
            nvidia_root / "cublas" / "lib",
            nvidia_root / "cudnn" / "lib",
            nvidia_root / "cuda_nvrtc" / "lib",
        ]
        worker_env = os.environ.copy()
        existing_library_path = worker_env.get("LD_LIBRARY_PATH", "")
        worker_env["LD_LIBRARY_PATH"] = ":".join(
            [str(path) for path in cuda_library_dirs if path.exists()]
            + ([existing_library_path] if existing_library_path else [])
        )
    result = run_cmd(command, stage="transcribe", env=worker_env)
    if result.returncode != 0:
        raise ProcessingError(
            f"Whisper {device} transcription failed: {result.stderr}"
        )
    try:
        transcript = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProcessingError(
            f"Whisper worker returned invalid JSON: {exc}"
        ) from exc
    if transcript.get("device_used") != device:
        raise ProcessingError(
            f"Whisper device mismatch: requested {device}, "
            f"worker reported {transcript.get('device_used')}"
        )
    return transcript


@audited(stage="transcribe")
def run_transcribe(
    video_path_or_action: Union[str, pathlib.Path, Callable[..., Any]],
    *args: Any,
    run_id: Optional[str] = None,
    model_size: str = "small",
    device: str = "cuda",
    compute_type: str = "float16",
    language: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    """Execute Stage 2 (transcribe) pipeline processing or run action callback."""
    if callable(video_path_or_action):
        return video_path_or_action(*args, **kwargs)

    vid_p = pathlib.Path(video_path_or_action).resolve()
    if not vid_p.exists():
        raise ProcessingError(f"Input video for transcribe does not exist: {vid_p}")

    run_dir = get_run_dir(run_id)
    tx_dir = run_dir / "artifacts" / "transcribe"
    tx_dir.mkdir(parents=True, exist_ok=True)

    audio_wav = tx_dir / "audio_16k.wav"
    transcript_json = tx_dir / "transcript.json"

    extract_audio_wav(vid_p, audio_wav)
    transcript_data = transcribe_with_faster_whisper(
        audio_wav=audio_wav,
        model_size=model_size,
        device=device,
        compute_type=compute_type,
        language=language,
    )

    transcript_json.write_text(
        json.dumps(transcript_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return {
        "status": "ok",
        "audio_path": str(audio_wav),
        "transcript_path": str(transcript_json),
        "transcript": transcript_data,
        "evidence_paths": [str(audio_wav), str(transcript_json)],
    }
