"""
tests/test_web_dashboard.py - Unit and integration tests for Web Dashboard REST API.
Tests HTML panel rendering, /api/analyze, /api/generate-clip, /api/gdrive-upload,
HTTP status error codes (400, 404, 405), and multi-threaded request concurrency.
"""

import json
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest


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
        """Test issuing an unsupported HTTP method (e.g. PUT) returns HTTP 405 Method Not Allowed."""
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
        """Test POST /api/gdrive-upload with nonexistent file returns HTTP 404 Not Found."""
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
        assert exc_info.value.code == 404


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
