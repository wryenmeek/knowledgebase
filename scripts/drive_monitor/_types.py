"""Typed definitions and runtime validation for Drive API responses, the
drive source registry schema, and the drive drift report schema.

All Drive API responses are treated as third-party untrusted data. Every
response must pass validation before any field is used in logic.

Hard failures (invalid shape) raise ``DriveAPIResponseError`` which callers
must map to ``DriveMonitorReasonCode.FETCH_FAILED``.
"""

from __future__ import annotations

import re
from typing import Any, TypedDict


_SHA256_RE: re.Pattern[str] = re.compile(r"^[0-9a-f]{64}$")
# Drive file_id: alphanumeric plus underscore and hyphen; typically ~33 chars.
_DRIVE_FILE_ID_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_\-]+$")
# Drive version: positive integer string.
_DRIVE_VERSION_RE: re.Pattern[str] = re.compile(r"^[0-9]+$")
# MD5 checksum: 32-char lowercase hex.
_MD5_RE: re.Pattern[str] = re.compile(r"^[0-9a-f]{32}$")
# Alias slug: lowercase, alphanumeric, hyphens only.
_ALIAS_RE: re.Pattern[str] = re.compile(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$|^[a-z0-9]$")

_VALID_FOLDER_TRACKING_STATUSES: frozenset[str] = frozenset(
    {"active", "paused", "archived"}
)
_VALID_FILE_TRACKING_STATUSES: frozenset[str] = frozenset(
    {"active", "paused", "archived", "pending_review", "uninitialized"}
)

REGISTRY_VERSION = "1"
DRIFT_REPORT_VERSION = "1"

# ---------------------------------------------------------------------------
# MIME type constants
# ---------------------------------------------------------------------------

DRIVE_MIME_ALLOWLIST: frozenset[str] = frozenset({
    "application/vnd.google-apps.document",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "application/vnd.google-apps.presentation",
})

# For native formats: maps Drive MIME type → export MIME type.
# Non-native formats are downloaded directly (no export needed).
MIME_EXPORT_MAP: dict[str, str] = {
    "application/vnd.google-apps.document": "text/markdown",
    "application/vnd.google-apps.presentation": "application/pdf",
}

# Extension to use when writing vendored assets for each MIME type.
MIME_EXTENSION_MAP: dict[str, str] = {
    "application/vnd.google-apps.document": ".md",
    "application/vnd.google-apps.presentation": ".pdf",
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
    "text/markdown": ".md",
}

# Files above this byte limit get a truncated diff notice.
OVERSIZE_LIMIT_BYTES = 5_000_000


# ---------------------------------------------------------------------------
# Exception types
# ---------------------------------------------------------------------------


class DriveAPIResponseError(ValueError):
    """Raised when a Drive API response does not match the expected shape."""


class DriveAPIRequestError(OSError):
    """Raised when an HTTP/gRPC request to the Drive API fails.

    Attributes
    ----------
    detail:
        Human-readable reason string.
    status_code:
        HTTP status code, or ``None`` for network-level failures.
    """

    def __init__(self, *, detail: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Drive API request failed: {status_code} {detail}")


# ---------------------------------------------------------------------------
# Source registry TypedDicts
# ---------------------------------------------------------------------------


class FolderEntry(TypedDict, total=False):
    """One registered Google Drive root folder.

    Required fields: ``folder_id``, ``folder_name``, ``wiki_namespace``,
    ``tracking_status``.
    """

    folder_id: str
    folder_name: str          # display only; may be stale after Drive rename
    wiki_namespace: str       # relative namespace, e.g. "cms/" → wiki/cms/{slug}.md
    tracking_status: str      # "active" | "paused" | "archived"


class DriveFileEntry(TypedDict, total=False):
    """One monitored Drive file.

    Required fields: ``file_id``, ``tracking_status``.
    All version / hash / timestamp fields are optional (nullable) to support
    the ``uninitialized`` state where no prior ingest has occurred.
    """

    file_id: str
    display_name: str         # filename at last fetch (informational)
    display_path: str         # folder-relative path (informational, may be stale)
    mime_type: str            # MIME type at last fetch
    tracking_status: str
    wiki_page: str | None     # repo-relative wiki page path

    # Three-stage state machine — native formats (google-apps.document / presentation)
    drive_version: int | None               # Drive version integer at last applied
    last_applied_drive_version: int | None
    last_applied_at: str | None             # ISO 8601
    sha256_at_last_applied: str | None      # SHA-256 of normalized export bytes
    last_fetched_drive_version: int | None
    last_fetched_at: str | None
    sha256_at_last_fetched: str | None

    # Three-stage state machine — non-native formats (PDF, DOCX, text/plain, text/markdown)
    md5_checksum_at_last_applied: str | None
    md5_checksum_at_last_fetched: str | None

    notes: str


class DriveRegistryFile(TypedDict):
    """Top-level shape of a ``{alias}.source-registry.json`` file."""

    version: str
    alias: str
    credential_secret_name: str       # default "GDRIVE_SA_KEY"
    changes_page_token: str | None    # Drive Changes API cursor
    last_full_scan_at: str | None     # ISO 8601; periodic safety-net timestamp
    folder_entries: list[FolderEntry]
    file_entries: list[DriveFileEntry]


# ---------------------------------------------------------------------------
# Drift report TypedDicts
# ---------------------------------------------------------------------------


class DriveDriftedEntry(TypedDict, total=False):
    """An entry with a detected content change or lifecycle event.

    Required fields: ``alias``, ``file_id``, ``display_name``, ``mime_type``,
    ``event_type``, ``tracking_status``.
    """

    alias: str
    file_id: str
    display_name: str
    display_path: str
    mime_type: str
    event_type: str   # "content_changed" | "new_file" | "trashed" | "deleted" | "out_of_scope"
    tracking_status: str
    wiki_page: str | None

    # Populated for native formats on content_changed / new_file
    current_drive_version: int | None
    last_applied_drive_version: int | None
    sha256_at_last_applied: str | None

    # Populated for non-native formats on content_changed / new_file
    current_md5_checksum: str | None
    md5_checksum_at_last_applied: str | None

    # Optional diff metrics (populated when old asset is available)
    lines_added: int | None
    lines_removed: int | None
    is_binary: bool | None
    file_size_bytes: int | None

    # Parent folder context (populated during parent-chain resolution for new files)
    parent_folder_id: str | None


class DriveUpToDateEntry(TypedDict):
    """An entry whose current version/checksum matches the last-applied value."""

    alias: str
    file_id: str
    display_name: str


class DriveUninitializedEntry(TypedDict):
    """An entry with ``tracking_status == "uninitialized"``."""

    alias: str
    file_id: str
    display_name: str
    tracking_status: str


class DriveErrorEntry(TypedDict):
    """An entry that could not be checked due to an API or validation error."""

    alias: str
    file_id: str
    reason_code: str
    message: str


class DriveDriftReport(TypedDict):
    """Top-level drift report produced by ``check_drift.py``."""

    version: str
    generated_at: str
    registry: str           # path to the registry file that produced this report
    has_drift: bool
    drifted: list[DriveDriftedEntry]
    up_to_date: list[DriveUpToDateEntry]
    uninitialized: list[DriveUninitializedEntry]
    errors: list[DriveErrorEntry]


# ---------------------------------------------------------------------------
# Registry validation
# ---------------------------------------------------------------------------


def validate_drive_registry_file(data: Any) -> DriveRegistryFile:
    """Validate the parsed JSON of a Drive ``*.source-registry.json`` file.

    Raises ``ValueError`` on any schema violation.  Callers should map this
    exception to an appropriate reason code and fail closed.
    """
    if not isinstance(data, dict):
        raise ValueError(
            f"Drive registry must be a JSON object, got {type(data).__name__!r}"
        )

    for key in ("version", "alias", "folder_entries", "file_entries"):
        if key not in data:
            raise ValueError(f"Drive registry missing required field {key!r}")

    if data["version"] != REGISTRY_VERSION:
        raise ValueError(
            f"Drive registry version must be {REGISTRY_VERSION!r}, "
            f"got {data['version']!r}"
        )

    if not isinstance(data["alias"], str) or not _ALIAS_RE.match(data["alias"]):
        raise ValueError(
            f"Drive registry 'alias' must be a lowercase alphanumeric-hyphen slug, "
            f"got {data['alias']!r}"
        )

    if not isinstance(data["folder_entries"], list):
        raise ValueError(
            f"Drive registry 'folder_entries' must be a list, "
            f"got {type(data['folder_entries']).__name__!r}"
        )

    if not isinstance(data["file_entries"], list):
        raise ValueError(
            f"Drive registry 'file_entries' must be a list, "
            f"got {type(data['file_entries']).__name__!r}"
        )

    for idx, entry in enumerate(data["folder_entries"]):
        _validate_folder_entry(entry, idx)

    for idx, entry in enumerate(data["file_entries"]):
        _validate_file_entry(entry, idx)

    return data  # type: ignore[return-value]


def _validate_folder_entry(entry: Any, idx: int) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"folder_entries[{idx}] must be an object")

    for key in ("folder_id", "folder_name", "wiki_namespace", "tracking_status"):
        if key not in entry:
            raise ValueError(f"folder_entries[{idx}] missing required field {key!r}")
        if not isinstance(entry[key], str) or not entry[key]:
            raise ValueError(
                f"folder_entries[{idx}] field {key!r} must be a non-empty string"
            )

    if entry["tracking_status"] not in _VALID_FOLDER_TRACKING_STATUSES:
        raise ValueError(
            f"folder_entries[{idx}] has unrecognised tracking_status "
            f"{entry['tracking_status']!r}; valid values: "
            f"{sorted(_VALID_FOLDER_TRACKING_STATUSES)}"
        )

    if not _DRIVE_FILE_ID_RE.match(entry["folder_id"]):
        raise ValueError(
            f"folder_entries[{idx}] 'folder_id' contains unsafe characters: "
            f"{entry['folder_id']!r}"
        )


def _validate_file_entry(entry: Any, idx: int) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"file_entries[{idx}] must be an object")

    for key in ("file_id", "tracking_status"):
        if key not in entry:
            raise ValueError(f"file_entries[{idx}] missing required field {key!r}")
        if not isinstance(entry[key], str) or not entry[key]:
            raise ValueError(
                f"file_entries[{idx}] field {key!r} must be a non-empty string"
            )

    if not _DRIVE_FILE_ID_RE.match(entry["file_id"]):
        raise ValueError(
            f"file_entries[{idx}] 'file_id' contains unsafe characters: "
            f"{entry['file_id']!r}"
        )

    if entry["tracking_status"] not in _VALID_FILE_TRACKING_STATUSES:
        raise ValueError(
            f"file_entries[{idx}] has unrecognised tracking_status "
            f"{entry['tracking_status']!r}; valid values: "
            f"{sorted(_VALID_FILE_TRACKING_STATUSES)}"
        )

    for sha256_key in ("sha256_at_last_applied", "sha256_at_last_fetched"):
        v = entry.get(sha256_key)
        if v is not None and not _SHA256_RE.match(v):
            raise ValueError(
                f"file_entries[{idx}] field {sha256_key!r} must be a 64-char "
                f"lowercase hex string or null, got {v!r}"
            )

    for md5_key in ("md5_checksum_at_last_applied", "md5_checksum_at_last_fetched"):
        v = entry.get(md5_key)
        if v is not None and not _MD5_RE.match(v):
            raise ValueError(
                f"file_entries[{idx}] field {md5_key!r} must be a 32-char "
                f"lowercase hex string or null, got {v!r}"
            )

    drive_version = entry.get("drive_version")
    if drive_version is not None and not isinstance(drive_version, int):
        raise ValueError(
            f"file_entries[{idx}] 'drive_version' must be an integer or null, "
            f"got {drive_version!r}"
        )


