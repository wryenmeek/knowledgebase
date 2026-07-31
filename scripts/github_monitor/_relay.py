"""GitHub webhook relay helpers for CI-5 repository_dispatch triggering.

This module is intentionally HTTP-framework agnostic.  A webhook receiver
(Cloud Run, Flask, FastAPI, etc.) can pass request headers/body to
``relay_github_push_event()`` and use the returned status to decide the HTTP
response code.
"""

from __future__ import annotations

import glob as glob_module
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Protocol, TypedDict

from scripts.replay_cache import InMemoryReplayReservationCache
from scripts.github_monitor.dispatch_client import (
    GitHubApiDispatchClient,
    RepositoryDispatchClient,
    RepositoryDispatchError,
)
from scripts.github_monitor._types import validate_registry_file
from scripts.github_monitor._validators import validate_external_path

_GITHUB_EVENT_HEADER = "x-github-event"
_GITHUB_DELIVERY_HEADER = "x-github-delivery"
_GITHUB_SIGNATURE_HEADER = "x-hub-signature-256"
_SIGNATURE_PREFIX = "sha256="
_HEX_DIGITS = frozenset("0123456789abcdef")
_UPSTREAM_SOURCE_UPDATED_EVENT = "upstream-source-updated"
_GITHUB_SOURCE_KIND = "github"
_MONITORED_TRACKING_STATUSES = frozenset({"active", "uninitialized"})
_MAX_CHANGED_PATHS = 200
_MAX_REGISTRY_PATH_LENGTH = 256
_MAX_UPSTREAM_REPO_LENGTH = 256
_MAX_UPSTREAM_REF_LENGTH = 256
_MAX_IDENTIFIER_LENGTH = 128
_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DELIVERY_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
_SAFE_REPO_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class UpstreamSourceUpdatedPayload(TypedDict):
    """Stable payload contract for event_type=upstream-source-updated."""

    source_kind: str
    registry_path: str
    upstream_repo: str
    upstream_ref: str
    upstream_after_sha: str
    changed_paths: list[str]
    delivery_id: str
    observed_at: str


@dataclass(frozen=True)
class GitHubPushEvent:
    """Validated subset of a GitHub push webhook event."""

    owner: str
    repo: str
    ref: str
    after_sha: str
    changed_paths: tuple[str, ...]
    delivery_id: str
    observed_at: str


@dataclass(frozen=True)
class GitHubRelayResult:
    """Result envelope returned by ``relay_github_push_event()``."""

    status: str
    reason: str
    dispatched_count: int
    payloads: tuple[UpstreamSourceUpdatedPayload, ...]


class RelayValidationError(ValueError):
    """Raised when webhook headers/body fail validation."""


class GitHubDeliveryReplayCache(InMemoryReplayReservationCache):
    """Best-effort replay suppression keyed by ``X-GitHub-Delivery``."""

    def __init__(self, *, ttl_seconds: int = 86_400, max_entries: int = 20_000) -> None:
        super().__init__(ttl_seconds=ttl_seconds, max_entries=max_entries)


class GitHubReplayCache(Protocol):
    """Replay cache contract for delivery-ID suppression."""

    def reserve(self, delivery_id: str, *, now: float | None = None) -> bool:
        """Atomically reserve a delivery_id; return True when replayed."""

    def commit(self, delivery_id: str, *, now: float | None = None) -> None:
        """Commit a reserved delivery_id after successful dispatch."""

    def rollback(self, delivery_id: str) -> None:
        """Release a reserved delivery_id after dispatch failure."""


_DEFAULT_REPLAY_CACHE = GitHubDeliveryReplayCache()


def _normalize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in headers.items()}


def validate_github_signature(
    *,
    webhook_secret: str,
    body: bytes,
    signature_header: str | None,
) -> bool:
    """Return ``True`` when ``X-Hub-Signature-256`` matches ``body``."""

    if not webhook_secret or not signature_header:
        return False
    if not signature_header.startswith(_SIGNATURE_PREFIX):
        return False
    signature_hex = signature_header[len(_SIGNATURE_PREFIX) :].strip().lower()
    if len(signature_hex) != 64:
        return False
    if any(ch not in _HEX_DIGITS for ch in signature_hex):
        return False
    expected = hmac.new(
        webhook_secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature_hex, expected)


