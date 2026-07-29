"""
Google Drive Uploader Integration Module for YouTube Clipper.
Uploads generated video clips directly to Google Drive using either OAuth2 User credentials
or Service Account credentials configured in google_drive_mcp.
"""

import logging
import os
import time
from typing import Dict, Any, Optional
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import HttpRequest, MediaFileUpload

from cortes.log import action_span, emit_event, emit_skipped, run_context

logger = logging.getLogger(__name__)

DEFAULT_SERVICE_ACCOUNT_PATH = "/home/pedrofelipealvesrocha/teamwork_projects/google_drive_mcp/service-account.json"
DEFAULT_TOKEN_PATH = "/home/pedrofelipealvesrocha/teamwork_projects/google_drive_mcp/token.json"
SCOPES = ["https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
DEFAULT_TARGET_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "1mYLUnTMhdflzmYhee804Nj52jBQuOI8H")
# Google requires resumable chunks to be multiples of 256 KiB. Four MiB gives
# useful progress updates for the typical 8-15 MiB Shorts produced here.
DRIVE_UPLOAD_CHUNK_SIZE = 4 * 1024 * 1024


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
                with action_span(
                    "env", "gdrive.auth.oauth_env",
                    component="youtube_clipper.gdrive",
                    next_action="gdrive.build_client", next_stage="env",
                    input_data={"credentials_present": True},
                ) as span:
                    self.credentials = Credentials(
                        token=None,
                        refresh_token=refresh_token,
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=client_id,
                        client_secret=client_secret,
                        scopes=SCOPES,
                    )
                    span.decision = {"selected_auth_method": "oauth_environment"}
            except Exception as exc:
                logger.warning(f"Failed to load OAuth2 credentials from environment variables: {exc}")
                self.credentials = None
        else:
            emit_skipped(
                "env", "gdrive.auth.oauth_env",
                "one or more OAuth environment variables are absent",
                component="youtube_clipper.gdrive",
                next_action="gdrive.auth.token_file", next_stage="env",
            )

        # Tier 2: Authorized user token file (token.json) wrapped in try...except for graceful fallback
        if self.credentials is None and self.token_path and os.path.exists(self.token_path):
            try:
                with action_span(
                    "env", "gdrive.auth.token_file",
                    component="youtube_clipper.gdrive",
                    next_action="gdrive.build_client", next_stage="env",
                    input_data={"token_file_present": True},
                ) as span:
                    self.credentials = Credentials.from_authorized_user_file(
                        self.token_path, scopes=SCOPES
                    )
                    span.decision = {"selected_auth_method": "oauth_token_file"}
            except Exception as exc:
                logger.warning(f"Failed to load token file at {self.token_path}: {exc}")
                self.credentials = None
        elif self.credentials is not None:
            emit_skipped(
                "env", "gdrive.auth.token_file",
                "a higher-priority OAuth method succeeded",
                component="youtube_clipper.gdrive",
                next_action="gdrive.build_client", next_stage="env",
            )
        else:
            emit_skipped(
                "env", "gdrive.auth.token_file",
                "authorized-user token file is absent",
                component="youtube_clipper.gdrive",
                next_action="gdrive.auth.adc", next_stage="env",
            )

        # Tier 2.5: Application Default Credentials (ADC) fallback
        if self.credentials is None:
            try:
                import google.auth
                import google.auth.compute_engine.credentials
                with action_span(
                    "env", "gdrive.auth.adc",
                    component="youtube_clipper.gdrive",
                    next_action="gdrive.build_client" if self.credentials else "gdrive.auth.service_account",
                    next_stage="env",
                    input_data={"adc_check": True},
                ) as span:
                    adc_creds, _ = google.auth.default(scopes=SCOPES)
                    if not isinstance(adc_creds, google.auth.compute_engine.credentials.Credentials):
                        self.credentials = adc_creds
                        span.decision = {"selected_auth_method": "adc_user"}
                    else:
                        emit_skipped(
                            "env", "gdrive.auth.adc",
                            "ADC is a Compute Engine Service Account; skipping in favor of explicit Service Account JSON or other methods",
                            component="youtube_clipper.gdrive",
                            next_action="gdrive.auth.service_account", next_stage="env",
                        )
            except Exception as exc:
                logger.info(f"Failed to load Application Default Credentials (ADC): {exc}")

        # Tier 3: Service Account JSON fallback
        if self.credentials is None and self.service_account_path and os.path.exists(self.service_account_path):
            try:
                with action_span(
                    "env", "gdrive.auth.service_account",
                    component="youtube_clipper.gdrive",
                    next_action="gdrive.build_client", next_stage="env",
                    input_data={"service_account_file_present": True},
                ) as span:
                    self.credentials = service_account.Credentials.from_service_account_file(
                        self.service_account_path, scopes=SCOPES
                    )
                    span.decision = {"selected_auth_method": "service_account"}
            except Exception as exc:
                raise GoogleDriveUploadError(f"Failed to load Service Account JSON: {exc}") from exc
        elif self.credentials is not None:
            emit_skipped(
                "env", "gdrive.auth.service_account",
                "a higher-priority OAuth method succeeded",
                component="youtube_clipper.gdrive",
                next_action="gdrive.build_client", next_stage="env",
            )
        else:
            emit_skipped(
                "env", "gdrive.auth.service_account",
                "service-account credential file is absent",
                component="youtube_clipper.gdrive",
            )

        # No valid credentials loaded across all 3 tiers
        if self.credentials is None:
            raise FileNotFoundError(
                f"Service Account JSON file not found at: {self.service_account_path}"
            )

        try:
            with action_span(
                "env", "gdrive.build_client",
                component="youtube_clipper.gdrive",
                next_action="gdrive.resolve_folder", next_stage="env",
            ):
                self.service = build("drive", "v3", credentials=self.credentials)
        except Exception as exc:
            raise GoogleDriveUploadError(f"Failed to authenticate Google Drive client: {exc}") from exc

    def upload_clip(
        self,
        file_path: str,
        folder_id: Optional[str] = None,
        folder_name: Optional[str] = "YouTube_Clips",
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
                with action_span(
                    "env", "gdrive.resolve_folder",
                    component="youtube_clipper.gdrive",
                    next_action="gdrive.upload", next_stage="report",
                ) as span:
                    fname = folder_name or "YouTube_Clips"
                    query = f"name = '{fname}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
                    results = self.service.files().list(
                        q=query, fields="files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True
                    ).execute()
                    folders = results.get("files", [])

                    if folders:
                        target_folder_id = folders[0]["id"]
                        span.decision = {"folder": "existing"}
                    else:
                        folder_metadata = {
                            "name": fname,
                            "mimeType": "application/vnd.google-apps.folder"
                        }
                        folder = self.service.files().create(
                            body=folder_metadata, fields="id", supportsAllDrives=True
                        ).execute()
                        target_folder_id = folder.get("id")
                        span.decision = {"folder": "created"}
            else:
                emit_skipped(
                    "env", "gdrive.resolve_folder",
                    "a target folder id was supplied or configured",
                    component="youtube_clipper.gdrive",
                    next_action="gdrive.upload", next_stage="report",
                )

            # Upload file to target folder
            file_metadata = {
                "name": file_name,
                "parents": [target_folder_id]
            }
            total_file_size = os.path.getsize(file_path)
            media = MediaFileUpload(
                file_path,
                mimetype="video/mp4",
                resumable=True,
                chunksize=DRIVE_UPLOAD_CHUNK_SIZE,
            )

            with action_span(
                "report", "gdrive.upload",
                component="youtube_clipper.gdrive",
                next_action="gdrive.set_permission", next_stage="report",
                input_data={"file_name": file_name, "size_bytes": os.path.getsize(file_path)},
            ):
                upload_request = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields="id, name, webViewLink, webContentLink, size",
                    supportsAllDrives=True
                )
                last_uploaded_bytes = 0
                last_progress_percent = 0.0
                last_chunk_number = 0

                def publish_progress(
                    suffix: str,
                    *,
                    percent: Optional[float],
                    uploaded_bytes: Optional[int],
                    total_bytes: int,
                    chunk_number: int,
                    indeterminate: bool,
                ) -> None:
                    decision = {
                        "progress_percent": (
                            None if percent is None else round(max(0.0, min(100.0, float(percent))), 2)
                        ),
                        "uploaded_bytes": (
                            None if uploaded_bytes is None else max(0, min(int(uploaded_bytes), int(total_bytes)))
                        ),
                        "total_bytes": int(total_bytes),
                        "chunk_number": max(0, int(chunk_number)),
                        "indeterminate": bool(indeterminate),
                    }
                    emit_event(
                        stage="report",
                        component="youtube_clipper.gdrive",
                        action=f"gdrive.upload.progress.{suffix}",
                        status="succeeded",
                        decision=decision,
                        next_action="gdrive.upload",
                        next_stage="report",
                        transition_reason="Google Drive upload progress updated",
                    )

                resumable_transport = (
                    isinstance(upload_request, HttpRequest)
                    and callable(upload_request.next_chunk)
                )
                if resumable_transport:
                    uploaded_file = None
                    retry_attempt = 0
                    publish_progress(
                        "0",
                        percent=0.0,
                        uploaded_bytes=0,
                        total_bytes=total_file_size,
                        chunk_number=0,
                        indeterminate=False,
                    )
                    while uploaded_file is None:
                        try:
                            progress, uploaded_file = upload_request.next_chunk()
                            retry_attempt = 0
                            if progress is not None:
                                last_chunk_number += 1
                                progress_total = int(
                                    (
                                        progress.total_size
                                        if hasattr(progress, "total_size")
                                        else None
                                    )
                                    or total_file_size
                                )
                                raw_uploaded = (
                                    progress.resumable_progress
                                    if hasattr(progress, "resumable_progress")
                                    else None
                                )
                                try:
                                    fraction = float(progress.progress())
                                except (AttributeError, TypeError, ValueError):
                                    fraction = (
                                        float(raw_uploaded) / float(progress_total)
                                        if raw_uploaded is not None and progress_total > 0
                                        else 0.0
                                    )
                                computed_uploaded = (
                                    int(raw_uploaded)
                                    if raw_uploaded is not None
                                    else int(round(progress_total * fraction))
                                )
                                last_uploaded_bytes = max(
                                    last_uploaded_bytes,
                                    min(computed_uploaded, total_file_size),
                                )
                                last_progress_percent = max(
                                    last_progress_percent,
                                    min(99.99, fraction * 100.0),
                                )
                                publish_progress(
                                    str(last_chunk_number),
                                    percent=last_progress_percent,
                                    uploaded_bytes=last_uploaded_bytes,
                                    total_bytes=total_file_size,
                                    chunk_number=last_chunk_number,
                                    indeterminate=False,
                                )
                            if uploaded_file is not None:
                                last_uploaded_bytes = total_file_size
                                last_progress_percent = 100.0
                                publish_progress(
                                    "complete",
                                    percent=100.0,
                                    uploaded_bytes=total_file_size,
                                    total_bytes=total_file_size,
                                    chunk_number=last_chunk_number,
                                    indeterminate=False,
                                )
                        except HttpError as chunk_error:
                            try:
                                http_status = int(chunk_error.resp.status)
                            except (AttributeError, TypeError, ValueError):
                                http_status = 0
                            retryable = http_status == 429 or 500 <= http_status < 600
                            if not retryable or retry_attempt >= 3:
                                raise
                            retry_attempt += 1
                            delay = 2 ** (retry_attempt - 1)
                            emit_event(
                                stage="report",
                                component="youtube_clipper.gdrive",
                                action="gdrive.upload",
                                status="retrying",
                                attempt=retry_attempt + 1,
                                severity="warn",
                                decision={
                                    "http_status": http_status,
                                    "backoff_seconds": delay,
                                    "progress_percent": last_progress_percent,
                                    "uploaded_bytes": last_uploaded_bytes,
                                    "total_bytes": total_file_size,
                                },
                                next_action="gdrive.upload",
                                next_stage="report",
                                transition_reason="transient Drive response; retrying resumable upload",
                            )
                            time.sleep(delay)
                else:
                    # Compatibility transports do not expose acknowledged bytes.
                    # Keep the bar indeterminate until execute() returns.
                    publish_progress(
                        "indeterminate",
                        percent=None,
                        uploaded_bytes=None,
                        total_bytes=total_file_size,
                        chunk_number=0,
                        indeterminate=True,
                    )
                    uploaded_file = upload_request.execute()
                    last_uploaded_bytes = total_file_size
                    last_progress_percent = 100.0
                    publish_progress(
                        "complete",
                        percent=100.0,
                        uploaded_bytes=total_file_size,
                        total_bytes=total_file_size,
                        chunk_number=0,
                        indeterminate=False,
                    )

            # Create reader permission (public link view)
            permission_configured = False
            try:
                with action_span(
                    "report", "gdrive.set_permission",
                    component="youtube_clipper.gdrive",
                ):
                    permission = {"type": "anyone", "role": "reader"}
                    self.service.permissions().create(
                        fileId=uploaded_file["id"], body=permission, supportsAllDrives=True
                    ).execute()
                    permission_configured = True
            except Exception as perm_err:
                logger.warning(f"Failed to set public permission on file {uploaded_file.get('id')}: {perm_err}")

            return {
                "status": "success",
                "success": True,
                "file_id": uploaded_file.get("id"),
                "file_name": uploaded_file.get("name"),
                "web_view_link": uploaded_file.get("webViewLink"),
                "web_content_link": uploaded_file.get("webContentLink"),
                "size_bytes": uploaded_file.get("size"),
                "permission_configured": permission_configured,
                "upload_progress": {
                    "determinate": True,
                    "progress_percent": last_progress_percent,
                    "uploaded_bytes": last_uploaded_bytes,
                    "total_bytes": total_file_size,
                    "chunk_number": last_chunk_number,
                },
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
    **kwargs: Any,
) -> Dict[str, Any]:
    """Helper function to upload clip to Google Drive."""
    try:
        plan = [
            {"action": "gdrive.auth.oauth_env", "stage": "env"},
            {"action": "gdrive.auth.token_file", "stage": "env"},
            {"action": "gdrive.auth.service_account", "stage": "env"},
            {"action": "gdrive.build_client", "stage": "env"},
            {"action": "gdrive.resolve_folder", "stage": "env"},
            {"action": "gdrive.upload", "stage": "report"},
            {"action": "gdrive.set_permission", "stage": "report"},
        ]
        requested_run_id = kwargs.pop("run_id", None)
        requested_request_id = kwargs.pop("request_id", None)
        with run_context(
            run_id=requested_run_id,
            request_id=requested_request_id,
            actions=plan,
            component="youtube_clipper.gdrive",
        ):
            uploader = GoogleDriveUploader()
            return uploader.upload_clip(
                file_path, folder_id=folder_id, folder_name=folder_name, **kwargs
            )
    except Exception as e:
        return {
            "status": "error",
            "success": False,
            "error": str(e)
        }
