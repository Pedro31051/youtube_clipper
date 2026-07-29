"""
tests/test_gdrive_uploader.py - Unit and integration tests for GoogleDriveUploader.
Tests service account authentication, folder checking/creation, file upload,
and exception handling.
"""

from pathlib import Path
from unittest.mock import MagicMock
import pytest
from youtube_clipper.gdrive_uploader import GoogleDriveUploader, upload_clip_to_gdrive


class TestGoogleDriveUploaderInit:
    """Test suite for GoogleDriveUploader initialization and authentication."""

    def test_init_with_valid_credential_path(
        self, mock_gdrive: MagicMock, tmp_path: Path
    ) -> None:
        """Test initialization when valid credential file path is provided."""
        sa_path = tmp_path / "valid_service_account.json"
        sa_path.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))
        assert uploader.service_account_path == str(sa_path)
        assert uploader.service is not None

    def test_init_with_missing_credential_path_raises_file_not_found(
        self, mock_gdrive: MagicMock, tmp_path: Path
    ) -> None:
        """Test that initialization with non-existent credential path raises FileNotFoundError."""
        non_existent = str(tmp_path / "missing_sa_credentials.json")
        with pytest.raises(FileNotFoundError, match="Service Account JSON file not found"):
            GoogleDriveUploader(service_account_path=non_existent)