def extract_changed_paths(push_payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Return normalized changed paths from ``commits[].{added,modified,removed}``."""

    changed_paths: set[str] = set()
    commits = push_payload.get("commits")
    if not isinstance(commits, list):
        return ()
    for commit in commits:
        if not isinstance(commit, dict):
            continue
        for key in ("added", "modified", "removed"):
            values = commit.get(key)
            if not isinstance(values, list):
                continue
            for value in values:
                if not isinstance(value, str) or not value:
                    continue
                changed_paths.add(validate_external_path(value))
    return tuple(sorted(changed_paths))


def parse_github_push_event(
    *, headers: Mapping[str, str], body: bytes, webhook_secret: str
) -> GitHubPushEvent | None:
    """Validate and parse a GitHub push webhook event.

    Returns ``None`` for non-push events.
    Raises ``RelayValidationError`` for malformed/unsigned payloads.
    """

    normalized_headers = _normalize_headers(headers)
    event_name = normalized_headers.get(_GITHUB_EVENT_HEADER)
    if not event_name:
        raise RelayValidationError("missing X-GitHub-Event header")

    delivery_id = normalized_headers.get(_GITHUB_DELIVERY_HEADER)
    if not delivery_id:
        raise RelayValidationError("missing X-GitHub-Delivery header")
    delivery_id = delivery_id.strip()
    if (
        not delivery_id
        or len(delivery_id) > _MAX_IDENTIFIER_LENGTH
        or not _DELIVERY_ID_RE.fullmatch(delivery_id)
    ):
        raise RelayValidationError("invalid X-GitHub-Delivery header")

    signature_header = normalized_headers.get(_GITHUB_SIGNATURE_HEADER)
    if not validate_github_signature(
        webhook_secret=webhook_secret,
        body=body,
        signature_header=signature_header,
    ):
        raise RelayValidationError("invalid X-Hub-Signature-256 header")

    if event_name != "push":
        return None

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RelayValidationError(f"invalid webhook JSON body: {exc}") from exc

    if not isinstance(payload, dict):
        raise RelayValidationError("webhook JSON body must be an object")

    repository = payload.get("repository")
    if not isinstance(repository, dict):
        raise RelayValidationError("push payload missing repository object")

    repo_name = repository.get("name")
    owner_obj = repository.get("owner")
    if not isinstance(repo_name, str) or not repo_name:
        raise RelayValidationError("push payload repository.name is required")
    if not isinstance(owner_obj, dict):
        raise RelayValidationError("push payload repository.owner is required")

    owner_login = owner_obj.get("login") or owner_obj.get("name")
    if not isinstance(owner_login, str) or not owner_login:
        raise RelayValidationError(
            "push payload repository.owner.login (or owner.name) is required"
        )
    repo_name = repo_name.strip()
    owner_login = owner_login.strip()
    if not _SAFE_REPO_SEGMENT_RE.fullmatch(repo_name):
        raise RelayValidationError(
            "push payload repository.name contains unsafe characters"
        )
    if not _SAFE_REPO_SEGMENT_RE.fullmatch(owner_login):
        raise RelayValidationError(
            "push payload repository.owner.login contains unsafe characters"
        )

    ref = payload.get("ref")
    if not isinstance(ref, str) or not ref.strip():
        raise RelayValidationError("push payload ref is required")
    ref = _validate_upstream_ref(ref)

    after_raw = payload.get("after")
    if not isinstance(after_raw, str) or not after_raw.strip():
        raise RelayValidationError("push payload after is required")
    after_sha = _normalize_commit_sha(after_raw)

    try:
        changed_paths = extract_changed_paths(payload)
    except ValueError as exc:
        raise RelayValidationError(
            f"invalid changed path in push payload: {exc}"
        ) from exc
    return GitHubPushEvent(
        owner=owner_login,
        repo=repo_name,
        ref=ref,
        after_sha=after_sha,
        changed_paths=changed_paths,
        delivery_id=delivery_id,
        observed_at=_format_utc_iso8601(_current_utc_datetime()),
    )


def _safe_repo_relative(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _normalize_registry_entry_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return validate_external_path(value)
    except ValueError:
        return None


def _current_utc_datetime() -> datetime:
    return datetime.now(timezone.utc)


def _format_utc_iso8601(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


def _parse_observed_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RelayValidationError(
            "payload field 'observed_at' must be a valid ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise RelayValidationError(
            "payload field 'observed_at' must include timezone information"
        )
    return parsed.astimezone(timezone.utc)


def _normalize_commit_sha(value: str) -> str:
    normalized = value.strip().lower()
    if not _COMMIT_SHA_RE.fullmatch(normalized):
        raise RelayValidationError("upstream commit SHA must be a 40-char hex string")
    return normalized


def _validate_upstream_repo(value: str) -> str:
    normalized = value.strip()
    if len(normalized) > _MAX_UPSTREAM_REPO_LENGTH:
        raise RelayValidationError("payload field 'upstream_repo' exceeds max length")
    parts = normalized.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise RelayValidationError(
            "payload field 'upstream_repo' must be formatted as '<owner>/<repo>'"
        )
    owner, repo = parts
    if not _SAFE_REPO_SEGMENT_RE.fullmatch(
        owner
    ) or not _SAFE_REPO_SEGMENT_RE.fullmatch(repo):
        raise RelayValidationError(
            "payload field 'upstream_repo' contains unsafe characters"
        )
    return f"{owner}/{repo}"


def _validate_upstream_ref(value: str) -> str:
    normalized = value.strip()
    if len(normalized) > _MAX_UPSTREAM_REF_LENGTH:
        raise RelayValidationError("payload field 'upstream_ref' exceeds max length")
    if any(ord(ch) < 0x20 for ch in normalized):
        raise RelayValidationError(
            "payload field 'upstream_ref' contains control characters"
        )
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or not normalized.startswith("refs/"):
        raise RelayValidationError("payload field 'upstream_ref' is invalid")
    return path.as_posix()


def _intersect_monitored_paths(
    *, registry: Mapping[str, Any], changed_paths: tuple[str, ...]
) -> list[str]:
    changed = set(changed_paths)
    tracked: set[str] = set()
    entries = registry.get("entries")
    if not isinstance(entries, list):
        return []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("tracking_status") not in _MONITORED_TRACKING_STATUSES:
            continue
        normalized = _normalize_registry_entry_path(entry.get("path"))
        if normalized is not None:
            tracked.add(normalized)
    return sorted(changed.intersection(tracked))


def build_upstream_source_payload(
    *,
    registry_path: str,
    upstream_repo: str,
    upstream_ref: str,
    upstream_after_sha: str,
    observed_at: str,
    changed_paths: list[str],
    delivery_id: str,
) -> UpstreamSourceUpdatedPayload:
    payload: UpstreamSourceUpdatedPayload = {
        "source_kind": _GITHUB_SOURCE_KIND,
        "registry_path": registry_path,
        "upstream_repo": upstream_repo,
        "upstream_ref": upstream_ref,
        "upstream_after_sha": upstream_after_sha,
        "observed_at": observed_at,
        "changed_paths": changed_paths,
        "delivery_id": delivery_id,
    }
    return validate_upstream_source_payload(payload)


def validate_upstream_source_payload(
    payload: Mapping[str, Any],
) -> UpstreamSourceUpdatedPayload:
    """Validate the stable payload contract for CI-5 dispatch events."""

    expected_fields = {
        "source_kind",
        "registry_path",
        "upstream_repo",
        "upstream_ref",
        "upstream_after_sha",
        "observed_at",
        "changed_paths",
        "delivery_id",
    }
    # ⚡ Bolt: Use dict view set operations to avoid intermediate set creation
    extra_fields = sorted(payload.keys() - expected_fields)
    if extra_fields:
        raise RelayValidationError(
            f"payload contains unexpected field(s): {', '.join(extra_fields)}"
        )

    source_kind = payload.get("source_kind")
    if source_kind != _GITHUB_SOURCE_KIND:
        raise RelayValidationError("payload field 'source_kind' must be 'github'")

    required_fields = (
        "registry_path",
        "upstream_repo",
        "upstream_ref",
        "upstream_after_sha",
        "observed_at",
        "delivery_id",
    )
    normalized_values: dict[str, str] = {}
    for field in required_fields:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise RelayValidationError(f"payload field {field!r} must be a string")
        normalized_values[field] = value.strip()

    if len(normalized_values["registry_path"]) > _MAX_REGISTRY_PATH_LENGTH:
        raise RelayValidationError("payload field 'registry_path' exceeds max length")
    if len(normalized_values["upstream_repo"]) > _MAX_UPSTREAM_REPO_LENGTH:
        raise RelayValidationError("payload field 'upstream_repo' exceeds max length")
    if len(normalized_values["upstream_ref"]) > _MAX_UPSTREAM_REF_LENGTH:
        raise RelayValidationError("payload field 'upstream_ref' exceeds max length")
    if len(normalized_values["delivery_id"]) > _MAX_IDENTIFIER_LENGTH:
        raise RelayValidationError("payload field 'delivery_id' exceeds max length")

    if not _DELIVERY_ID_RE.fullmatch(normalized_values["delivery_id"]):
        raise RelayValidationError(
            "payload field 'delivery_id' contains unsafe characters"
        )

    changed_paths = payload.get("changed_paths")
    if not isinstance(changed_paths, list):
        raise RelayValidationError("payload field 'changed_paths' must be a list")
    if not changed_paths:
        raise RelayValidationError("payload field 'changed_paths' must not be empty")
    if len(changed_paths) > _MAX_CHANGED_PATHS:
        raise RelayValidationError(
            f"payload field 'changed_paths' exceeds max count {_MAX_CHANGED_PATHS}"
        )
    normalized_changed_paths: list[str] = []
    for path in changed_paths:
        if not isinstance(path, str) or not path:
            raise RelayValidationError(
                "payload field 'changed_paths' must contain non-empty strings"
            )
        if len(path) > _MAX_REGISTRY_PATH_LENGTH:
            raise RelayValidationError(
                "payload field 'changed_paths' contains path exceeding max length"
            )
        try:
            normalized_changed_paths.append(validate_external_path(path))
        except ValueError as exc:
            raise RelayValidationError(str(exc)) from exc

    registry_path = normalized_values["registry_path"]
    registry_parts = PurePosixPath(registry_path).parts
    if (
        PurePosixPath(registry_path).is_absolute()
        or ".." in registry_parts
        or not registry_path.startswith("raw/github-sources/")
        or not registry_path.endswith(".source-registry.json")
    ):
        raise RelayValidationError("payload field 'registry_path' is invalid")

    upstream_repo = _validate_upstream_repo(normalized_values["upstream_repo"])
    upstream_ref = _validate_upstream_ref(normalized_values["upstream_ref"])
    upstream_after_sha = _normalize_commit_sha(normalized_values["upstream_after_sha"])
    observed_at = _format_utc_iso8601(
        _parse_observed_at(normalized_values["observed_at"])
    )

    validated: UpstreamSourceUpdatedPayload = {
        "source_kind": _GITHUB_SOURCE_KIND,
        "registry_path": registry_path,
        "upstream_repo": upstream_repo,
        "upstream_ref": upstream_ref,
        "upstream_after_sha": upstream_after_sha,
        "observed_at": observed_at,
        "changed_paths": sorted(set(normalized_changed_paths)),
        "delivery_id": normalized_values["delivery_id"],
    }
    return validated


def plan_upstream_source_dispatches(
    *,
    repo_root: Path,
    push_event: GitHubPushEvent,
) -> list[UpstreamSourceUpdatedPayload]:
    """Build per-registry repository_dispatch payloads for a push event."""

    if not push_event.changed_paths:
        return []

    registry_pattern = (
        repo_root / "raw" / "github-sources" / "*.source-registry.json"
    ).as_posix()
    payloads: list[UpstreamSourceUpdatedPayload] = []
    for path_string in sorted(glob_module.glob(registry_pattern)):
        registry_file = Path(path_string)
        try:
            parsed = json.loads(registry_file.read_text(encoding="utf-8"))
            registry = validate_registry_file(parsed)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise RelayValidationError(
                f"registry file is unreadable/invalid: {registry_file}: {exc}"
            ) from exc
        if (
            registry.get("owner") != push_event.owner
            or registry.get("repo") != push_event.repo
        ):
            continue
        matching_paths = _intersect_monitored_paths(
            registry=registry,
            changed_paths=push_event.changed_paths,
        )
        if not matching_paths:
            continue
        try:
            registry_path = _safe_repo_relative(registry_file, repo_root)
        except (OSError, ValueError) as exc:
            raise RelayValidationError(
                f"registry path escaped repo root: {registry_file}: {exc}"
            ) from exc
        payloads.append(
            build_upstream_source_payload(
                registry_path=registry_path,
                upstream_repo=f"{push_event.owner}/{push_event.repo}",
                upstream_ref=push_event.ref,
                upstream_after_sha=push_event.after_sha,
                observed_at=push_event.observed_at,
                changed_paths=matching_paths,
                delivery_id=push_event.delivery_id,
            )
        )
    return payloads


def relay_github_push_event(
    *,
    repo_root: Path,
    headers: Mapping[str, str],
    body: bytes,
    webhook_secret: str,
    dispatch_client: RepositoryDispatchClient,
    replay_cache: GitHubReplayCache | None = None,
) -> GitHubRelayResult:
    """Validate a webhook event, path-filter, and emit repository_dispatch."""

    try:
        push_event = parse_github_push_event(
            headers=headers,
            body=body,
            webhook_secret=webhook_secret,
        )
    except RelayValidationError as exc:
        return GitHubRelayResult(
            status="rejected",
            reason=str(exc),
            dispatched_count=0,
            payloads=(),
        )

    if push_event is None:
        return GitHubRelayResult(
            status="ignored",
            reason="event_not_push",
            dispatched_count=0,
            payloads=(),
        )

    try:
        payloads = tuple(
            plan_upstream_source_dispatches(repo_root=repo_root, push_event=push_event)
        )
    except RelayValidationError as exc:
        return GitHubRelayResult(
            status="rejected",
            reason=str(exc),
            dispatched_count=0,
            payloads=(),
        )
    if not payloads:
        return GitHubRelayResult(
            status="ignored",
            reason="no_registry_match_or_path_intersection",
            dispatched_count=0,
            payloads=(),
        )

    effective_replay_cache = replay_cache or _DEFAULT_REPLAY_CACHE
    if effective_replay_cache.reserve(push_event.delivery_id):
        return GitHubRelayResult(
            status="ignored",
            reason="replay_suppressed",
            dispatched_count=0,
            payloads=(),
        )

    dispatched_count = 0
    try:
        for payload in payloads:
            dispatch_client.dispatch(
                event_type=_UPSTREAM_SOURCE_UPDATED_EVENT,
                client_payload=payload,
            )
            dispatched_count += 1
    except Exception as exc:  # pragma: no cover - defensive envelope
        effective_replay_cache.rollback(push_event.delivery_id)
        return GitHubRelayResult(
            status="failed",
            reason=f"dispatch_failed: {exc}",
            dispatched_count=dispatched_count,
            payloads=payloads,
        )

    effective_replay_cache.commit(push_event.delivery_id)
    return GitHubRelayResult(
        status="dispatched",
        reason="ok",
        dispatched_count=dispatched_count,
        payloads=payloads,
    )


def externalize_relay_reason(*, status: str, reason: str) -> str:
    """Return an external-safe reason string for HTTP/webhook responses."""

    if status == "rejected":
        return "request_rejected"
    if status == "failed":
        return "relay_failed"
    return reason


__all__ = [
    "externalize_relay_reason",
    "GitHubApiDispatchClient",
    "GitHubDeliveryReplayCache",
    "GitHubReplayCache",
    "GitHubPushEvent",
    "GitHubRelayResult",
    "RelayValidationError",
    "RepositoryDispatchClient",
    "RepositoryDispatchError",
    "UpstreamSourceUpdatedPayload",
    "build_upstream_source_payload",
    "extract_changed_paths",
    "parse_github_push_event",
    "plan_upstream_source_dispatches",
    "relay_github_push_event",
    "validate_github_signature",
    "validate_upstream_source_payload",
]
