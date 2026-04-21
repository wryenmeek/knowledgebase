"""Typed definitions and runtime validation for GitHub API responses, the
source registry schema, and the drift report schema.

All GitHub API responses are treated as third-party untrusted data. Every
response must pass validation before any field is used in logic.

Hard failures (invalid shape) raise ``GitHubAPIResponseError`` which callers
must map to ``GitHubMonitorReasonCode.FETCH_FAILED``.
"""

from __future__ import annotations

import re
from typing import Any, TypedDict


_COMMIT_SHA_RE: re.Pattern[str] = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE: re.Pattern[str] = re.compile(r"^[0-9a-f]{64}$")
# Same pattern as _validators._SAFE_SEGMENT_RE — keep in sync with scripts/github_monitor/_validators.py._SAFE_SEGMENT_RE
_SAFE_SEGMENT_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9._\-]+$")

_VALID_TRACKING_STATUSES: frozenset[str] = frozenset(
    {"active", "paused", "archived", "unreachable", "uninitialized"}
)

REGISTRY_VERSION = "1"
DRIFT_REPORT_VERSION = "1"


# ---------------------------------------------------------------------------
# Exception types
# ---------------------------------------------------------------------------


class GitHubAPIResponseError(ValueError):
    """Raised when a GitHub API response does not match the expected shape."""


class GitHubAPIRequestError(OSError):
    """Raised when an HTTP request to the GitHub API fails.

    Attributes
    ----------
    url:
        The requested URL.
    status_code:
        HTTP status code, or ``None`` for network-level failures.
    detail:
        Human-readable reason string from the HTTP response or network layer.
    """

    def __init__(self, *, url: str, status_code: int | None, detail: str) -> None:
        self.url = url
        self.status_code = status_code
        self.detail = detail
        super().__init__(
            f"GitHub API request failed: {status_code} {detail} — {url}"
        )


# ---------------------------------------------------------------------------
# Source registry TypedDicts
# ---------------------------------------------------------------------------


class RegistryEntry(TypedDict, total=False):
    """One entry in a source registry file.

    Required keys: ``path``, ``tracking_status``.
    All SHA / timestamp fields are optional (null-able) to support the
    ``uninitialized`` state where no prior ingest has occurred.
    """

    path: str
    tracking_status: str
    last_applied_commit_sha: str | None
    last_applied_blob_sha: str | None
    last_applied_at: str | None
    last_fetched_commit_sha: str | None
    last_fetched_blob_sha: str | None
    sha256_at_last_applied: str | None
    wiki_page: str | None
    notes: str


class RegistryFile(TypedDict):
    """Top-level shape of a ``*.source-registry.json`` file."""

    version: str
    owner: str
    repo: str
    github_app_installation_id: int | None
    entries: list[RegistryEntry]


# ---------------------------------------------------------------------------
# Drift report TypedDicts
# ---------------------------------------------------------------------------


class DriftedEntry(TypedDict):
    """An entry where the current blob SHA differs from ``last_applied_blob_sha``."""

    owner: str
    repo: str
    path: str
    current_commit_sha: str
    current_blob_sha: str
    last_applied_commit_sha: str | None
    last_applied_blob_sha: str | None
    compare_url: str | None


class UpToDateEntry(TypedDict):
    """An entry where the current blob SHA matches ``last_applied_blob_sha``."""

    owner: str
    repo: str
    path: str
    blob_sha: str


class UninitializedEntry(TypedDict):
    """An entry with ``tracking_status == "uninitialized"`` (no prior ingest)."""

    owner: str
    repo: str
    path: str
    tracking_status: str


class ErrorEntry(TypedDict):
    """An entry that could not be checked due to an API or validation error."""

    path: str
    reason_code: str
    message: str


class DriftReport(TypedDict):
    """Top-level drift report produced by ``check_drift.py``."""

    version: str
    generated_at: str
    registry: str
    has_drift: bool
    drifted: list[DriftedEntry]
    up_to_date: list[UpToDateEntry]
    uninitialized: list[UninitializedEntry]
    errors: list[ErrorEntry]


