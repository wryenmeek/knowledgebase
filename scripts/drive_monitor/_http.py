"""Shared Drive API helpers for the drive_monitor script family.

All scripts (``check_drift``, ``fetch_content``, ``synthesize_diff``) need
authenticated Drive API v3 access.  Centralising these helpers eliminates
duplication and ensures consistent retry / auth handling.

Authentication:
    Set ``GDRIVE_SA_KEY`` (service account JSON key file content, as a
    JSON string) in the environment.  The key is never accepted as a CLI
    argument because that would expose it in ``ps aux`` and CI logs.

    For per-registry credential overrides, the registry may specify a
    ``credential_secret_name`` field (defaults to ``GDRIVE_SA_KEY``).

    Requires ``google-api-python-client>=2.100`` and ``google-auth>=2.23``
    (installed via ``pip install -e ".[drive-monitor]"``).
"""

from __future__ import annotations

import io
import json
import os
import time
from typing import Any

from scripts.drive_monitor._types import DriveAPIRequestError, DriveAPIResponseError

_MAX_RETRIES = 3
_RETRY_DELAYS = (1.0, 2.0, 4.0)
_MAX_RETRY_DELAY = 60.0

# Fields requested for file metadata in changes.list and files.get.
_FILE_FIELDS = (
    "id,name,mimeType,version,md5Checksum,parents,trashed,explicitlyTrashed,"
    "size,modifiedTime"
)

_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def _load_credentials(credential_secret_name: str = "GDRIVE_SA_KEY") -> Any:
    """Load Google service account credentials from the environment.

    Reads the secret named ``credential_secret_name`` from the environment,
    parses it as a JSON service account key, and returns a
    ``google.oauth2.service_account.Credentials`` object scoped for
    Drive read-only access.

    Raises ``DriveAPIRequestError`` if the env var is absent or the JSON is
    malformed.  Never accepts credentials as CLI arguments.
    """
    try:
        from google.oauth2 import service_account  # type: ignore[import]
    except ImportError as exc:
        raise DriveAPIRequestError(
            detail=(
                "google-auth is not installed. "
                "Run: pip install -e \".[drive-monitor]\""
            )
        ) from exc

    raw = os.environ.get(credential_secret_name)
    if not raw:
        raise DriveAPIRequestError(
            detail=(
                f"Environment variable {credential_secret_name!r} is not set. "
                "Set it to the service account JSON key content."
            )
        )
    try:
        key_data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DriveAPIRequestError(
            detail=f"Failed to parse service account JSON from {credential_secret_name!r}: {exc}"
        ) from exc

    try:
        creds = service_account.Credentials.from_service_account_info(
            key_data, scopes=_DRIVE_SCOPES
        )
    except (ValueError, KeyError):
        raise DriveAPIRequestError(
            detail=(
                "Failed to load service account credentials — "
                "check GOOGLE_DRIVE_SA_KEY format"
            )
        ) from None
    return creds


def build_drive_client(credential_secret_name: str = "GDRIVE_SA_KEY") -> Any:
    """Build and return a Drive API v3 client.

    Parameters
    ----------
    credential_secret_name:
        Name of the environment variable holding the service account JSON key.

    Returns
    -------
    googleapiclient.discovery.Resource
        Authenticated Drive API v3 resource object.
    """
    try:
        from googleapiclient.discovery import build  # type: ignore[import]
    except ImportError as exc:
        raise DriveAPIRequestError(
            detail=(
                "google-api-python-client is not installed. "
                "Run: pip install -e \".[drive-monitor]\""
            )
        ) from exc

    try:
        import httplib2  # type: ignore[import]
        import google_auth_httplib2  # type: ignore[import]
    except ImportError as exc:
        raise DriveAPIRequestError(
            detail=(
                "httplib2 / google-auth-httplib2 is not installed. "
                "Run: pip install -e \".[drive-monitor]\""
            )
        ) from exc

    creds = _load_credentials(credential_secret_name)
    http = google_auth_httplib2.AuthorizedHttp(
        creds, http=httplib2.Http(timeout=30)
    )
    return build("drive", "v3", http=http, cache_discovery=False)