# ---------------------------------------------------------------------------
# Drift report validation
# ---------------------------------------------------------------------------


def validate_drive_drift_report(data: Any) -> DriveDriftReport:
    """Validate a parsed drive drift report JSON object.

    Raises ``ValueError`` on any schema violation.  Used by downstream
    scripts that consume the drift report produced by ``check_drift.py``.
    """
    if not isinstance(data, dict):
        raise ValueError(
            f"Drive drift report must be a JSON object, "
            f"got {type(data).__name__!r}"
        )

    for key in ("version", "generated_at", "registry", "has_drift",
                "drifted", "up_to_date", "uninitialized", "errors"):
        if key not in data:
            raise ValueError(f"Drive drift report missing required field {key!r}")

    if data["version"] != DRIFT_REPORT_VERSION:
        raise ValueError(
            f"Drive drift report version must be {DRIFT_REPORT_VERSION!r}, "
            f"got {data['version']!r}"
        )

    for list_key in ("drifted", "up_to_date", "uninitialized", "errors"):
        if not isinstance(data[list_key], list):
            raise ValueError(
                f"Drive drift report {list_key!r} must be a list, "
                f"got {type(data[list_key]).__name__!r}"
            )

    if not isinstance(data["has_drift"], bool):
        raise ValueError(
            f"Drive drift report 'has_drift' must be a bool, "
            f"got {type(data['has_drift']).__name__!r}"
        )

    for i, entry in enumerate(data["drifted"]):
        _validate_drifted_entry(entry, i)

    return data  # type: ignore[return-value]