def validate_contents_response(data: Any) -> dict[str, Any]:
    """Validate a response from ``GET /repos/{owner}/{repo}/contents/{path}``.

    Returns the validated response dict.  Raises ``GitHubAPIResponseError`` on
    any shape violation:

    - Not a dict (could be a list when path points to a directory).
    - Missing required fields: ``sha``, ``content``, ``encoding``, ``size``.
    - ``encoding`` is not ``"base64"``.
    - ``sha`` is not a non-empty string.
    - ``size`` is not an integer.

    The caller is responsible for mapping this exception to
    ``GitHubMonitorReasonCode.FETCH_FAILED``.
    """
    if not isinstance(data, dict):
        raise GitHubAPIResponseError(
            f"Expected dict from contents API, got {type(data).__name__!r}"
        )

    for field in ("sha", "content", "encoding", "size"):
        if field not in data:
            raise GitHubAPIResponseError(
                f"Contents API response missing required field {field!r}"
            )

    if not isinstance(data["sha"], str) or not data["sha"]:
        raise GitHubAPIResponseError(
            f"Contents API 'sha' must be a non-empty string, got {data['sha']!r}"
        )

    if not _COMMIT_SHA_RE.match(data["sha"]):
        raise GitHubAPIResponseError(
            f"Contents API 'sha' must be a 40-char lowercase hex string, got {data['sha']!r}"
        )

    if data["encoding"] != "base64":
        raise GitHubAPIResponseError(
            f"Contents API 'encoding' must be 'base64', got {data['encoding']!r}"
        )

    if not isinstance(data["size"], int):
        raise GitHubAPIResponseError(
            f"Contents API 'size' must be an integer, got {type(data['size']).__name__!r}"
        )

    return data


def validate_commits_response(data: Any) -> list[dict[str, Any]]:
    """Validate a response from ``GET /repos/{owner}/{repo}/commits``.

    Returns the validated list.  Raises ``GitHubAPIResponseError`` on any shape
    violation:

    - Not a list.
    - Empty list.  An empty commits list is treated as an API shape violation
      because ``check_drift.py`` queries this endpoint only for files known to
      exist in the registry (i.e., files that were previously ingested and must
      have at least one commit).  An empty result therefore indicates either an
      unexpected API change or a request that points at the wrong path.
    - First item missing a non-empty ``sha`` string field.

    The caller is responsible for mapping this exception to
    ``GitHubMonitorReasonCode.FETCH_FAILED``.
    """
    if not isinstance(data, list):
        raise GitHubAPIResponseError(
            f"Expected list from commits API, got {type(data).__name__!r}"
        )

    if not data:
        raise GitHubAPIResponseError("Commits API returned an empty list")

    first = data[0]
    if not isinstance(first, dict):
        raise GitHubAPIResponseError(
            f"Commits API list item must be a dict, got {type(first).__name__!r}"
        )

    if "sha" not in first or not isinstance(first["sha"], str) or not first["sha"]:
        raise GitHubAPIResponseError(
            f"Commits API list item missing valid 'sha' field: {first!r}"
        )

    return data


# ---------------------------------------------------------------------------
# Registry validation
# ---------------------------------------------------------------------------


def validate_registry_file(data: Any) -> RegistryFile:
    """Validate the parsed JSON of a ``*.source-registry.json`` file.

    Raises ``ValueError`` on any schema violation:

    - Wrong top-level type or missing required keys.
    - ``version`` field does not equal ``REGISTRY_VERSION``.
    - ``owner`` or ``repo`` are not non-empty strings.
    - ``entries`` is not a list.
    - Any entry is missing required keys ``path`` or ``tracking_status``.
    - Any entry has an unrecognised ``tracking_status`` value.
    - Any SHA field present is not a 40-char lowercase hex string.
    - Any SHA-256 field present is not a 64-char lowercase hex string.

    Callers should map this exception to an appropriate reason code and fail
    closed rather than continuing with a partially-validated registry.
    """
    if not isinstance(data, dict):
        raise ValueError(
            f"Registry must be a JSON object, got {type(data).__name__!r}"
        )

    for key in ("version", "owner", "repo", "entries"):
        if key not in data:
            raise ValueError(f"Registry missing required field {key!r}")

    if data["version"] != REGISTRY_VERSION:
        raise ValueError(
            f"Registry version must be {REGISTRY_VERSION!r}, got {data['version']!r}"
        )

    for key in ("owner", "repo"):
        if not isinstance(data[key], str) or not data[key].strip():
            raise ValueError(
                f"Registry {key!r} must be a non-empty string, got {data[key]!r}"
            )

    if not isinstance(data["entries"], list):
        raise ValueError(
            f"Registry 'entries' must be a list, got {type(data['entries']).__name__!r}"
        )

    for idx, entry in enumerate(data["entries"]):
        _validate_registry_entry(entry, idx)

    return data  # type: ignore[return-value]


