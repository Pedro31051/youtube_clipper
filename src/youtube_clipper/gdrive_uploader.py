"""
Google Drive Uploader Integration Module for YouTube Clipper.
Uploads generated video clips directly to Google Drive using either OAuth2 User credentials
or Service Account credentials configured in google_drive_mcp.
"""

import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "youtube_clipper"
DEFAULT_SERVICE_ACCOUNT_PATH = str(DEFAULT_CONFIG_DIR / "service-account.json")
DEFAULT_TOKEN_PATH = str(DEFAULT_CONFIG_DIR / "token.json")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
DEFAULT_TARGET_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "1mYLUnTMhdflzmYhee804Nj52jBQuOI8H")


class GoogleDriveUploadError(Exception):
    """Exception raised when Google Drive upload fails."""
    pass


class GoogleDriveUploader:
    """Handles Google Drive authentication and video clip file uploads."""

    def __init__(
        self,
        service_account_path: Optional[str] = None,
        token_path: Optional[str] = None,
    ):
        self.service_account_path = (
            service_account_path
            or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            or DEFAULT_SERVICE_ACCOUNT_PATH
        )
        self.token_path = token_path or os.environ.get("GOOGLE_TOKEN_FILE") or DEFAULT_TOKEN_PATH

        self.credentials = None

        # Tier 1: OAuth2 Environment Variables
        client_id = os.environ.get("GOOGLE_CLIENT_ID")
        client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
        refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN")

        if client_id and client_secret and refresh_token:
            try:
                self.credentials = Credentials(
                    token=None,
                    refresh_token=refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=client_id,
                    client_secret=client_secret,
                    scopes=SCOPES,
                )
            except Exception as exc:
                logger.warning(f"Failed to load OAuth2 credentials from environment variables: {exc}")
                self.credentials = None

        # Tier 2: Authorized user token file (token.json) wrapped in try...except for graceful fallback
        if self.credentials is None and self.token_path and os.path.exists(self.token_path):
            try:
                self.credentials = Credentials.from_authorized_user_file(self.token_path, scopes=SCOPES)
            except Exception as exc:
                logger.warning(f"Failed to load token file at {self.token_path}: {exc}")
                self.credentials = None

        # Tier 3: Service Account JSON fallback
        if self.credentials is None and self.service_account_path and os.path.exists(self.service_account_path):
            try:
                self.credentials = service_account.Credentials.from_service_account_file(
                    self.service_account_path, scopes=SCOPES
                )
            except Exception as exc:
                raise GoogleDriveUploadError(f"Failed to load Service Account JSON: {exc}") from exc

        # No valid credentials loaded across all 3 tiers
        if self.credentials is None:
            raise FileNotFoundError(
                f"Service Account JSON file not found at: {self.service_account_path}"
            )

        try:
            self.service = build("drive", "v3", credentials=self.credentials)
        except Exception as exc:
            raise GoogleDriveUploadError(f"Failed to authenticate Google Drive client: {exc}") from exc

    def upload_clip(
        self,
        file_path: str,
        folder_id: Optional[str] = None,
        folder_name: Optional[str] = "YouTube_Clips",
        public_link: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Uploads a clip MP4 file to Google Drive.
        Accepts folder_id or folder_name to specify target Drive folder.
        Defaults to DEFAULT_TARGET_FOLDER_ID ("1mYLUnTMhdflzmYhee804Nj52jBQuOI8H") if folder_id is None.
        Creates target folder only if folder_id and DEFAULT_TARGET_FOLDER_ID are absent/empty.
        Returns metadata dictionary including Google Drive web link.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Clip file not found for upload: {file_path}")

        file_name = os.path.basename(file_path)

        try:
            target_folder_id = folder_id or DEFAULT_TARGET_FOLDER_ID
            if not target_folder_id:
                fname = folder_name or "YouTube_Clips"
                # Find or create folder in Google Drive
                query = f"name = '{fname}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
                results = self.service.files().list(
                    q=query, fields="files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True
                ).execute()
                folders = results.get("files", [])

                if folders:
                    target_folder_id = folders[0]["id"]
                else:
                    folder_metadata = {
                        "name": fname,
                        "mimeType": "application/vnd.google-apps.folder"
                    }
                    folder = self.service.files().create(
                        body=folder_metadata, fields="id", supportsAllDrives=True
                    ).execute()
                    target_folder_id = folder.get("id")

            # Upload file to target folder
            file_metadata = {
                "name": file_name,
                "parents": [target_folder_id]
            }
            media = MediaFileUpload(file_path, mimetype="video/mp4", resumable=True)

            uploaded_file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, name, webViewLink, webContentLink, size",
                supportsAllDrives=True
            ).execute()

            public_link_created = False
            if public_link:
                try:
                    permission = {"type": "anyone", "role": "reader"}
                    self.service.permissions().create(
                        fileId=uploaded_file["id"],
                        body=permission,
                        supportsAllDrives=True,
                    ).execute()
                    public_link_created = True
                except Exception as perm_err:
                    logger.warning(
                        f"Failed to set public permission on file "
                        f"{uploaded_file.get('id')}: {perm_err}"
                    )

            return {
                "status": "success",
                "success": True,
                "file_id": uploaded_file.get("id"),
                "file_name": uploaded_file.get("name"),
                "web_view_link": uploaded_file.get("webViewLink"),
                "web_content_link": uploaded_file.get("webContentLink"),
                "size_bytes": uploaded_file.get("size"),
                "public_link_enabled": public_link_created,
            }
        except FileNotFoundError:
            raise
        except HttpError as e:
            err_str = str(e)
            if e.resp.status == 403 or "storageQuotaExceeded" in err_str or "quota" in err_str.lower():
                raise GoogleDriveUploadError(
                    f"Google Drive storage quota exceeded (HTTP 403). Service accounts have 0 bytes storage limit. "
                    f"Please configure OAuth2 user credentials (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN or token.json) "
                    f"to upload files using user quota: {e}"
                ) from e
            raise GoogleDriveUploadError(f"Failed to upload clip to Google Drive: {e}") from e
        except Exception as e:
            err_str = str(e)
            if "storageQuotaExceeded" in err_str or ("403" in err_str and "quota" in err_str.lower()):
                raise GoogleDriveUploadError(
                    f"Google Drive storage quota exceeded (HTTP 403). Service accounts have 0 bytes storage limit. "
                    f"Please configure OAuth2 user credentials (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN or token.json) "
                    f"to upload files using user quota: {e}"
                ) from e
            raise GoogleDriveUploadError(f"Failed to upload clip to Google Drive: {e}") from e


def upload_clip_to_gdrive(
    file_path: str,
    folder_id: Optional[str] = None,
    folder_name: Optional[str] = "YouTube_Clips",
    public_link: bool = False,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Helper function to upload clip to Google Drive."""
    try:
        uploader = GoogleDriveUploader()
        return uploader.upload_clip(
            file_path,
            folder_id=folder_id,
            folder_name=folder_name,
            public_link=public_link,
            **kwargs,
        )
    except Exception as e:
        return {
            "status": "error",
            "success": False,
            "error": str(e)
        }

