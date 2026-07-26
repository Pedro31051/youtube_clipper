"""
Adversarial Stress Tests for YouTube Clipper Google Drive Uploader.
Empirically tests edge cases, corrupt files, missing credentials, and HttpErrors.
"""

from pathlib import Path
from unittest.mock import MagicMock
import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from youtube_clipper.gdrive_uploader import (
    GoogleDriveUploader,
    GoogleDriveUploadError,
    upload_clip_to_gdrive,
)


class TestAdversarialTokenAndServiceAccountFallback:
    """Stress tests for Tier 1 / Tier 2 / Tier 3 authentication fallback and corruption handling."""

    def test_corrupted_token_json_with_valid_sa_falls_back(
        self, monkeypatch: pytest.MonkeyPatch, mock_gdrive: MagicMock, tmp_path: Path
    ) -> None:
        """Verify malformed JSON in token.json gracefully falls back to Service Account."""
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)

        bad_token = tmp_path / "token.json"
        bad_token.write_text("{malformed: json, missing quotes}")

        valid_sa = tmp_path / "service_account.json"
        valid_sa.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(
            service_account_path=str(valid_sa), token_path=str(bad_token)
        )
        assert uploader.service is not None

    def test_empty_token_json_with_valid_sa_falls_back(
        self, monkeypatch: pytest.MonkeyPatch, mock_gdrive: MagicMock, tmp_path: Path
    ) -> None:
        """Verify 0-byte empty token.json gracefully falls back to Service Account."""
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)

        empty_token = tmp_path / "token.json"
        empty_token.write_text("")

        valid_sa = tmp_path / "service_account.json"
        valid_sa.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(
            service_account_path=str(valid_sa), token_path=str(empty_token)
        )
        assert uploader.service is not None

    def test_empty_dict_token_json_with_valid_sa_falls_back(
        self, monkeypatch: pytest.MonkeyPatch, mock_gdrive: MagicMock, tmp_path: Path
    ) -> None:
        """Verify token.json with empty dict `{}` gracefully falls back to Service Account."""
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)

        empty_dict_token = tmp_path / "token.json"
        empty_dict_token.write_text("{}")

        valid_sa = tmp_path / "service_account.json"
        valid_sa.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(
            service_account_path=str(valid_sa), token_path=str(empty_dict_token)
        )
        assert uploader.service is not None

    def test_corrupted_token_json_and_missing_sa_raises_file_not_found(
        self, monkeypatch: pytest.MonkeyPatch, mock_gdrive: MagicMock, tmp_path: Path
    ) -> None:
        """Verify corrupted token.json + missing service-account.json raises FileNotFoundError."""
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)

        bad_token = tmp_path / "token.json"
        bad_token.write_text("CORRUPTED")

        missing_sa = str(tmp_path / "non_existent_sa.json")

        with pytest.raises(FileNotFoundError, match="Service Account JSON file not found"):
            GoogleDriveUploader(service_account_path=missing_sa, token_path=str(bad_token))

    def test_missing_token_and_missing_sa_raises_file_not_found(
        self, monkeypatch: pytest.MonkeyPatch, mock_gdrive: MagicMock, tmp_path: Path
    ) -> None:
        """Verify missing token.json + missing service-account.json raises FileNotFoundError."""
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)

        missing_token = str(tmp_path / "no_token.json")
        missing_sa = str(tmp_path / "no_sa.json")

        with pytest.raises(FileNotFoundError, match="Service Account JSON file not found"):
            GoogleDriveUploader(service_account_path=missing_sa, token_path=missing_token)

    def test_corrupted_sa_raises_gdrive_upload_error(
        self, monkeypatch: pytest.MonkeyPatch, mock_gdrive: MagicMock, tmp_path: Path
    ) -> None:
        """Verify corrupted service-account.json raises GoogleDriveUploadError when token is missing/invalid."""
        monkeypatch.setattr(
            "google.oauth2.service_account.Credentials.from_service_account_file",
            MagicMock(side_effect=ValueError("Invalid JSON")),
        )

        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)

        missing_token = str(tmp_path / "nonexistent_token.json")
        corrupted_sa = tmp_path / "corrupted_sa.json"
        corrupted_sa.write_text("INVALID JSON FOR SA")

        with pytest.raises(GoogleDriveUploadError, match="Failed to load Service Account JSON"):
            GoogleDriveUploader(service_account_path=str(corrupted_sa), token_path=missing_token)


class TestAdversarialHttpErrorQuotaHandling:
    """Stress tests for HttpError 403 and storageQuotaExceeded handling."""

    def test_httperror_403_status_only_raises_descriptive_gdrive_error(
        self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path
    ) -> None:
        """HttpError with status 403 (even without storageQuotaExceeded in body) raises descriptive quota error."""
        resp = Response({"status": 403, "content-type": "application/json"})
        content = b'{"error": {"code": 403, "message": "Forbidden"}}'
        http_err = HttpError(resp, content)

        mock_gdrive.files().create().execute.side_effect = http_err

        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')
        uploader = GoogleDriveUploader(service_account_path=str(sa_path))

        with pytest.raises(GoogleDriveUploadError) as exc_info:
            uploader.upload_clip(str(dummy_video_file))

        assert "Google Drive storage quota exceeded (HTTP 403)" in str(exc_info.value)
        assert "Service accounts have 0 bytes storage limit" in str(exc_info.value)

    def test_httperror_with_storage_quota_exceeded_in_body_raises_descriptive_error(
        self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path
    ) -> None:
        """HttpError with storageQuotaExceeded string raises descriptive error."""
        resp = Response({"status": 403, "content-type": "application/json"})
        content = b'{"error": {"code": 403, "message": "The user\'s drive storage quota has been exceeded.", "errors": [{"reason": "storageQuotaExceeded"}]}}'
        http_err = HttpError(resp, content)

        mock_gdrive.files().create().execute.side_effect = http_err

        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')
        uploader = GoogleDriveUploader(service_account_path=str(sa_path))

        with pytest.raises(GoogleDriveUploadError) as exc_info:
            uploader.upload_clip(str(dummy_video_file))

        assert "storage quota exceeded" in str(exc_info.value).lower()
        assert "GOOGLE_CLIENT_ID" in str(exc_info.value)

    def test_permission_creation_failure_is_non_fatal(
        self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path
    ) -> None:
        """Verify permission creation HTTP error is logged as warning and does not break upload."""
        resp = Response({"status": 403, "content-type": "application/json"})
        content = b'{"error": {"code": 403, "message": "Cannot share file"}}'
        http_err = HttpError(resp, content)

        mock_gdrive.permissions().create().execute.side_effect = http_err

        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')
        uploader = GoogleDriveUploader(service_account_path=str(sa_path))

        result = uploader.upload_clip(str(dummy_video_file))
        assert result["success"] is True
        assert result["file_id"] == "file_456"
