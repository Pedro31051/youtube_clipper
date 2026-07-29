"""
tests/test_gdrive_uploader.py - Unit and integration tests for GoogleDriveUploader.
Tests service account authentication, folder checking/creation, file upload,
and exception handling.
"""

from pathlib import Path
from unittest.mock import MagicMock
import pytest
from youtube_clipper.gdrive_uploader import (
    GoogleDriveUploader,
    SCOPES,
    upload_clip_to_gdrive,
)


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
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
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




def test_drive_scope_is_least_privilege() -> None:
    assert SCOPES == ["https://www.googleapis.com/auth/drive.file"]


def test_upload_is_private_by_default(
    mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path
) -> None:
    credential = tmp_path / "sa-private.json"
    credential.write_text('{"type": "service_account"}')
    uploader = GoogleDriveUploader(service_account_path=str(credential))
    permission_create = mock_gdrive.permissions.return_value.create
    permission_create.reset_mock()

    result = uploader.upload_clip(str(dummy_video_file))

    assert result["success"] is True
    assert result["public_link_enabled"] is False
    permission_create.assert_not_called()


def test_public_link_requires_explicit_opt_in(
    mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path
) -> None:
    credential = tmp_path / "sa-public.json"
    credential.write_text('{"type": "service_account"}')
    uploader = GoogleDriveUploader(service_account_path=str(credential))
    permission_create = mock_gdrive.permissions.return_value.create
    permission_create.reset_mock()

    result = uploader.upload_clip(str(dummy_video_file), public_link=True)

    assert result["success"] is True
    assert result["public_link_enabled"] is True
    permission_create.assert_called_once_with(
        fileId="file_456",
        body={"type": "anyone", "role": "reader"},
        supportsAllDrives=True,
    )
