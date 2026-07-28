"""Generate the deterministic three-candidate media fixture for panel UI-0.

The source is entirely synthetic.  Each three-second interval has a unique
colour, bar count, and audio frequency so a preview can be matched to a clip
without relying on titles, network access, or third-party media.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from cortes.log import action_span, get_run_dir, run_cmd, run_context


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "panel_preview_identity"
    / "source_three_candidates.mp4"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_fixture(output: Path, run_id: str) -> dict[str, object]:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    actions = [
        {"action": "ui0.fixture.generate", "stage": "env"},
        {"action": "ui0.fixture.probe", "stage": "verify"},
        {"action": "ui0.fixture.publish", "stage": "report"},
    ]
    with run_context(
        run_id=run_id,
        actions=actions,
        component="ui0.panel_baseline",
    ) as active_run_id:
        run_dir = get_run_dir(active_run_id)
        artifact_dir = run_dir / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        generated_video = artifact_dir / "source_three_candidates.mp4"

        with action_span(
            "env",
            "ui0.fixture.generate",
            component="ui0.panel_baseline",
            next_action="ui0.fixture.probe",
            next_stage="verify",
        ) as span:
            command = [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0xd7263d:s=640x360:r=30:d=3,"
                "drawbox=x=280:y=80:w=80:h=200:color=white:t=fill",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000:duration=3",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x20a05a:s=640x360:r=30:d=3,"
                "drawbox=x=220:y=80:w=70:h=200:color=white:t=fill,"
                "drawbox=x=350:y=80:w=70:h=200:color=white:t=fill",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=660:sample_rate=48000:duration=3",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x2563eb:s=640x360:r=30:d=3,"
                "drawbox=x=170:y=80:w=60:h=200:color=white:t=fill,"
                "drawbox=x=290:y=80:w=60:h=200:color=white:t=fill,"
                "drawbox=x=410:y=80:w=60:h=200:color=white:t=fill",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=880:sample_rate=48000:duration=3",
                "-filter_complex",
                "[0:v][1:a][2:v][3:a][4:v][5:a]"
                "concat=n=3:v=1:a=1[v][a]",
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(generated_video),
            ]
            result = run_cmd(
                command,
                stage="env",
                action="ui0.fixture.ffmpeg",
                evidence_paths=[generated_video],
            )
            if result.returncode != 0 or not generated_video.is_file():
                raise RuntimeError(
                    "FFmpeg failed to generate the panel baseline fixture: "
                    f"{result.stderr}"
                )
            span.set_evidence([generated_video])

        with action_span(
            "verify",
            "ui0.fixture.probe",
            component="ui0.panel_baseline",
            next_action="ui0.fixture.publish",
            next_stage="report",
        ) as span:
            probe_result = run_cmd(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration:stream=index,codec_type,codec_name,width,height",
                    "-of",
                    "json",
                    str(generated_video),
                ],
                stage="verify",
                action="ui0.fixture.ffprobe",
            )
            if probe_result.returncode != 0:
                raise RuntimeError(
                    f"ffprobe failed for the panel fixture: {probe_result.stderr}"
                )
            probe = json.loads(probe_result.stdout)
            manifest = {
                "schema_version": "1.0.0",
                "fixture": generated_video.name,
                "sha256": _sha256(generated_video),
                "candidates": [
                    {
                        "clip_id": "fixture-red-440",
                        "start_seconds": 0,
                        "end_seconds": 3,
                        "visual_identity": "red background, one white bar",
                        "audio_frequency_hz": 440,
                    },
                    {
                        "clip_id": "fixture-green-660",
                        "start_seconds": 3,
                        "end_seconds": 6,
                        "visual_identity": "green background, two white bars",
                        "audio_frequency_hz": 660,
                    },
                    {
                        "clip_id": "fixture-blue-880",
                        "start_seconds": 6,
                        "end_seconds": 9,
                        "visual_identity": "blue background, three white bars",
                        "audio_frequency_hz": 880,
                    },
                ],
                "ffprobe": probe,
            }
            manifest_path = artifact_dir / "manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            span.set_evidence([generated_video, manifest_path])

        with action_span(
            "report",
            "ui0.fixture.publish",
            component="ui0.panel_baseline",
        ) as span:
            published_manifest = output.with_name("manifest.json")
            shutil.copy2(generated_video, output)
            shutil.copy2(manifest_path, published_manifest)
            span.decision = {
                "output": str(output),
                "manifest": str(published_manifest),
                "sha256": manifest["sha256"],
            }
            span.transition_reason = (
                "fixture and manifest copied to their versioned paths"
            )
            span.set_evidence([generated_video, manifest_path])

    return {
        "run_id": active_run_id,
        "output": str(output),
        "manifest": str(output.with_name("manifest.json")),
        "sha256": manifest["sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the deterministic panel preview identity fixture."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--run-id", default="run_ui0_panel_fixture")
    args = parser.parse_args()
    print(json.dumps(generate_fixture(args.output, args.run_id), indent=2))


if __name__ == "__main__":
    main()
