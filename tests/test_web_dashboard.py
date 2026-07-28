"""
tests/test_web_dashboard.py - Unit and integration tests for Web Dashboard REST API.
Tests HTML panel rendering, /api/analyze, /api/generate-clip, /api/gdrive-upload,
HTTP status error codes (400, 404, 405), and multi-threaded request concurrency.
"""

import json
import urllib.request
import urllib.error
import uuid
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import pytest

from youtube_clipper.web_dashboard import ClipperDashboardHandler


class TestWebDashboardEndpoints:
    """Test suite for Web Dashboard HTTP server routes."""

    def test_get_root_dashboard_html(self, dashboard_server: str) -> None:
        """Test GET / returns HTTP 200, text/html content type, and Glassmorphism UI content."""
        url = f"{dashboard_server}/"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            content_type = resp.headers.get("Content-Type", "")
            assert "text/html" in content_type
            body = resp.read().decode("utf-8")
            assert "<!DOCTYPE html>" in body or "<html" in body
            assert "YouTube AI Clipper" in body or "glassmorphism" in body.lower() or "container" in body
            assert "Revisar e configurar" in body
            assert "confirmed_configuration" in body
            assert "Recibo de renderização" in body
            assert "clipExactTime(clip, 'start_time', 'start_timestamp')" in body

    def test_get_index_html(self, dashboard_server: str) -> None:
        """Test GET /index.html returns HTTP 200 and HTML template."""
        url = f"{dashboard_server}/index.html"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            body = resp.read().decode("utf-8")
            assert "YouTube AI Clipper" in body

    def test_post_api_analyze_valid_json(
        self, dashboard_server: str, mock_yt_dlp_subs: None
    ) -> None:
        """Test POST /api/analyze with valid YouTube URL returning clips, transcript, and hashtags."""
        url = f"{dashboard_server}/api/analyze"
        payload = json.dumps({"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            content_type = resp.headers.get("Content-Type", "")
            assert "application/json" in content_type
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("success") is True
            assert "clips" in data
            assert isinstance(data["clips"], list)
            assert "transcript" in data
            assert "hashtags" in data

    def test_post_api_generate_clip_valid_json(
        self, dashboard_server: str, mock_ffmpeg: pytest.FixtureRequest, mock_yt_dlp: pytest.FixtureRequest
    ) -> None:
        """Test POST /api/generate-clip returning HTTP 200, clip_path, and download_url."""
        url = f"{dashboard_server}/api/generate-clip"
        payload = json.dumps({
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "start": 10.0,
            "end": 40.0,
            "format": "blur_background",
            "overlay_text": "Contexto essencial do corte",
            "confirmed_configuration": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("success") is True
            assert "clip_path" in data or "output_path" in data
            assert "download_url" in data

    def test_generate_clip_returns_authoritative_receipt(
        self,
        dashboard_server: str,
        mock_ffmpeg: pytest.FixtureRequest,
        mock_yt_dlp: pytest.FixtureRequest,
    ) -> None:
        """The server confirms normalized settings actually passed to rendering."""
        payload = json.dumps({
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "start": 10.25,
            "end": 20.5,
            "format": "crop_center",
            "crop_focus": "right",
            "blur_sigma": 9,
            "include_audio": False,
            "overlay_text": "Análise editorial confirmada",
            "overlay_position": "bottom",
            "gdrive": False,
            "confirmed_configuration": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{dashboard_server}/api/generate-clip",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))

        applied = data["applied_settings"]
        receipt = data["render_receipt"]
        assert applied["start_seconds"] == 10.25
        assert applied["end_seconds"] == 20.5
        assert applied["duration_seconds"] == 10.25
        assert applied["format"] == "crop_center"
        assert applied["crop_focus"] == "right"
        assert applied["audio_included"] is False
        assert applied["editorial_overlay"] == {
            "included": True,
            "text": "Análise editorial confirmada",
            "position": "bottom",
        }
        assert applied["captions_included"] is False
        assert applied["narration_included"] is False
        assert applied["resolution"] == {
            "width": 1080,
            "height": 1920,
            "aspect_ratio": "9:16",
        }
        assert receipt["request_id"]
        assert receipt["file"]["size_bytes"] > 1000
        assert receipt["applied_settings"] == applied
        assert "Áudio original" in receipt["not_included"]
        assert Path(data["output_path"]).name == receipt["file"]["name"]

    def test_generate_clip_requires_explicit_confirmation(
        self, dashboard_server: str
    ) -> None:
        payload = json.dumps({
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "start": 10,
            "end": 20,
            "format": "blur_background",
            "overlay_text": "Sem confirmação",
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{dashboard_server}/api/generate-clip",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 400
        body = json.loads(exc_info.value.read().decode("utf-8"))
        assert body["field"] == "confirmed_configuration"

    @pytest.mark.parametrize(
        "override",
        [
            {"end": 70},
            {"overlay_text": ""},
            {"include_audio": "yes"},
            {"blur_sigma": 99},
            {"crop_focus": "outside"},
            {"overlay_position": "middle"},
        ],
    )
    def test_generate_clip_rejects_invalid_editor_configuration(
        self, dashboard_server: str, override: dict[str, object]
    ) -> None:
        config = {
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "start": 10,
            "end": 20,
            "format": "blur_background",
            "overlay_text": "Configuração válida",
            "include_audio": True,
            "confirmed_configuration": True,
        }
        config.update(override)
        req = urllib.request.Request(
            f"{dashboard_server}/api/generate-clip",
            data=json.dumps(config).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 400

    def test_post_api_gdrive_upload_valid_json(
        self, dashboard_server: str, mock_gdrive: pytest.FixtureRequest, dummy_video_file: Path
    ) -> None:
        """Test POST /api/gdrive-upload with valid file_path returning HTTP 200 and GDrive status/web_view_link."""
        url = f"{dashboard_server}/api/gdrive-upload"
        payload = json.dumps({"file_path": str(dummy_video_file)}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("status") == "success" or data.get("success") is True
            assert "web_view_link" in data or "link" in data

    def test_html_contains_gdrive_folder_id_input(self, dashboard_server: str) -> None:
        """Test GET / returns HTML template containing gdriveFolderId input element."""
        url = f"{dashboard_server}/"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            body = resp.read().decode("utf-8")
            assert 'id="gdriveFolderId"' in body
            assert "1mYLUnTMhdflzmYhee804Nj52jBQuOI8H" in body

    def test_post_api_gdrive_upload_with_folder_id(
        self, dashboard_server: str, mock_gdrive: pytest.FixtureRequest, dummy_video_file: Path
    ) -> None:
        """Test POST /api/gdrive-upload with explicit folder_id in request body."""
        url = f"{dashboard_server}/api/gdrive-upload"
        payload = json.dumps({
            "file_path": str(dummy_video_file),
            "folder_id": "custom_web_folder_123"
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("status") == "success" or data.get("success") is True

    def test_post_api_generate_clip_with_folder_id_and_cookies(
        self, dashboard_server: str, mock_ffmpeg: pytest.FixtureRequest, mock_yt_dlp: pytest.FixtureRequest, mock_gdrive: pytest.FixtureRequest
    ) -> None:
        """Test POST /api/generate-clip passing folder_id and cookies."""
        url = f"{dashboard_server}/api/generate-clip"
        payload = json.dumps({
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "start": 10.0,
            "end": 20.0,
            "format": "blur_background",
            "overlay_text": "Contexto essencial do corte",
            "confirmed_configuration": True,
            "gdrive": True,
            "folder_id": "test_folder_999",
            "cookies": "/path/to/cookies.txt"
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("success") is True

    def test_post_api_analyze_with_cookies(
        self, dashboard_server: str, mock_yt_dlp_subs: None
    ) -> None:
        """Test POST /api/analyze passing cookies parameter."""
        url = f"{dashboard_server}/api/analyze"
        payload = json.dumps({
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "cookies": "chrome"
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("success") is True


    def test_get_api_download_existing_file(
        self, dashboard_server: str, dummy_video_file: Path
    ) -> None:
        """Test GET /api/download/<filename> serves the clip file with video/mp4 MIME type."""
        filename = dummy_video_file.name
        url = f"{dashboard_server}/api/download/{filename}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            assert "video/mp4" in resp.headers.get("Content-Type", "")
            content = resp.read()
            assert len(content) > 0

    def test_get_api_download_nonexistent_file(
        self, dashboard_server: str
    ) -> None:
        """Test GET /api/download/<filename> for missing file returns HTTP 404."""
        url = f"{dashboard_server}/api/download/nonexistent_clip_xyz.mp4"
        req = urllib.request.Request(url, method="GET")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 404



class TestWebDashboardOperationStatus:
    """Status UI, request correlation, sanitization, and partial outcomes."""

    def test_html_contains_persistent_status_and_activity_log(
        self, dashboard_server: str
    ) -> None:
        with urllib.request.urlopen(f"{dashboard_server}/") as resp:
            body = resp.read().decode("utf-8")
        assert 'role="log"' in body
        assert 'aria-live="polite"' in body
        assert 'id="activityLog"' in body
        assert 'id="operationBadge"' in body
        assert 'X-Request-ID' in body
        assert 'startStatusPolling' in body
        assert 'card-operation-status' in body

    def test_html_contains_accessible_drive_progress_per_card(
        self, dashboard_server: str
    ) -> None:
        """Each clip exposes honest determinate/indeterminate Drive progress."""
        with urllib.request.urlopen(f"{dashboard_server}/") as resp:
            body = resp.read().decode("utf-8")

        assert 'class="drive-progress"' in body
        assert 'role="progressbar"' in body
        assert 'aria-label="Progresso do upload do corte ${rank} ao Google Drive"' in body
        assert 'aria-valuemin="0"' in body
        assert 'aria-valuemax="100"' in body
        assert "function renderDriveProgress" in body
        assert "data.drive_upload" in body
        assert 'removeAttribute("aria-valuenow")' in body
        assert 'setAttribute("aria-valuenow"' in body

    def test_status_aggregates_sanitized_drive_upload_progress(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Drive progress is monotonic and never exposes raw audit payloads."""
        request_id = f"drive-progress-{uuid.uuid4().hex}"
        run_id = f"run_dashboard_gdrive_{uuid.uuid4().hex}"
        run_dir = tmp_path / "runs" / run_id
        run_dir.mkdir(parents=True)
        timestamps = [
            "2026-07-27T12:00:00+00:00",
            "2026-07-27T12:00:01+00:00",
            "2026-07-27T12:00:02+00:00",
            "2026-07-27T12:00:03+00:00",
            "2026-07-27T12:00:04+00:00",
            "2026-07-27T12:00:05+00:00",
        ]

        def event(
            seq: int,
            action: str,
            status: str,
            *,
            decision: dict | None = None,
            attempt: int = 1,
        ) -> dict:
            return {
                "event_id": f"event-{seq}",
                "run_id": run_id,
                "request_id": request_id,
                "seq": seq,
                "ts": timestamps[seq - 1],
                "stage": "report",
                "status": status,
                "component": "youtube_clipper.gdrive",
                "action": action,
                "attempt": attempt,
                "duration_ms": 0.0,
                "error": None,
                "decision": {
                    **(decision or {}),
                    "oauth_token": "must-never-leak",
                },
                "input": {
                    "file_path": "/private/must-never-leak.mp4",
                    "size_bytes": 4096,
                },
                "cmd": ["must-never-leak"],
                "evidence": {"paths": ["must-never-leak"]},
                "execution": {"traceback": "must-never-leak"},
            }

        events = [
            event(1, "gdrive.auth.oauth_env", "started"),
            event(
                2,
                "gdrive.upload.progress.1",
                "succeeded",
                decision={
                    "progress_percent": 25.0,
                    "uploaded_bytes": 1024,
                    "total_bytes": 4096,
                    "chunk_number": 1,
                },
            ),
            event(
                3,
                "gdrive.upload.progress.2",
                "succeeded",
                decision={
                    "progress_percent": 10.0,
                    "uploaded_bytes": 512,
                    "total_bytes": 4096,
                    "chunk_number": 2,
                },
            ),
            event(4, "gdrive.upload", "retrying", attempt=2),
            event(
                5,
                "gdrive.upload.progress.3",
                "succeeded",
                decision={
                    "progress_percent": 150.0,
                    "uploaded_bytes": 8192,
                    "total_bytes": 4096,
                    "chunk_number": 3,
                },
            ),
            event(6, "gdrive.set_permission", "succeeded"),
        ]
        (run_dir / "events.jsonl").write_text(
            "".join(f"{json.dumps(item)}\n" for item in events),
            encoding="utf-8",
        )
        (run_dir / "seal.json").write_text(
            json.dumps({"status": "succeeded"}),
            encoding="utf-8",
        )

        monkeypatch.chdir(tmp_path)
        handler = object.__new__(ClipperDashboardHandler)
        handler.server = SimpleNamespace(
            request_runs={request_id: [run_id]},
        )
        data = handler._request_status_payload(request_id)

        assert data is not None
        assert data["state"] == "completed"
        assert data["drive_upload"] == {
            "state": "succeeded",
            "determinate": True,
            "progress_percent": 100.0,
            "uploaded_bytes": 4096,
            "total_bytes": 4096,
            "chunk_number": 3,
            "attempt": 2,
            "updated_at": timestamps[-1],
        }
        allowed_event_fields = {
            "event_id", "run_id", "seq", "ts", "stage", "status",
            "component", "action", "duration_ms", "error",
        }
        assert all(set(item) == allowed_event_fields for item in data["events"])
        serialized = json.dumps(data)
        for forbidden in (
            '"decision"',
            '"input"',
            '"cmd"',
            '"evidence"',
            '"execution"',
            "must-never-leak",
        ):
            assert forbidden not in serialized

    def test_response_echoes_request_id_and_status_is_sanitized(
        self, dashboard_server: str
    ) -> None:
        request_id = f"status-test-{uuid.uuid4().hex}"
        req = urllib.request.Request(
            f"{dashboard_server}/",
            headers={"X-Request-ID": request_id},
            method="GET",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.headers.get("X-Request-ID") == request_id
            resp.read()

        with urllib.request.urlopen(
            f"{dashboard_server}/api/status/{request_id}"
        ) as resp:
            assert resp.headers.get("Cache-Control") == "no-store"
            data = json.loads(resp.read().decode("utf-8"))

        assert data["success"] is True
        assert data["request_id"] == request_id
        assert data["completed"] is True
        assert data["events"]
        allowed = {
            "event_id", "run_id", "seq", "ts", "stage", "status",
            "component", "action", "duration_ms", "error",
        }
        assert all(set(event) == allowed for event in data["events"])
        serialized = json.dumps(data)
        for forbidden in ("input", "cmd", "evidence", "execution", "traceback"):
            assert f'"{forbidden}"' not in serialized

    def test_invalid_status_request_id_returns_400(
        self, dashboard_server: str
    ) -> None:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"{dashboard_server}/api/status/bad%24id")
        assert exc_info.value.code == 400

    def test_generate_clip_correlates_pipeline_events(
        self,
        dashboard_server: str,
        mock_ffmpeg: pytest.FixtureRequest,
        mock_yt_dlp: pytest.FixtureRequest,
    ) -> None:
        request_id = f"render-test-{uuid.uuid4().hex}"
        payload = json.dumps({
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "start": 10.0,
            "end": 20.0,
            "format": "blur_background",
            "overlay_text": "Contexto essencial do corte",
            "confirmed_configuration": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{dashboard_server}/api/generate-clip",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Request-ID": request_id,
            },
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            resp.read()

        with urllib.request.urlopen(
            f"{dashboard_server}/api/status/{request_id}"
        ) as resp:
            status_data = json.loads(resp.read().decode("utf-8"))
        actions = {event["action"] for event in status_data["events"]}
        assert "dashboard.ingest_interval" in actions
        assert "dashboard.render" in actions
        assert "public.validate_input" not in actions
        assert any(action == "command.ffmpeg" for action in actions)
        assert len(status_data["run_ids"]) >= 2

    def test_generate_and_upload_reports_partial_success(
        self,
        dashboard_server: str,
        mock_ffmpeg: pytest.FixtureRequest,
        mock_yt_dlp: pytest.FixtureRequest,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "youtube_clipper.web_dashboard.upload_clip_to_gdrive",
            lambda *args, **kwargs: {
                "success": False,
                "status": "error",
                "error": "quota indisponível",
            },
        )
        payload = json.dumps({
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "start": 10.0,
            "end": 20.0,
            "format": "blur_background",
            "overlay_text": "Contexto essencial do corte",
            "confirmed_configuration": True,
            "gdrive": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{dashboard_server}/api/generate-clip",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        assert data["success"] is True
        assert data["overall_status"] == "partial_success"
        assert data["upload"]["requested"] is True
        assert data["upload"]["success"] is False
        assert data["upload"]["error"] == "quota indisponível"

    def test_http_400_is_terminal_failure_in_status_log(
        self, dashboard_server: str
    ) -> None:
        request_id = f"error-test-{uuid.uuid4().hex}"
        req = urllib.request.Request(
            f"{dashboard_server}/api/analyze",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "X-Request-ID": request_id,
            },
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 400

        request_events = []
        status_data = {}
        for _ in range(20):
            with urllib.request.urlopen(
                f"{dashboard_server}/api/status/{request_id}"
            ) as resp:
                status_data = json.loads(resp.read().decode("utf-8"))
            request_events = [
                event for event in status_data["events"]
                if event["action"] == "http.post./api/analyze"
            ]
            if any(event["status"] == "failed" for event in request_events):
                break
            time.sleep(0.05)
        assert any(event["status"] == "failed" for event in request_events)
        assert status_data["state"] == "failed"


class TestWebDashboardErrors:
    """Test suite for error handling in Web Dashboard (400, 404, 405)."""

    def test_post_bad_json_returns_http_400(self, dashboard_server: str) -> None:
        """Test POST with malformed JSON body returns HTTP 400 Bad Request."""
        url = f"{dashboard_server}/api/analyze"
        bad_payload = b"{ malformed json string "
        req = urllib.request.Request(
            url,
            data=bad_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 400

    def test_invalid_endpoint_path_returns_http_404(self, dashboard_server: str) -> None:
        """Test requesting an invalid endpoint route returns HTTP 404 Not Found."""
        url = f"{dashboard_server}/api/non_existent_route"
        req = urllib.request.Request(url, method="GET")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 404

    def test_invalid_http_method_returns_http_405(self, dashboard_server: str) -> None:
        """Test issuing an unsupported HTTP method (e.g. PUT) returns HTTP 405 Method Not Allowed with JSON payload."""
        url = f"{dashboard_server}/api/analyze"
        payload = json.dumps({"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 405
        assert "application/json" in exc_info.value.headers.get("Content-Type", "")
        data = json.loads(exc_info.value.read().decode("utf-8"))
        assert data["success"] is False
        assert "Method Not Allowed" in data["error"]

    def test_status_pending_for_valid_unregistered_request_id(self, dashboard_server: str) -> None:
        """Test status check returns 200 OK and pending state for a valid but unregistered request ID."""
        valid_id = "req_1234567890_abcdefg"
        url = f"{dashboard_server}/api/status/{valid_id}"
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            assert data["request_id"] == valid_id
            assert data["state"] == "pending"
            assert data["completed"] is False
            assert data["events"] == []

    def test_post_missing_param_returns_http_400(self, dashboard_server: str) -> None:
        """Test POST with missing required parameters returns HTTP 400."""
        url = f"{dashboard_server}/api/analyze"
        payload = json.dumps({}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 400

        url = f"{dashboard_server}/api/gdrive-upload"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 400

    def test_get_on_post_endpoint_returns_http_405(self, dashboard_server: str) -> None:
        """Test sending GET request to POST-only endpoint returns HTTP 405 Method Not Allowed."""
        url = f"{dashboard_server}/api/analyze"
        req = urllib.request.Request(url, method="GET")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 405

    def test_path_traversal_download_returns_http_400(self, dashboard_server: str) -> None:
        """Test path traversal attempts in /api/download/<filename> return HTTP 400 Bad Request."""
        for path_segment in ("../PROJECT.md", "..%2fPROJECT.md", "..\\PROJECT.md"):
            url = f"{dashboard_server}/api/download/{path_segment}"
            req = urllib.request.Request(url, method="GET")
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req)
            assert exc_info.value.code == 400

    def test_invalid_format_mode_returns_http_400(self, dashboard_server: str) -> None:
        """Test POST /api/generate-clip with invalid format mode returns HTTP 400 Bad Request."""
        url = f"{dashboard_server}/api/generate-clip"
        payload = json.dumps({
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "format": "invalid_format_xyz",
            "overlay_text": "Teste de formato",
            "confirmed_configuration": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 400

    def test_gdrive_upload_nonexistent_file_returns_http_404(self, dashboard_server: str) -> None:
        """Paths outside the dedicated output directory are forbidden."""
        url = f"{dashboard_server}/api/gdrive-upload"
        payload = json.dumps({"file_path": "/nonexistent/path/to/clip.mp4"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 403


class TestWebDashboardConcurrency:
    """Test suite for multi-threaded request handling."""

    def test_concurrent_requests_handled_successfully(self, dashboard_server: str) -> None:
        """Test that multiple concurrent requests issued to dashboard_server execute without blocking or failing."""
        def fetch_index(i: int) -> int:
            url = f"{dashboard_server}/index.html"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req) as resp:
                return resp.status

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch_index, i) for i in range(10)]
            results = [f.result() for f in futures]

        assert all(status == 200 for status in results)
        assert len(results) == 10
