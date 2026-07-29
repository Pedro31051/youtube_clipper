"""Emit a reproducible JSON benchmark for one checkout's vertical formatter."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import tempfile
import time
from pathlib import Path

from cortes.ingest import probe_video_metadata
from cortes.log import run_cmd
from youtube_clipper.video_formatter import VideoFormatter, detect_h264_encoder


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="youtube-clipper-benchmark-") as raw:
        root = Path(raw)
        source = root / "source.mp4"
        fixture = run_cmd(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=640x360:rate=30:duration=5",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000:duration=5",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(source),
            ],
            stage="benchmark",
            audit=False,
        )
        if fixture.returncode != 0:
            raise RuntimeError(fixture.stderr)

        measurements = []
        encoder = detect_h264_encoder()
        for repetition in range(args.repetitions):
            output = root / f"output-{repetition}.mp4"
            started = time.monotonic()
            VideoFormatter.convert_to_vertical(
                input_path=str(source),
                output_path=str(output),
                mode="blur_background",
                start=0,
                end=5,
            )
            elapsed = time.monotonic() - started
            metadata = probe_video_metadata(output)
            measurements.append(
                {
                    "processing_seconds": round(elapsed, 3),
                    "processing_ratio": round(elapsed / float(metadata["duration"]), 4),
                    "duration_seconds": metadata["duration"],
                    "width": metadata["width"],
                    "height": metadata["height"],
                    "fps": metadata["fps"],
                    "frame_count": round(
                        float(metadata["duration"]) * float(metadata["fps"])
                    ),
                    "video_codec": metadata["video_codec"],
                    "size_bytes": metadata["file_size"],
                }
            )

    ratios = [float(item["processing_ratio"]) for item in measurements]
    print(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "label": args.label,
                "encoder": encoder,
                "hardware": platform.platform(),
                "repetitions": args.repetitions,
                "median_processing_ratio": round(statistics.median(ratios), 4),
                "measurements": measurements,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