_VALID_EVENT_TYPES: frozenset[str] = frozenset(
    {"content_changed", "new_file", "trashed", "deleted", "out_of_scope"}
)


def _validate_drifted_entry(entry: Any, idx: int) -> None:
    """Validate one entry from the ``drifted`` list of a drive drift report."""
    if not isinstance(entry, dict):
        raise ValueError(f"drifted[{idx}] must be a JSON object")

    for key in ("alias", "file_id", "display_name", "mime_type", "event_type"):
        if key not in entry:
            raise ValueError(f"drifted[{idx}] missing required field {key!r}")
        if not isinstance(entry[key], str) or not entry[key]:
            raise ValueError(
                f"drifted[{idx}] field {key!r} must be a non-empty string"
            )

    if entry["event_type"] not in _VALID_EVENT_TYPES:
        raise ValueError(
            f"drifted[{idx}] 'event_type' must be one of {sorted(_VALID_EVENT_TYPES)}, "
            f"got {entry['event_type']!r}"
        )

    if not _DRIVE_FILE_ID_RE.match(entry["file_id"]):
        raise ValueError(
            f"drifted[{idx}]['file_id'] contains unsafe characters: "
            f"{entry['file_id']!r}"
        )

    sha256 = entry.get("sha256_at_last_applied")
    if sha256 is not None and not _SHA256_RE.match(sha256):
        raise ValueError(
            f"drifted[{idx}]['sha256_at_last_applied'] must be a 64-char "
            f"lowercase hex string or null"
        )