def _validate_registry_entry(entry: Any, idx: int) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"Registry entry {idx} must be an object")

    for key in ("path", "tracking_status"):
        if key not in entry:
            raise ValueError(f"Registry entry {idx} missing required field {key!r}")
        if not isinstance(entry[key], str) or not entry[key]:
            raise ValueError(
                f"Registry entry {idx} field {key!r} must be a non-empty string"
            )

    if entry["tracking_status"] not in _VALID_TRACKING_STATUSES:
        raise ValueError(
            f"Registry entry {idx} has unrecognised tracking_status "
            f"{entry['tracking_status']!r}; valid values: {sorted(_VALID_TRACKING_STATUSES)}"
        )

    for sha_key in ("last_applied_commit_sha", "last_fetched_commit_sha"):
        v = entry.get(sha_key)
        if v is not None and not _COMMIT_SHA_RE.match(v):
            raise ValueError(
                f"Registry entry {idx} field {sha_key!r} must be a 40-char "
                f"lowercase hex string or null, got {v!r}"
            )

    for sha_key in ("last_applied_blob_sha", "last_fetched_blob_sha"):
        v = entry.get(sha_key)
        if v is not None and not _COMMIT_SHA_RE.match(v):
            raise ValueError(
                f"Registry entry {idx} field {sha_key!r} must be a 40-char "
                f"lowercase hex string or null, got {v!r}"
            )

    sha256_v = entry.get("sha256_at_last_applied")
    if sha256_v is not None and not _SHA256_RE.match(sha256_v):
        raise ValueError(
            f"Registry entry {idx} 'sha256_at_last_applied' must be a 64-char "
            f"lowercase hex string or null, got {sha256_v!r}"
        )


# ---------------------------------------------------------------------------
# Drift report validation
# ---------------------------------------------------------------------------


def validate_drift_report(data: Any) -> DriftReport:
    """Validate a parsed drift report JSON object.

    Raises ``ValueError`` on any schema violation.  Used by downstream
    scripts (``fetch_content.py``, ``synthesize_diff.py``) that consume
    the drift report produced by ``check_drift.py``.
    """
    if not isinstance(data, dict):
        raise ValueError(
            f"Drift report must be a JSON object, got {type(data).__name__!r}"
        )

    for key in ("version", "generated_at", "registry", "has_drift", "drifted",
                "up_to_date", "uninitialized", "errors"):
        if key not in data:
            raise ValueError(f"Drift report missing required field {key!r}")

    if data["version"] != DRIFT_REPORT_VERSION:
        raise ValueError(
            f"Drift report version must be {DRIFT_REPORT_VERSION!r}, "
            f"got {data['version']!r}"
        )

    for list_key in ("drifted", "up_to_date", "uninitialized", "errors"):
        if not isinstance(data[list_key], list):
            raise ValueError(
                f"Drift report {list_key!r} must be a list, "
                f"got {type(data[list_key]).__name__!r}"
            )

    if not isinstance(data["has_drift"], bool):
        raise ValueError(
            f"Drift report 'has_drift' must be a bool, "
            f"got {type(data['has_drift']).__name__!r}"
        )

    for i, entry in enumerate(data["drifted"]):
        _validate_drifted_entry(entry, i)

    return data  # type: ignore[return-value]


def _validate_drifted_entry(entry: Any, idx: int) -> None:
    """Validate one entry from the ``drifted`` list of a drift report."""
    if not isinstance(entry, dict):
        raise ValueError(f"drifted[{idx}] must be a JSON object")

    for key in ("owner", "repo", "path", "current_commit_sha", "current_blob_sha"):
        if key not in entry:
            raise ValueError(f"drifted[{idx}] missing required field {key!r}")
        if not isinstance(entry[key], str) or not entry[key]:
            raise ValueError(
                f"drifted[{idx}] field {key!r} must be a non-empty string"
            )

    if not _SAFE_SEGMENT_RE.match(entry["owner"]):
        raise ValueError(
            f"drifted[{idx}]['owner'] contains unsafe characters: {entry['owner']!r}"
        )
    if not _SAFE_SEGMENT_RE.match(entry["repo"]):
        raise ValueError(
            f"drifted[{idx}]['repo'] contains unsafe characters: {entry['repo']!r}"
        )
    if not _COMMIT_SHA_RE.match(entry["current_commit_sha"]):
        raise ValueError(
            f"drifted[{idx}]['current_commit_sha'] must be a 40-char lowercase hex string"
        )

    last_applied = entry.get("last_applied_commit_sha")
    if last_applied is not None:
        if not isinstance(last_applied, str) or not _COMMIT_SHA_RE.match(last_applied):
            raise ValueError(
                f"drifted[{idx}]['last_applied_commit_sha'] must be a 40-char "
                f"lowercase hex string or null"
            )
