"""Physical proof that the quick dashboard render uses canonical components."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from cortes.dashboard_pipeline import run_dashboard_clip_pipeline
from cortes.log import run_cmd


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "panel_preview_identity"
    / "source_three_candidates.mp4"
)


def test_canonical_dashboard_pipeline_applies_plan_without_audio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    run_id = f"run_ui1_dashboard_physical_{uuid.uuid4().hex}"
    clip_id = "clp_22222222222222222222222222222222"
    output = tmp_path / "published.mp4"

    rendered = Path(
        run_dashboard_clip_pipeline(
            input_source=str(FIXTURE),
            start=0,
            end=3,
            output=output,
            mode="crop_center",
            crop_focus="left",
            include_audio=False,
            overlay_text="PROVA UI-1",
            overlay_position="bottom",
            run_id=run_id,
            request_id="ui1-dashboard-physical",
            clip_id=clip_id,
        )
    )

    assert rendered == output
    assert rendered.is_file()
    probe = run_cmd(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height",
            "-of",
            "json",
            str(rendered),
        ],
        stage="verify",
        action="ui1.dashboard.probe",
    )
    assert probe.returncode == 0, probe.stderr
    measured = json.loads(probe.stdout)
    assert 2.8 <= float(measured["format"]["duration"]) <= 3.3
    video = next(
        stream
        for stream in measured["streams"]
        if stream["codec_type"] == "video"
    )
    assert (video["width"], video["height"]) == (1080, 1920)
    assert not any(
        stream["codec_type"] == "audio" for stream in measured["streams"]
    )

    metadata = json.loads(
        (
            tmp_path
            / "runs"
            / run_id
            / "artifacts"
            / clip_id
            / "render_metadata.json"
        ).read_text(encoding="utf-8")
    )
    assert metadata["crop_focus"] == "left"
    assert metadata["overlay_position"] == "bottom"
    assert metadata["audio_included"] is False
