"""Regression proofs for the findings confirmed by the independent T0 audit."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from cortes.verify import verify_run
from cortes.log import run_cmd
from youtube_clipper.exceptions import ProcessingError
from youtube_clipper.pipeline import run_pipeline
from youtube_clipper.processor import FFmpegProcessor
from youtube_clipper.web_dashboard import (
    ClipperDashboardHandler,
    start_dashboard_server,
)


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _portable_run(tmp_path: Path, *, legacy_absolute: bool = False) -> Path:
    run = tmp_path / "portable_run"
    artifact = run / "artifacts" / "proof.txt"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("portable evidence\n", encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest()
    evidence_path = "artifacts/proof.txt"
    if legacy_absolute:
        evidence_path = "/home/producer/runs/portable_run/artifacts/proof.txt"
    event = {
        "schema_version": "1.0.0",
        "run_id": run.name,
        "seq": 1,
        "ts": "2026-07-27T00:00:00+00:00",
        "agent": "test",
        "video_id": "synthetic",
        "clip_id": None,
        "stage": "env",
        "attempt": 1,
        "severity": "info",
        "duration_ms": 1.0,
        "tool": "python",
        "cmd": None,
        "exit_code": 0,
        "args_hash": "sha256:" + hashlib.sha256(b"").hexdigest(),
        "cost": {"usd": 0.0, "tokens_in": 0, "tokens_out": 0},
        "trace": {"span_id": "0123456789abcdef", "parent_span_id": None},
        "evidence": {
            "paths": [evidence_path],
            "sha256": [digest],
            "bytes": [artifact.stat().st_size],
        },
        "outcome": "ok",
        "error": None,
        "claim": None,
    }
    (run / "events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
    return run


def _synthetic_video(path: Path, duration: float = 3.0) -> None:
    result = run_cmd(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size=320x240:rate=15:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        audit=False,
    )
    assert result.returncode == 0, result.stderr


def test_youtube_segment_offset_is_consumed_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    segment = tmp_path / "already_segmented.mp4"
    output = tmp_path / "result.mp4"
    _synthetic_video(segment)

    class LocalDownloader:
        def download_segment(self, **kwargs: object) -> str:
            assert kwargs["start"] == 60.0
            assert kwargs["end"] == 63.0
            return str(segment)

    monkeypatch.setattr("youtube_clipper.pipeline.YouTubeDownloader", LocalDownloader)
    result = run_pipeline(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        start=60,
        end=63,
        output=output,
    )

    probe = run_cmd(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            result,
        ],
        audit=False,
    )
    assert probe.returncode == 0
    assert 2.5 <= float(probe.stdout.strip()) <= 3.1


def test_out_of_range_cut_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    _synthetic_video(source)
    with pytest.raises(ProcessingError):
        FFmpegProcessor().cut_media(source, 60, 63, tmp_path / "invalid.mp4")


def test_verifier_is_read_only_and_creates_no_collateral_run(tmp_path: Path) -> None:
    run = _portable_run(tmp_path)
    before = _tree_hashes(run)
    result = verify_run(run)
    after = _tree_hashes(run)

    assert result["overall_passed"] is True
    assert before == after
    assert not (Path.cwd() / "runs").exists()


def test_legacy_absolute_evidence_is_rejected_as_non_portable(tmp_path: Path) -> None:
    original = _portable_run(tmp_path / "original", legacy_absolute=True)
    relocated = tmp_path / "relocated" / original.name
    relocated.parent.mkdir()
    shutil.copytree(original, relocated)

    result = verify_run(relocated)

    assert result["overall_passed"] is False
    failed = {
        check["check_id"] for check in result["checks"] if not check["passed"]
    }
    assert "evidence_paths_relative" in failed
    assert all(not Path(check["evidence_path"]).is_absolute() for check in result["checks"])


def test_removing_all_declared_artifacts_fails_verification(tmp_path: Path) -> None:
    run = _portable_run(tmp_path)
    shutil.rmtree(run / "artifacts")

    result = verify_run(run)
    failed = {check["check_id"] for check in result["checks"] if not check["passed"]}

    assert result["overall_passed"] is False
    assert {"artifact_exists", "artifact_sha256", "artifact_bytes"} <= failed


def test_verifier_rejects_evidence_path_escape(tmp_path: Path) -> None:
    run = _portable_run(tmp_path)
    events_file = run / "events.jsonl"
    event = json.loads(events_file.read_text(encoding="utf-8"))
    event["evidence"]["paths"] = ["artifacts/../../outside.txt"]
    events_file.write_text(json.dumps(event) + "\n", encoding="utf-8")

    result = verify_run(run)
    failed = {check["check_id"] for check in result["checks"] if not check["passed"]}

    assert result["overall_passed"] is False
    assert {"artifact_exists", "artifact_sha256", "artifact_bytes"} <= failed


def test_verifier_output_must_be_outside_verified_run(tmp_path: Path) -> None:
    run = _portable_run(tmp_path)
    with pytest.raises(ValueError):
        verify_run(run, output_path=run / "verify_result.json")
    outside = tmp_path / "verification" / "result.json"
    verify_run(run, output_path=outside)
    assert outside.exists()


def test_dashboard_refuses_public_bind_without_token() -> None:
    with pytest.raises(ValueError, match="bearer API token"):
        start_dashboard_server(port=0, host="0.0.0.0")


def test_dashboard_token_protects_routes(tmp_path: Path) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), ClipperDashboardHandler)
    server.output_dir = tmp_path / "output"
    server.output_dir.mkdir()
    server.api_token = "secret-test-token"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(url)
        assert exc.value.code == 401
        request = urllib.request.Request(
            url, headers={"Authorization": "Bearer secret-test-token"}
        )
        with urllib.request.urlopen(request) as response:
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_does_not_serve_files_outside_output_dir(
    dashboard_server: str, tmp_path: Path
) -> None:
    secret = tmp_path / "outside.mp4"
    secret.write_bytes(b"not public")
    request = urllib.request.Request(
        f"{dashboard_server}/api/download/{secret.name}"
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(request)
    assert exc.value.code == 404


def test_dashboard_cookie_input_does_not_mutate_process_environment(
    dashboard_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("YOUTUBE_COOKIES_FILE", "original-value")
    monkeypatch.setattr(
        "youtube_clipper.web_dashboard.extract_transcript_and_analyze",
        lambda *_args, **_kwargs: {"success": True, "clips": []},
    )
    payload = json.dumps(
        {
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "cookies": "client-value",
        }
    ).encode()
    request = urllib.request.Request(
        f"{dashboard_server}/api/analyze",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        assert response.status == 200
    assert os.environ["YOUTUBE_COOKIES_FILE"] == "original-value"


def test_dashboard_rejects_gdrive_path_outside_output_dir(
    dashboard_server: str, tmp_path: Path
) -> None:
    outside = tmp_path / "outside-upload.mp4"
    outside.write_bytes(b"private")
    payload = json.dumps({"file_path": str(outside)}).encode()
    request = urllib.request.Request(
        f"{dashboard_server}/api/gdrive-upload",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(request)
    assert exc.value.code == 403


def test_dashboard_rejects_non_youtube_url(dashboard_server: str) -> None:
    payload = json.dumps({"url": "https://example.com/internal"}).encode()
    request = urllib.request.Request(
        f"{dashboard_server}/api/analyze",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(request)
    assert exc.value.code == 400
