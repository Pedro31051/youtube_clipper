"""Isolated faster-whisper worker invoked exclusively through ``run_cmd``."""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, Optional


def transcribe(
    audio_path: str,
    model_size: str,
    device: str,
    compute_type: str,
    language: Optional[str],
) -> Dict[str, Any]:
    """Run faster-whisper on exactly the requested device."""
    from faster_whisper import WhisperModel

    model = WhisperModel(
        model_size,
        device=device,
        compute_type=compute_type,
    )
    segments_iter, info = model.transcribe(
        audio_path,
        word_timestamps=True,
        language=language,
        beam_size=5,
        best_of=5,
        vad_filter=True,
    )

    segments = []
    words = []
    text_parts = []
    for index, segment in enumerate(segments_iter):
        segment_text = segment.text.strip()
        text_parts.append(segment_text)
        segment_words = []
        for word in segment.words or []:
            start = round(float(word.start), 3)
            end = round(float(word.end), 3)
            word_data = {
                "word": word.word,
                "start": start,
                "end": end,
                "start_ms": int(round(start * 1000)),
                "end_ms": int(round(end * 1000)),
                "probability": round(float(word.probability), 4),
            }
            segment_words.append(word_data)
            words.append(word_data)
        segments.append(
            {
                "id": index,
                "start": round(float(segment.start), 3),
                "end": round(float(segment.end), 3),
                "start_ms": int(round(float(segment.start) * 1000)),
                "end_ms": int(round(float(segment.end) * 1000)),
                "text": segment_text,
                "words": segment_words,
            }
        )

    try:
        detected_language = info.language
    except AttributeError:
        detected_language = language or "unknown"
    try:
        language_probability = round(float(info.language_probability), 4)
    except AttributeError:
        language_probability = 0.0
    try:
        detected_duration = round(float(info.duration), 3)
    except AttributeError:
        detected_duration = 0.0

    return {
        "schema_version": "1.0.0",
        "device_requested": device,
        "device_used": device,
        "compute_type": compute_type,
        "model_size": model_size,
        "language": detected_language,
        "language_probability": language_probability,
        "duration": detected_duration,
        "text": " ".join(part for part in text_parts if part),
        "segments": segments,
        "words": words,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--model", default="small")
    parser.add_argument("--device", choices=("cuda", "cpu"), required=True)
    parser.add_argument("--compute-type", required=True)
    parser.add_argument("--language")
    args = parser.parse_args()
    result = transcribe(
        audio_path=args.audio,
        model_size=args.model,
        device=args.device,
        compute_type=args.compute_type,
        language=args.language,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
