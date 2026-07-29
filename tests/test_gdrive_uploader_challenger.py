"""
tests/test_gdrive_uploader_challenger.py - Adversarial stress tests for GoogleDriveUploader.
Tests thread safety, multi-threading, target folder ID behavior, token refresh concurrency,
and API error boundary handling.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

import youtube_clipper.gdrive_uploader as gdu
from youtube_clipper.gdrive_uploader import GoogleDriveUploader, upload_clip_to_gdrive, GoogleDriveUploadError


class TestFolderIdBehaviorAdversarial:
    """Adversarial tests for folder_id parameter and default target folder ID handling."""

    def test_folder_id_supplied(self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path) -> None:
        """When folder_id is supplied explicitly, parents must be set to that folder_id."""
        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))
        result = uploader.upload_clip(str(dummy_video_file), folder_id="EXPLICIT_FOLDER_123")

        assert result["success"] is True
        # Verify body passed to files().create
        create_args = mock_gdrive.files().create.call_args
        body = create_args[1].get("body", {}) if create_args[1] else create_args[0][0]
        assert body["parents"] == ["EXPLICIT_FOLDER_123"]

    def test_folder_id_omitted(self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path) -> None:
        """When folder_id is omitted, default folder ID 1mYLUnTMhdflzmYhee804Nj52jBQuOI8H must be used."""
        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))
        result = uploader.upload_clip(str(dummy_video_file))

        assert result["success"] is True
        create_args = mock_gdrive.files().create.call_args
        body = create_args[1].get("body", {}) if create_args[1] else create_args[0][0]
        assert body["parents"] == ["1mYLUnTMhdflzmYhee804Nj52jBQuOI8H"]

    def test_folder_id_explicit_none(self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path) -> None:
        """When folder_id=None is passed explicitly, default folder ID 1mYLUnTMhdflzmYhee804Nj52jBQuOI8H must be used."""
        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))
        result = uploader.upload_clip(str(dummy_video_file), folder_id=None)

        assert result["success"] is True
        create_args = mock_gdrive.files().create.call_args
        body = create_args[1].get("body", {}) if create_args[1] else create_args[0][0]
        assert body["parents"] == ["1mYLUnTMhdflzmYhee804Nj52jBQuOI8H"]

    def test_folder_id_empty_string(self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path) -> None:
        """When folder_id="" is passed, folder_id or DEFAULT_TARGET_FOLDER_ID falls back to default folder ID."""
        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))
        result = uploader.upload_clip(str(dummy_video_file), folder_id="")

        assert result["success"] is True
        create_args = mock_gdrive.files().create.call_args
        body = create_args[1].get("body", {}) if create_args[1] else create_args[0][0]
        assert body["parents"] == ["1mYLUnTMhdflzmYhee804Nj52jBQuOI8H"]

    def test_folder_name_ignored_when_default_folder_id_present(
        self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path
    ) -> None:
        """Verify that passing folder_name when DEFAULT_TARGET_FOLDER_ID is set does NOT trigger folder search/create."""
        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))
        mock_gdrive.files().list.reset_mock()
        result = uploader.upload_clip(str(dummy_video_file), folder_name="Custom_Folder_Name")

        assert result["success"] is True
        # files().list should NOT have been called during upload_clip because target_folder_id was resolved from DEFAULT_TARGET_FOLDER_ID
        mock_gdrive.files().list.assert_not_called()
        create_args = mock_gdrive.files().create.call_args
        body = create_args[1].get("body", {}) if create_args[1] else create_args[0][0]
        assert body["parents"] == ["1mYLUnTMhdflzmYhee804Nj52jBQuOI8H"]

    def test_folder_name_used_when_default_folder_id_empty(
        self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When DEFAULT_TARGET_FOLDER_ID is empty string, folder_name triggers search and fallback creation."""
        monkeypatch.setattr(gdu, "DEFAULT_TARGET_FOLDER_ID", "")
        mock_gdrive.files().list().execute.return_value = {"files": []}
        mock_gdrive.files().create().execute.side_effect = [
            {"id": "CREATED_FOLDER_99"},
            {
                "id": "UPLOADED_FILE_11",
                "name": dummy_video_file.name,
                "webViewLink": "https://drive.google.com/view/11",
                "webContentLink": "https://drive.google.com/uc/11",
                "size": "100",
            },
        ]

        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))
        mock_gdrive.files().list.reset_mock()
        result = uploader.upload_clip(str(dummy_video_file), folder_id=None, folder_name="MyDynamicFolder")

        assert result["success"] is True
        assert result["file_id"] == "UPLOADED_FILE_11"
        mock_gdrive.files().list.assert_called_once()


