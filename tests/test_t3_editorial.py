"""Focused T3 editorial transformation and template-variation tests."""

from __future__ import annotations

import json
import pathlib

import pytest

from cortes.editorial import (
    assert_variant_not_recent,
    build_clip_id,
    recent_template_records,
)
from cortes.log import compute_sha256
from cortes.verify import verify_run
from youtube_clipper.exceptions import ProcessingError


def _write_t3_run(run_dir: pathlib.Path) -> pathlib.Path:
    clip_dir = run_dir / "artifacts" / "clip_t3"
    editorial_dir = run_dir / "artifacts" / "editorial"
    clip_dir.mkdir(parents=True)
    editorial_dir.mkdir(parents=True)

    video_path = clip_dir / "short.mp4"
    narration_path = editorial_dir / "narration.wav"
    metadata_path = clip_dir / "render_metadata.json"
    video_path.write_bytes(b"video" * 4096)
    narration_path.write_bytes(b"narration" * 1024)

    metadata = {
        "schema_version": "1.0.0",
        "phase": "T3",
        "clip_id": "clip_t3",
        "editorial_transformation_required": True,
        "editorial_requirements": ["narration", "analytical_overlay"],
        "narration_required": True,
        "narration_mixed": True,
        "narration_source_path": "artifacts/editorial/narration.wav",
        "narration_source_sha256": compute_sha256(narration_path),
        "narration_source_bytes": narration_path.stat().st_size,
        "narration_duration_s": 9.0,
        "analytical_overlay": True,
        "overlay_text": "ORIGINAL ANALYSIS",
        "template_variant": "variant_editorial_1",
        "template_variant_history": [
            {"run_id": "prior", "clip_id": "clip_old", "template_variant": "variant_old_1"}
        ],
        "output_size_bytes": video_path.stat().st_size,
    }
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    command = (
        f"ffmpeg -i source.mp4 -i {narration_path} "
        "-filter_complex amix=inputs=2,drawbox=x=1,drawtext=text='ORIGINAL ANALYSIS' "
        f"{video_path}"
    )
    event = {
        "schema_version": "1.0.0",
        "run_id": run_dir.name,
        "seq": 1,
        "ts": "2026-07-27T00:00:00+00:00",
        "agent": "worker",
        "video_id": "synthetic",
        "clip_id": "clip_t3",
        "stage": "render",
        "attempt": 1,
        "severity": "info",
        "duration_ms": 100.0,
        "tool": "ffmpeg",
        "cmd": command,
        "exit_code": 0,
        "args_hash": "sha256:" + ("0" * 64),
        "cost": {"usd": 0.0, "tokens_in": 0, "tokens_out": 0},
        "trace": {"span_id": "0123456789abcdef", "parent_span_id": None},
        "evidence": {
            "paths": [
                "artifacts/clip_t3/short.mp4",
                "artifacts/clip_t3/render_metadata.json",
                "artifacts/editorial/narration.wav",
            ],
            "sha256": [
                compute_sha256(video_path),
                compute_sha256(metadata_path),
                compute_sha256(narration_path),
            ],
            "bytes": [
                video_path.stat().st_size,
                metadata_path.stat().st_size,
                narration_path.stat().st_size,
            ],
        },
        "outcome": "ok",
        "error": None,
        "claim": None,
    }
    (run_dir / "events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
    (run_dir / "commands.log").write_text(
        f"COMMAND: {command}\n", encoding="utf-8"
    )
    return metadata_path


@pytest.fixture
def t3_probe_stubs(monkeypatch):
    def fake_probe(path: pathlib.Path):
        if path.suffix == ".wav":
            return {
                "format": {"duration": "9.0"},
                "streams": [{"codec_type": "audio"}],
            }
        return {
            "format": {"duration": "21.0"},
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1080,
                    "height": 1920,
                    "r_frame_rate": "30/1",
                    "avg_frame_rate": "30/1",
                },
                {"codec_type": "audio"},
            ],
        }

    monkeypatch.setattr("cortes.verify.run_ffprobe_json", fake_probe)
    monkeypatch.setattr("cortes.verify.measure_audio_loudness_lufs", lambda path: -14.0)


def _refresh_metadata_evidence(run_dir: pathlib.Path, metadata_path: pathlib.Path) -> None:
    events_path = run_dir / "events.jsonl"
    event = json.loads(events_path.read_text(encoding="utf-8"))
    event["evidence"]["sha256"][1] = compute_sha256(metadata_path)
    event["evidence"]["bytes"][1] = metadata_path.stat().st_size
    events_path.write_text(json.dumps(event) + "\n", encoding="utf-8")


def test_t3_golden_editorial_proof_passes(tmp_path, t3_probe_stubs):
    run_dir = tmp_path / "run_t3"
    _write_t3_run(run_dir)
    result = verify_run(run_dir)
    assert result["overall_passed"] is True


def test_removing_narration_makes_verify_fail(tmp_path, t3_probe_stubs):
    run_dir = tmp_path / "run_t3_no_narration"
    metadata_path = _write_t3_run(run_dir)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["narration_mixed"] = False
    metadata["narration_source_path"] = None
    metadata["narration_source_sha256"] = None
    metadata["narration_source_bytes"] = None
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    _refresh_metadata_evidence(run_dir, metadata_path)

    result = verify_run(run_dir)
    failed = {check["check_id"] for check in result["checks"] if not check["passed"]}
    assert "editorial_narration::artifacts/clip_t3/short.mp4" in failed
    assert "editorial_transformation::artifacts/clip_t3/short.mp4" in failed


def test_repeated_variant_in_previous_five_fails(tmp_path, t3_probe_stubs):
    run_dir = tmp_path / "run_t3_repeated"
    metadata_path = _write_t3_run(run_dir)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["template_variant_history"] = [
        {
            "run_id": "prior",
            "clip_id": "clip_old",
            "template_variant": metadata["template_variant"],
        }
    ]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    _refresh_metadata_evidence(run_dir, metadata_path)

    result = verify_run(run_dir)
    failed = {check["check_id"] for check in result["checks"] if not check["passed"]}
    assert "template_variant_unique::artifacts/clip_t3/short.mp4" in failed


def test_clip_id_changes_with_template_variant():
    selection = b'{"start_ms": 0, "end_ms": 20000}'
    assert build_clip_id(selection, "variant_alpha") != build_clip_id(
        selection, "variant_beta"
    )


def test_runtime_policy_rejects_recent_variant(tmp_path):
    runs_root = tmp_path / "runs"
    prior_meta = runs_root / "run_prior" / "artifacts" / "clip_old" / "render_metadata.json"
    prior_meta.parent.mkdir(parents=True)
    prior_meta.write_text(
        json.dumps(
            {
                "clip_id": "clip_old",
                "template_variant": "variant_recent_1",
            }
        ),
        encoding="utf-8",
    )
    compatibility_meta = (
        runs_root / "run_prior" / "artifacts" / "render" / "render_metadata.json"
    )
    compatibility_meta.parent.mkdir()
    compatibility_meta.symlink_to(
        pathlib.Path("..") / "clip_old" / "render_metadata.json"
    )
    current_run = runs_root / "run_current"
    current_run.mkdir()
    records = recent_template_records(
        runs_root, current_run_dir=current_run, limit=5
    )
    assert len(records) == 1
    with pytest.raises(ProcessingError, match="previous five"):
        assert_variant_not_recent("variant_recent_1", records)
