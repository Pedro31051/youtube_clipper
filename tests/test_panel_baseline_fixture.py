"""Physical contract for the synthetic UI-0 panel fixture."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from cortes.log import run_cmd, run_context


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "panel_preview_identity"
VIDEO_PATH = FIXTURE_DIR / "source_three_candidates.mp4"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_panel_baseline_fixture_has_three_distinct_physical_previews(
    tmp_path: Path,
) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert VIDEO_PATH.is_file()
    assert manifest["sha256"] == _sha256(VIDEO_PATH)
    assert [item["clip_id"] for item in manifest["candidates"]] == [
        "fixture-red-440",
        "fixture-green-660",
        "fixture-blue-880",
    ]

    actions = [
        {"action": "ui0.fixture.test.probe", "stage": "verify"},
        {"action": "ui0.fixture.test.frames", "stage": "verify"},
    ]
    with run_context(
        run_id=f"run_ui0_fixture_test_{uuid.uuid4().hex}",
        actions=actions,
        component="tests.panel_baseline",
    ):
        probe = run_cmd(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,width,height",
                "-of",
                "json",
                str(VIDEO_PATH),
            ],
            stage="verify",
            action="ui0.fixture.test.probe",
        )
        assert probe.returncode == 0, probe.stderr
        measured = json.loads(probe.stdout)
        assert 8.9 <= float(measured["format"]["duration"]) <= 9.1
        video_stream = next(
            stream
            for stream in measured["streams"]
            if stream["codec_type"] == "video"
        )
        assert (video_stream["width"], video_stream["height"]) == (640, 360)

        frame_hashes = []
        for index, timestamp in enumerate(("1.5", "4.5", "7.5"), start=1):
            frame_path = tmp_path / f"candidate-{index}.png"
            frame = run_cmd(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    timestamp,
                    "-i",
                    str(VIDEO_PATH),
                    "-frames:v",
                    "1",
                    str(frame_path),
                ],
                stage="verify",
                action="ui0.fixture.test.frames",
            )
            assert frame.returncode == 0, frame.stderr
            frame_hashes.append(_sha256(frame_path))

        assert len(set(frame_hashes)) == 3