class TestMultiThreadingAndConcurrencyAdversarial:
    """Adversarial stress tests for multi-threading, concurrency, and async context execution."""

    def test_upload_clip_async_existence_check(self) -> None:
        """Empirically test whether upload_clip_async exists in gdrive_uploader module."""
        has_async_fn = hasattr(gdu, "upload_clip_async") or hasattr(GoogleDriveUploader, "upload_clip_async")
        # Record result: upload_clip_async is NOT implemented in gdrive_uploader.py
        # System relies on sync upload_clip / upload_clip_to_gdrive or threading.
        assert not has_async_fn, "upload_clip_async function exists in module, but prompt asked to verify behavior"

    def test_concurrent_uploads_single_uploader_instance(
        self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path
    ) -> None:
        """Stress test 25 concurrent threads calling upload_clip on a single GoogleDriveUploader instance."""
        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))
        num_threads = 25

        def worker(i: int) -> dict:
            return uploader.upload_clip(str(dummy_video_file), folder_id=f"folder_{i}")

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker, i) for i in range(num_threads)]
            results = [f.result() for f in futures]

        assert len(results) == num_threads
        assert all(res["success"] is True for res in results)
        assert mock_gdrive.files().create.call_count >= num_threads

    def test_concurrent_uploads_helper_function(
        self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path
    ) -> None:
        """Stress test 20 concurrent threads invoking upload_clip_to_gdrive helper function."""
        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')

        with patch.object(gdu, "DEFAULT_SERVICE_ACCOUNT_PATH", str(sa_path)):
            def worker(i: int) -> dict:
                return upload_clip_to_gdrive(str(dummy_video_file), folder_id=f"folder_helper_{i}")

            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(worker, i) for i in range(20)]
                results = [f.result() for f in futures]

            assert len(results) == 20
            assert all(res["success"] is True for res in results)

    def test_asyncio_thread_execution(
        self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path
    ) -> None:
        """Test concurrent execution of upload_clip via asyncio.to_thread in an event loop."""
        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))

        async def async_worker(i: int) -> dict:
            return await asyncio.to_thread(
                uploader.upload_clip, str(dummy_video_file), folder_id=f"async_folder_{i}"
            )

        async def main():
            tasks = [async_worker(i) for i in range(15)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(main())
        assert len(results) == 15
        assert all(res["success"] is True for res in results)


class TestPermissionsAndErrorHandlingAdversarial:
    """Adversarial tests for Google Drive API error handling and permission failure resilience."""

    def test_permission_creation_failure_does_not_fail_upload(
        self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path
    ) -> None:
        """If permissions().create() raises an exception (e.g. domain policy), upload must still succeed."""
        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')

        # Simulate failure during permission creation
        resp = Response({"status": 403, "content-type": "application/json"})
        perm_err = HttpError(resp, b'{"error": {"message": "Domain policy prohibits sharing outside organization."}}')
        mock_gdrive.permissions().create().execute.side_effect = perm_err

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))
        result = uploader.upload_clip(str(dummy_video_file))

        # The bytes remain uploaded, but public sharing must be reported honestly.
        assert result["success"] is True
        assert result["file_id"] == "file_456"
        assert result["permission_configured"] is False

    def test_generic_http_error_handling(
        self, mock_gdrive: MagicMock, tmp_path: Path, dummy_video_file: Path
    ) -> None:
        """Non-quota HttpError (e.g. 500 Internal Server Error) raises GoogleDriveUploadError without quota guidance."""
        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')

        resp = Response({"status": 500, "content-type": "application/json"})
        http_err = HttpError(resp, b'{"error": {"message": "Backend Error"}}')
        mock_gdrive.files().create().execute.side_effect = http_err

        uploader = GoogleDriveUploader(service_account_path=str(sa_path))

        with pytest.raises(GoogleDriveUploadError) as exc_info:
            uploader.upload_clip(str(dummy_video_file))

        assert "Failed to upload clip to Google Drive" in str(exc_info.value)
        assert "storage quota" not in str(exc_info.value)
