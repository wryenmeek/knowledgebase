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
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Protocol, TypedDict

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
_MONITORED_TRACKING_STATUSES = frozenset({"active", "uninitialized"})
_MAX_CHANGED_PATHS = 200
_MAX_REGISTRY_PATH_LENGTH = 256
_MAX_IDENTIFIER_LENGTH = 128


class UpstreamSourceUpdatedPayload(TypedDict):
    """Stable payload contract for event_type=upstream-source-updated."""

    registry_path: str
    owner: str
    repo: str
    changed_paths: list[str]
    delivery_id: str
    event_name: str


@dataclass(frozen=True)
class GitHubPushEvent:
    """Validated subset of a GitHub push webhook event."""

    owner: str
    repo: str
    changed_paths: tuple[str, ...]
    delivery_id: str
    event_name: str


@dataclass(frozen=True)
class GitHubRelayResult:
    """Result envelope returned by ``relay_github_push_event()``."""

    status: str
    reason: str
    dispatched_count: int
    payloads: tuple[UpstreamSourceUpdatedPayload, ...]


class RelayValidationError(ValueError):
    """Raised when webhook headers/body fail validation."""


class GitHubDeliveryReplayCache:
    """Best-effort replay suppression keyed by ``X-GitHub-Delivery``."""

    def __init__(self, *, ttl_seconds: int = 86_400, max_entries: int = 20_000) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._ttl_seconds = float(ttl_seconds)
        self._max_entries = max_entries
        self._expirations: dict[str, float] = {}
        self._inflight: set[str] = set()
        self._lock = threading.Lock()

    def check_and_record(self, delivery_id: str, *, now: float | None = None) -> bool:
        if self.reserve(delivery_id, now=now):
            return True
        self.commit(delivery_id, now=now)
        return False

    def is_replay(self, delivery_id: str, *, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        with self._lock:
            self._evict_expired(current)
            return delivery_id in self._expirations or delivery_id in self._inflight

    def reserve(self, delivery_id: str, *, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        with self._lock:
            self._evict_expired(current)
            if delivery_id in self._expirations or delivery_id in self._inflight:
                return True
            self._inflight.add(delivery_id)
            return False

    def commit(self, delivery_id: str, *, now: float | None = None) -> None:
        current = time.time() if now is None else now
        with self._lock:
            self._evict_expired(current)
            self._inflight.discard(delivery_id)
            self._record_unlocked(delivery_id, current)

    def rollback(self, delivery_id: str) -> None:
        with self._lock:
            self._inflight.discard(delivery_id)

    def record(self, delivery_id: str, *, now: float | None = None) -> None:
        self.commit(delivery_id, now=now)

    def _record_unlocked(self, delivery_id: str, now: float) -> None:
        if len(self._expirations) >= self._max_entries:
            oldest_key = min(self._expirations, key=self._expirations.get)
            self._expirations.pop(oldest_key, None)
        self._expirations[delivery_id] = now + self._ttl_seconds

    def _evict_expired(self, now: float) -> None:
        expired_keys = [k for k, expiry in self._expirations.items() if expiry <= now]
        for key in expired_keys:
            self._expirations.pop(key, None)


class GitHubReplayCache(Protocol):
    """Replay cache contract for delivery-ID suppression."""

    def check_and_record(self, delivery_id: str, *, now: float | None = None) -> bool:
        """Return True when delivery_id is replayed, else record and return False."""

    def is_replay(self, delivery_id: str, *, now: float | None = None) -> bool:
        """Return True when delivery_id has already been recorded."""

    def reserve(self, delivery_id: str, *, now: float | None = None) -> bool:
        """Atomically reserve a delivery_id; return True when replayed."""

    def commit(self, delivery_id: str, *, now: float | None = None) -> None:
        """Commit a reserved delivery_id after successful dispatch."""

    def rollback(self, delivery_id: str) -> None:
        """Release a reserved delivery_id after dispatch failure."""

    def record(self, delivery_id: str, *, now: float | None = None) -> None:
        """Record delivery_id after successful dispatch."""


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

    try:
        changed_paths = extract_changed_paths(payload)
    except ValueError as exc:
        raise RelayValidationError(f"invalid changed path in push payload: {exc}") from exc
    return GitHubPushEvent(
        owner=owner_login,
        repo=repo_name,
        changed_paths=changed_paths,
        delivery_id=delivery_id,
        event_name=event_name,
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
    owner: str,
    repo: str,
    changed_paths: list[str],
    delivery_id: str,
    event_name: str,
) -> UpstreamSourceUpdatedPayload:
    payload: UpstreamSourceUpdatedPayload = {
        "registry_path": registry_path,
        "owner": owner,
        "repo": repo,
        "changed_paths": changed_paths,
        "delivery_id": delivery_id,
        "event_name": event_name,
    }
    return validate_upstream_source_payload(payload)


def validate_upstream_source_payload(
    payload: Mapping[str, Any],
) -> UpstreamSourceUpdatedPayload:
    """Validate the stable payload contract for CI-5 dispatch events."""

    expected_fields = {
        "registry_path",
        "owner",
        "repo",
        "changed_paths",
        "delivery_id",
        "event_name",
    }
    extra_fields = sorted(set(payload.keys()) - expected_fields)
    if extra_fields:
        raise RelayValidationError(
            f"payload contains unexpected field(s): {', '.join(extra_fields)}"
        )

    required_fields = (
        "registry_path",
        "owner",
        "repo",
        "delivery_id",
        "event_name",
    )
    for field in required_fields:
        value = payload.get(field)
        if not isinstance(value, str) or not value:
            raise RelayValidationError(f"payload field {field!r} must be a string")
        if field == "registry_path" and len(value) > _MAX_REGISTRY_PATH_LENGTH:
            raise RelayValidationError("payload field 'registry_path' exceeds max length")
        if field != "registry_path" and len(value) > _MAX_IDENTIFIER_LENGTH:
            raise RelayValidationError(f"payload field {field!r} exceeds max length")
    if payload["event_name"] != "push":
        raise RelayValidationError("payload field 'event_name' must be 'push'")
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

    registry_path = payload["registry_path"]
    registry_parts = PurePosixPath(registry_path).parts
    if (
        PurePosixPath(registry_path).is_absolute()
        or ".." in registry_parts
        or not registry_path.startswith("raw/github-sources/")
        or not registry_path.endswith(".source-registry.json")
    ):
        raise RelayValidationError("payload field 'registry_path' is invalid")

    validated: UpstreamSourceUpdatedPayload = {
        "registry_path": registry_path,
        "owner": str(payload["owner"]),
        "repo": str(payload["repo"]),
        "changed_paths": sorted(set(normalized_changed_paths)),
        "delivery_id": str(payload["delivery_id"]),
        "event_name": str(payload["event_name"]),
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
                owner=push_event.owner,
                repo=push_event.repo,
                changed_paths=matching_paths,
                delivery_id=push_event.delivery_id,
                event_name=push_event.event_name,
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


__all__ = [
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