class TestGoogleDriveUploadClip:
    """Test suite for upload_clip functionality."""

    def test_resumable_upload_uses_explicit_chunk_size_and_reports_real_bytes(
        self,
        mock_gdrive: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Resumable progress starts at zero, advances by acknowledged bytes, and ends at 100%."""
        import youtube_clipper.gdrive_uploader as gdu

        clip_path = tmp_path / "progress_clip.mp4"
        clip_path.write_bytes(b"x" * 4000)
        total_bytes = clip_path.stat().st_size
        emitted_events: list[dict] = []
        media_calls: list[tuple[str, dict]] = []

        class FakeProgress:
            def __init__(self, uploaded_bytes: int) -> None:
                self.resumable_progress = uploaded_bytes
                self.total_size = total_bytes

            def progress(self) -> float:
                return self.resumable_progress / self.total_size

        class FakeHttpRequest:
            def __init__(self) -> None:
                self.responses = [
                    (FakeProgress(1000), None),
                    (FakeProgress(2500), None),
                    (
                        None,
                        {
                            "id": "file_progress",
                            "name": clip_path.name,
                            "webViewLink": "https://drive.google.com/file/d/file_progress/view",
                            "webContentLink": "https://drive.google.com/uc?id=file_progress",
                            "size": str(total_bytes),
                        },
                    ),
                ]

            def next_chunk(self) -> tuple[FakeProgress | None, dict | None]:
                return self.responses.pop(0)

        request = FakeHttpRequest()
        mock_gdrive.files().create.return_value = request
        monkeypatch.setattr(gdu, "HttpRequest", FakeHttpRequest)
        monkeypatch.setattr(
            gdu,
            "emit_event",
            lambda *args, **kwargs: emitted_events.append(dict(kwargs)),
        )

        def capture_media(file_path: str, **kwargs: object) -> object:
            media_calls.append((file_path, dict(kwargs)))
            return object()

        monkeypatch.setattr(gdu, "MediaFileUpload", capture_media)
        sa_path = tmp_path / "sa-progress.json"
        sa_path.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))
        result = uploader.upload_clip(str(clip_path), folder_id="folder_progress")

        assert result["success"] is True
        assert result["permission_configured"] is True
        assert len(media_calls) == 1
        assert media_calls[0][0] == str(clip_path)
        assert media_calls[0][1]["resumable"] is True
        assert media_calls[0][1]["chunksize"] == gdu.DRIVE_UPLOAD_CHUNK_SIZE
        assert gdu.DRIVE_UPLOAD_CHUNK_SIZE % (256 * 1024) == 0

        progress_events = [
            event
            for event in emitted_events
            if str(event.get("action", "")).startswith("gdrive.upload.progress.")
        ]
        decisions = [event["decision"] for event in progress_events]
        assert [decision["progress_percent"] for decision in decisions] == [
            0.0,
            25.0,
            62.5,
            100.0,
        ]
        uploaded_values = [decision["uploaded_bytes"] for decision in decisions]
        assert uploaded_values == [0, 1000, 2500, total_bytes]
        assert uploaded_values == sorted(uploaded_values)
        assert all(decision["total_bytes"] == total_bytes for decision in decisions)
        assert all(decision["indeterminate"] is False for decision in decisions)

    def test_non_resumable_fallback_is_indeterminate_until_execute_completes(
        self,
        mock_gdrive: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A transport without next_chunk must not invent intermediate upload percentages."""
        import youtube_clipper.gdrive_uploader as gdu

        clip_path = tmp_path / "fallback_clip.mp4"
        clip_path.write_bytes(b"fallback upload")
        total_bytes = clip_path.stat().st_size
        emitted_events: list[dict] = []

        class ResumableHttpRequest:
            pass

        class ExecuteOnlyRequest:
            def execute(self) -> dict:
                return {
                    "id": "file_fallback",
                    "name": clip_path.name,
                    "webViewLink": "https://drive.google.com/file/d/file_fallback/view",
                    "webContentLink": "https://drive.google.com/uc?id=file_fallback",
                    "size": str(total_bytes),
                }

        mock_gdrive.files().create.return_value = ExecuteOnlyRequest()
        monkeypatch.setattr(gdu, "HttpRequest", ResumableHttpRequest)
        monkeypatch.setattr(gdu, "MediaFileUpload", lambda *args, **kwargs: object())
        monkeypatch.setattr(
            gdu,
            "emit_event",
            lambda *args, **kwargs: emitted_events.append(dict(kwargs)),
        )
        sa_path = tmp_path / "sa-fallback.json"
        sa_path.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))
        result = uploader.upload_clip(str(clip_path), folder_id="folder_fallback")

        assert result["success"] is True
        progress_events = [
            event
            for event in emitted_events
            if str(event.get("action", "")).startswith("gdrive.upload.progress.")
        ]
        assert [event["action"] for event in progress_events] == [
            "gdrive.upload.progress.indeterminate",
            "gdrive.upload.progress.complete",
        ]
        indeterminate, completed = [event["decision"] for event in progress_events]
        assert indeterminate == {
            "progress_percent": None,
            "uploaded_bytes": None,
            "total_bytes": total_bytes,
            "chunk_number": 0,
            "indeterminate": True,
        }
        assert completed == {
            "progress_percent": 100.0,
            "uploaded_bytes": total_bytes,
            "total_bytes": total_bytes,
            "chunk_number": 0,
            "indeterminate": False,
        }

    def test_upload_clip_existing_folder(
        self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path
    ) -> None:
        """Test file upload when target folder 'YouTube_Clips' already exists."""
        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))
        result = uploader.upload_clip(str(dummy_video_file), folder_name="YouTube_Clips")

        assert result["success"] is True
        assert result["file_id"] == "file_456"
        assert result["file_name"] in ("sample_video.mp4", "test_clip.mp4")
        assert "webViewLink" in result["web_view_link"] or "drive.google.com" in result["web_view_link"]

    def test_upload_clip_creates_new_folder(
        self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test file upload when target folder does not exist and must be created."""
        import youtube_clipper.gdrive_uploader as gdu

        monkeypatch.setattr(gdu, "DEFAULT_TARGET_FOLDER_ID", "")
        # Configure mock_gdrive files.list to return empty folder list
        mock_gdrive.files().list().execute.return_value = {"files": []}
        mock_gdrive.files().create().execute.side_effect = [
            {"id": "new_folder_789"},  # First create call: folder creation
            {
                "id": "file_999",
                "name": "sample_video.mp4",
                "webViewLink": "https://drive.google.com/file/d/file_999/view",
                "webContentLink": "https://drive.google.com/uc?id=file_999",
                "size": "2048",
            },  # Second create call: file upload
        ]

        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))
        result = uploader.upload_clip(str(dummy_video_file), folder_name="New_Clips_Folder")

        assert result["success"] is True
        assert result["file_id"] == "file_999"

    def test_upload_clip_with_folder_id(
        self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path
    ) -> None:
        """Test upload_clip accepts folder_id parameter without TypeError and uses folder_id."""
        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))
        result = uploader.upload_clip(str(dummy_video_file), folder_id="custom_folder_id_123")

        assert result["success"] is True
        assert result["file_id"] == "file_456"

    def test_upload_clip_with_folder_id_and_folder_name(
        self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path
    ) -> None:
        """Test upload_clip accepts both folder_id and folder_name without TypeError."""
        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))
        result = uploader.upload_clip(
            str(dummy_video_file),
            folder_id="folder_id_xyz",
            folder_name="Custom_Folder_Name",
        )

        assert result["success"] is True
        assert result["file_id"] == "file_456"

    def test_upload_clip_missing_video_file_raises_file_not_found(
        self, mock_gdrive: MagicMock, tmp_path: Path
    ) -> None:
        """Test uploading a non-existent video clip file raises FileNotFoundError."""
        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))
        missing_clip = str(tmp_path / "non_existent_clip.mp4")

        with pytest.raises(FileNotFoundError, match="Clip file not found for upload"):
            uploader.upload_clip(missing_clip)

    def test_upload_clip_storage_quota_exceeded_raises_descriptive_error(
        self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path
    ) -> None:
        """Test that storageQuotaExceeded 403 error raises GoogleDriveUploadError with user guidance."""
        from googleapiclient.errors import HttpError
        from httplib2 import Response
        from youtube_clipper.gdrive_uploader import GoogleDriveUploadError

        resp = Response({"status": 403, "content-type": "application/json"})
        content = b'{"error": {"code": 403, "message": "The user\'s drive storage quota has been exceeded.", "errors": [{"reason": "storageQuotaExceeded"}]}}'
        http_err = HttpError(resp, content)

        mock_gdrive.files().create().execute.side_effect = http_err

        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')
        uploader = GoogleDriveUploader(service_account_path=str(sa_path))

        with pytest.raises(GoogleDriveUploadError, match="storage quota exceeded"):
            uploader.upload_clip(str(dummy_video_file))


class TestGoogleDriveAuthTiers:
    """Test suite for 3-tier authentication resolution in GoogleDriveUploader."""

    def test_tier_1_env_vars_auth(
        self, monkeypatch: pytest.MonkeyPatch, mock_gdrive: MagicMock
    ) -> None:
        """Test Tier 1 auth using GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN."""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "test_refresh_token")
        monkeypatch.setattr("youtube_clipper.gdrive_uploader.DEFAULT_SERVICE_ACCOUNT_PATH", "/nonexistent/sa.json")

        uploader = GoogleDriveUploader()
        assert uploader.credentials is not None
        assert uploader.credentials.refresh_token == "test_refresh_token"

    def test_tier_2_corrupted_token_json_falls_back_to_tier_3(
        self, monkeypatch: pytest.MonkeyPatch, mock_gdrive: MagicMock, tmp_path: Path
    ) -> None:
        """Test Tier 2 corrupted token.json logs warning and falls back to Tier 3 service account."""
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)

        corrupted_token = tmp_path / "corrupted_token.json"
        corrupted_token.write_text("INVALID JSON CONTENT")

        sa_path = tmp_path / "valid_sa.json"
        sa_path.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(
            service_account_path=str(sa_path), token_path=str(corrupted_token)
        )
        assert uploader.service_account_path == str(sa_path)
        assert uploader.service is not None


class TestGoogleDriveUploadHelper:
    """Test suite for upload_clip_to_gdrive helper function."""

    def test_upload_clip_to_gdrive_success(
        self, mock_gdrive: MagicMock, dummy_video_file: Path
    ) -> None:
        """Test high-level helper function returning successful upload result dictionary."""
        result = upload_clip_to_gdrive(str(dummy_video_file))
        assert result["success"] is True
        assert "file_id" in result
        assert "web_view_link" in result

    def test_upload_clip_to_gdrive_missing_credentials_returns_error_dict(
        self, monkeypatch: pytest.MonkeyPatch, tmp_media_dir: Path, dummy_video_file: Path
    ) -> None:
        """Test high-level helper function returning error dict when credentials file is missing."""
        import youtube_clipper.gdrive_uploader as gdu

        monkeypatch.setattr(gdu, "DEFAULT_SERVICE_ACCOUNT_PATH", "/non/existent/path/sa.json")
        monkeypatch.setattr(gdu, "DEFAULT_TOKEN_PATH", "/non/existent/path/token.json")
        monkeypatch.setattr(
            "google.auth.default",
            MagicMock(side_effect=Exception("ADC unavailable for this missing-credentials case")),
        )
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GOOGLE_TOKEN_FILE", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)

        result = upload_clip_to_gdrive(str(dummy_video_file))
        assert result["success"] is False
        assert "error" in result


class TestGoogleDriveUploaderConcurrency:
    """Test suite for thread concurrency in GoogleDriveUploader."""

    def test_concurrent_uploads(
        self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path
    ) -> None:
        """Test multiple concurrent uploads using ThreadPoolExecutor."""
        from concurrent.futures import ThreadPoolExecutor

        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))

        def upload_task(index: int) -> dict:
            return uploader.upload_clip(str(dummy_video_file), folder_name="YouTube_Clips")

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(upload_task, i) for i in range(8)]
            results = [f.result() for f in futures]

        assert len(results) == 8
        for res in results:
            assert res["success"] is True
            assert "file_id" in res