def _with_retry(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Call *fn* with retry on transient API errors.

    Retries on HTTP 429 and 5xx status codes.  Raises ``DriveAPIRequestError``
    after all retries are exhausted or on permanent errors.
    """
    try:
        from googleapiclient.errors import HttpError  # type: ignore[import]
    except ImportError:
        # If the library is not installed, let the underlying call fail.
        return fn(*args, **kwargs)

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except HttpError as exc:
            status = exc.resp.status if exc.resp else 0
            if (status >= 500 or status == 429) and attempt < _MAX_RETRIES - 1:
                last_exc = exc
                delay = _RETRY_DELAYS[attempt]
                retry_after = exc.resp.get("retry-after") if exc.resp else None
                if retry_after:
                    try:
                        delay = min(float(retry_after), _MAX_RETRY_DELAY)
                    except (ValueError, TypeError):
                        pass
                time.sleep(delay)
                continue
            raise DriveAPIRequestError(
                detail=f"Drive API error: {exc.reason}",
                status_code=status,
            ) from exc
    raise DriveAPIRequestError(
        detail=f"Drive API request failed after {_MAX_RETRIES} retries; "
               f"last error: {last_exc}",
    )


def get_changes_start_page_token(drive: Any) -> str:
    """Retrieve the current start page token for changes.list.

    Call this on first initialization when ``changes_page_token`` is ``None``.
    Returns the token as a string.  Raises ``DriveAPIRequestError`` on failure.
    """
    result = _with_retry(
        lambda: drive.changes()
        .getStartPageToken(supportsAllDrives=True)
        .execute()
    )
    token = result.get("startPageToken")
    if not token:
        raise DriveAPIResponseError(
            f"getStartPageToken returned unexpected response: {result!r}"
        )
    return token


def list_changes(
    drive: Any,
    page_token: str,
    *,
    page_size: int = 100,
) -> tuple[list[dict[str, Any]], str]:
    """Page through Drive changes starting from *page_token*.

    Returns ``(changes, new_page_token)`` where ``changes`` is the aggregated
    list of all change objects across all pages, and ``new_page_token`` is the
    ``newStartPageToken`` to save for the next run.

    Raises ``DriveAPIRequestError`` on network/API failure.
    Raises ``DriveAPIResponseError`` on unexpected response shape.
    """
    all_changes: list[dict[str, Any]] = []
    current_token = page_token

    while True:
        response = _with_retry(
            lambda t=current_token: drive.changes()
            .list(
                pageToken=t,
                pageSize=page_size,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                fields=(
                    "nextPageToken,newStartPageToken,"
                    f"changes(fileId,file({_FILE_FIELDS}),removed)"
                ),
            )
            .execute()
        )

        changes = response.get("changes", [])
        all_changes.extend(changes)

        next_token = response.get("nextPageToken")
        if next_token:
            current_token = next_token
        else:
            new_start_token = response.get("newStartPageToken")
            if not new_start_token:
                raise DriveAPIResponseError(
                    f"changes.list response missing both nextPageToken and "
                    f"newStartPageToken: {response!r}"
                )
            return all_changes, new_start_token


def get_file_metadata(
    drive: Any,
    file_id: str,
) -> dict[str, Any]:
    """Fetch metadata for a single Drive file.

    Returns the file resource dict.  Raises ``DriveAPIRequestError`` on
    network failure or ``DriveAPIResponseError`` on unexpected shape.
    """
    result = _with_retry(
        lambda: drive.files()
        .get(fileId=file_id, fields=_FILE_FIELDS, supportsAllDrives=True)
        .execute()
    )
    if not isinstance(result, dict) or "id" not in result:
        raise DriveAPIResponseError(
            f"files.get returned unexpected response for {file_id!r}: {result!r}"
        )
    return result


def get_file_parents(drive: Any, file_id: str) -> list[str]:
    """Fetch the parent IDs for a single Drive file.

    Used for parent-chain resolution when discovering new files.
    Returns a list of parent folder IDs (usually one element).
    Raises ``DriveAPIRequestError`` on failure.
    """
    result = _with_retry(
        lambda: drive.files()
        .get(fileId=file_id, fields="id,parents", supportsAllDrives=True)
        .execute()
    )
    if not isinstance(result, dict):
        raise DriveAPIResponseError(
            f"files.get(parents) returned unexpected type for {file_id!r}"
        )
    return result.get("parents") or []


def export_file_as_markdown(drive: Any, file_id: str) -> bytes:
    """Export a native Google Doc to Markdown bytes.

    Uses ``files.export`` with ``mimeType=text/markdown``.
    Raises ``DriveAPIRequestError`` on failure.
    """
    try:
        from googleapiclient.http import MediaIoBaseDownload  # type: ignore[import]
    except ImportError as exc:
        raise DriveAPIRequestError(
            detail="google-api-python-client is not installed."
        ) from exc

    request = drive.files().export_media(fileId=file_id, mimeType="text/markdown")
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = _with_retry(lambda: downloader.next_chunk())
    return buf.getvalue()


def export_file_as_pdf(drive: Any, file_id: str) -> bytes:
    """Export a native Google Slides presentation to PDF bytes."""
    try:
        from googleapiclient.http import MediaIoBaseDownload  # type: ignore[import]
    except ImportError as exc:
        raise DriveAPIRequestError(
            detail="google-api-python-client is not installed."
        ) from exc

    request = drive.files().export_media(
        fileId=file_id, mimeType="application/pdf"
    )
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = _with_retry(lambda: downloader.next_chunk())
    return buf.getvalue()


def download_file(drive: Any, file_id: str) -> bytes:
    """Download a non-native Drive file's raw bytes.

    Used for PDF, DOCX, text/plain, text/markdown files.
    Raises ``DriveAPIRequestError`` on failure.
    """
    try:
        from googleapiclient.http import MediaIoBaseDownload  # type: ignore[import]
    except ImportError as exc:
        raise DriveAPIRequestError(
            detail="google-api-python-client is not installed."
        ) from exc

    request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = _with_retry(lambda: downloader.next_chunk())
    return buf.getvalue()
