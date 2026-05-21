"""Drive webhook relay helpers for CI-6 repository_dispatch triggering.

This module validates Drive push-notification headers, enforces replay
suppression, and emits ``repository_dispatch`` with a stable payload contract.
It is intentionally HTTP-framework agnostic.
"""

from __future__ import annotations

import base64
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
from scripts.drive_monitor._types import validate_drive_registry_file
from scripts.drive_monitor._validators import validate_alias, validate_file_id

_DRIVE_SOURCE_UPDATED_EVENT = "drive-source-updated"
_DRIVE_CHANNEL_TOKEN_PREFIX = "kbdrv1"
_HEX_DIGITS = frozenset("0123456789abcdef")

_HEADER_CHANNEL_ID = "x-goog-channel-id"
_HEADER_CHANNEL_TOKEN = "x-goog-channel-token"
_HEADER_RESOURCE_ID = "x-goog-resource-id"
_HEADER_RESOURCE_STATE = "x-goog-resource-state"
_HEADER_MESSAGE_NUMBER = "x-goog-message-number"
_HEADER_FILE_ID = "x-goog-file-id"
_HEADER_FILE_IDS = "x-goog-file-ids"

_IGNORED_RESOURCE_STATES = frozenset({"sync", "heartbeat"})
_RELEVANT_RESOURCE_STATES = frozenset(
    {
        "add",
        "change",
        "content_changed",
        "exists",
        "not_exists",
        "remove",
        "trash",
        "untrash",
        "update",
    }
)
_MAX_FILE_IDS = 200
_MAX_REGISTRY_PATH_LENGTH = 256
_MAX_IDENTIFIER_LENGTH = 128


class DriveSourceUpdatedPayload(TypedDict):
    """Stable payload contract for event_type=drive-source-updated."""

    alias: str
    registry_path: str
    file_ids: list[str]
    channel_id: str
    resource_id: str
    resource_state: str
    message_number: int


class DriveChannelTokenContext(TypedDict):
    """Validated context decoded from ``X-Goog-Channel-Token``."""

    alias: str
    registry_path: str
    file_ids: list[str]


@dataclass(frozen=True)
class DriveNotification:
    """Validated Drive notification header subset."""

    alias: str
    registry_path: str
    file_ids: tuple[str, ...]
    channel_id: str
    resource_id: str
    resource_state: str
    message_number: int


@dataclass(frozen=True)
class DriveRelayResult:
    """Result envelope returned by ``relay_drive_notification()``."""

    status: str
    reason: str
    dispatched: bool
    payload: DriveSourceUpdatedPayload | None


class RelayValidationError(ValueError):
    """Raised when Drive headers/token/context are invalid."""


class DriveReplayCache:
    """In-memory replay suppression keyed by Drive channel/resource headers."""

    def __init__(self, *, ttl_seconds: int = 3600, max_entries: int = 20_000) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._ttl_seconds = float(ttl_seconds)
        self._max_entries = max_entries
        self._expirations: dict[str, float] = {}
        self._inflight: set[str] = set()
        self._lock = threading.Lock()

    def check_and_record(self, key: str, *, now: float | None = None) -> bool:
        """Return ``True`` for replay, else record and return ``False``."""

        if self.reserve(key, now=now):
            return True
        self.commit(key, now=now)
        return False

    def is_replay(self, key: str, *, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        with self._lock:
            self._evict_expired(current)
            return key in self._expirations or key in self._inflight

    def reserve(self, key: str, *, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        with self._lock:
            self._evict_expired(current)
            if key in self._expirations or key in self._inflight:
                return True
            self._inflight.add(key)
            return False

    def commit(self, key: str, *, now: float | None = None) -> None:
        current = time.time() if now is None else now
        with self._lock:
            self._evict_expired(current)
            self._inflight.discard(key)
            self._record_unlocked(key, current)

    def rollback(self, key: str) -> None:
        with self._lock:
            self._inflight.discard(key)

    def record(self, key: str, *, now: float | None = None) -> None:
        self.commit(key, now=now)

    def _record_unlocked(self, key: str, now: float) -> None:
        if len(self._expirations) >= self._max_entries:
            oldest_key = min(self._expirations, key=self._expirations.get)
            self._expirations.pop(oldest_key, None)
        self._expirations[key] = now + self._ttl_seconds

    def _evict_expired(self, now: float) -> None:
        expired_keys = [k for k, expiry in self._expirations.items() if expiry <= now]
        for key in expired_keys:
            self._expirations.pop(key, None)


# Explicit concrete alias used in operator docs/examples.
InMemoryDriveReplayCache = DriveReplayCache


class DriveReplayStore(Protocol):
    """Replay cache/store contract for notification dedupe."""

    def check_and_record(self, key: str, *, now: float | None = None) -> bool:
        """Return True when key is replayed, else record and return False."""

    def is_replay(self, key: str, *, now: float | None = None) -> bool:
        """Return True when key has already been recorded."""

    def reserve(self, key: str, *, now: float | None = None) -> bool:
        """Atomically reserve a key; return True when replayed."""

    def commit(self, key: str, *, now: float | None = None) -> None:
        """Commit a reserved key after successful dispatch."""

    def rollback(self, key: str) -> None:
        """Release a reserved key after dispatch failure."""

    def record(self, key: str, *, now: float | None = None) -> None:
        """Record key after successful dispatch."""


def _normalize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in headers.items()}


def _require_header(headers: Mapping[str, str], header_name: str) -> str:
    value = headers.get(header_name)
    if not value:
        raise RelayValidationError(f"missing {header_name} header")
    return value.strip()


def _validate_registry_path_literal(registry_path: str) -> str:
    if not isinstance(registry_path, str) or not registry_path:
        raise RelayValidationError("registry_path must be a non-empty string")
    candidate = PurePosixPath(registry_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise RelayValidationError("registry_path must be relative and traversal-safe")
    normalized = candidate.as_posix()
    if not normalized.startswith("raw/drive-sources/"):
        raise RelayValidationError("registry_path must be under raw/drive-sources/")
    if not normalized.endswith(".source-registry.json"):
        raise RelayValidationError("registry_path must end with .source-registry.json")
    return normalized


def _decode_b64url(value: str) -> bytes:
    padding = "=" * ((4 - (len(value) % 4)) % 4)
    return base64.urlsafe_b64decode(value + padding)


def build_drive_channel_token(
    *,
    alias: str,
    registry_path: str,
    token_secret: str,
    file_ids: list[str] | None = None,
) -> str:
    """Build a signed channel token for Drive push notifications."""

    if not token_secret:
        raise ValueError("token_secret is required")
    try:
        validated_alias = validate_alias(alias)
        validated_registry_path = _validate_registry_path_literal(registry_path)
    except ValueError as exc:
        raise RelayValidationError(str(exc)) from exc
    validated_file_ids: list[str] = []
    for file_id in file_ids or []:
        if not isinstance(file_id, str):
            raise RelayValidationError("file_ids must contain strings")
        try:
            validated_file_ids.append(validate_file_id(file_id))
        except ValueError as exc:
            raise RelayValidationError(str(exc)) from exc
    context: DriveChannelTokenContext = {
        "alias": validated_alias,
        "registry_path": validated_registry_path,
        "file_ids": sorted(set(validated_file_ids)),
    }
    encoded_context = base64.urlsafe_b64encode(
        json.dumps(context, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(
        token_secret.encode("utf-8"),
        encoded_context.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{_DRIVE_CHANNEL_TOKEN_PREFIX}.{encoded_context}.{signature}"


def parse_drive_channel_token(
    *, token: str, token_secret: str
) -> DriveChannelTokenContext:
    """Validate and decode a signed Drive channel token."""

    if not token_secret:
        raise RelayValidationError("token_secret is required")
    if not token:
        raise RelayValidationError("missing Drive channel token")
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != _DRIVE_CHANNEL_TOKEN_PREFIX:
        raise RelayValidationError("invalid Drive channel token format")
    encoded_context, signature = parts[1], parts[2].lower()
    if len(signature) != 64 or any(ch not in _HEX_DIGITS for ch in signature):
        raise RelayValidationError("invalid Drive channel token signature format")
    expected_signature = hmac.new(
        token_secret.encode("utf-8"),
        encoded_context.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise RelayValidationError("invalid Drive channel token signature")

    try:
        decoded = _decode_b64url(encoded_context).decode("utf-8")
        raw_context = json.loads(decoded)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RelayValidationError(f"invalid Drive channel token payload: {exc}") from exc

    if not isinstance(raw_context, dict):
        raise RelayValidationError("Drive channel token payload must be an object")
    alias = raw_context.get("alias")
    registry_path = raw_context.get("registry_path")
    raw_file_ids = raw_context.get("file_ids") or []
    if not isinstance(alias, str) or not alias:
        raise RelayValidationError("Drive channel token alias is required")
    if not isinstance(registry_path, str) or not registry_path:
        raise RelayValidationError("Drive channel token registry_path is required")
    if not isinstance(raw_file_ids, list):
        raise RelayValidationError("Drive channel token file_ids must be a list")

    validated_file_ids: list[str] = []
    for file_id in raw_file_ids:
        if not isinstance(file_id, str):
            raise RelayValidationError("Drive channel token file_ids must contain strings")
        try:
            validated_file_ids.append(validate_file_id(file_id))
        except ValueError as exc:
            raise RelayValidationError(str(exc)) from exc
    try:
        return {
            "alias": validate_alias(alias),
            "registry_path": _validate_registry_path_literal(registry_path),
            "file_ids": sorted(set(validated_file_ids)),
        }
    except ValueError as exc:
        raise RelayValidationError(str(exc)) from exc


def _extract_file_ids(
    *,
    headers: Mapping[str, str],
    token_context: DriveChannelTokenContext,
) -> tuple[str, ...]:
    file_ids: set[str] = set(token_context.get("file_ids", []))
    raw_single = headers.get(_HEADER_FILE_ID)
    if raw_single:
        try:
            file_ids.add(validate_file_id(raw_single.strip()))
        except ValueError as exc:
            raise RelayValidationError(str(exc)) from exc
    raw_multiple = headers.get(_HEADER_FILE_IDS)
    if raw_multiple:
        for value in raw_multiple.split(","):
            trimmed = value.strip()
            if trimmed:
                try:
                    file_ids.add(validate_file_id(trimmed))
                except ValueError as exc:
                    raise RelayValidationError(str(exc)) from exc
    return tuple(sorted(file_ids))


def parse_drive_notification(
    *, headers: Mapping[str, str], token_secret: str
) -> DriveNotification:
    """Validate and parse Drive webhook headers into a typed object."""

    normalized_headers = _normalize_headers(headers)
    channel_id = _require_header(normalized_headers, _HEADER_CHANNEL_ID)
    channel_token = _require_header(normalized_headers, _HEADER_CHANNEL_TOKEN)
    resource_id = _require_header(normalized_headers, _HEADER_RESOURCE_ID)
    resource_state = _require_header(normalized_headers, _HEADER_RESOURCE_STATE).lower()
    message_number_raw = _require_header(normalized_headers, _HEADER_MESSAGE_NUMBER)
    try:
        message_number = int(message_number_raw)
    except ValueError as exc:
        raise RelayValidationError("x-goog-message-number must be an integer") from exc
    if message_number <= 0:
        raise RelayValidationError("x-goog-message-number must be positive")

    token_context = parse_drive_channel_token(
        token=channel_token,
        token_secret=token_secret,
    )
    file_ids = _extract_file_ids(headers=normalized_headers, token_context=token_context)
    return DriveNotification(
        alias=token_context["alias"],
        registry_path=token_context["registry_path"],
        file_ids=file_ids,
        channel_id=channel_id,
        resource_id=resource_id,
        resource_state=resource_state,
        message_number=message_number,
    )


def is_relevant_drive_resource_state(resource_state: str) -> bool:
    """Return whether a Drive resource_state should trigger dispatch."""

    normalized = resource_state.strip().lower()
    if normalized in _IGNORED_RESOURCE_STATES:
        return False
    return normalized in _RELEVANT_RESOURCE_STATES


def drive_replay_key(notification: DriveNotification) -> str:
    """Stable replay key from Drive header tuple."""

    return (
        f"{notification.channel_id}:"
        f"{notification.resource_id}:"
        f"{notification.message_number}"
    )


def validate_drive_registry_context(*, repo_root: Path, notification: DriveNotification) -> None:
    """Fail-closed validation for alias/registry_path context from channel token."""

    repo_root_resolved = repo_root.resolve()
    registry_file = (repo_root_resolved / notification.registry_path).resolve()
    registry_root = (repo_root_resolved / "raw" / "drive-sources").resolve()
    if not registry_file.is_relative_to(registry_root):
        raise RelayValidationError("registry_path escapes raw/drive-sources boundary")
    if not registry_file.exists():
        raise RelayValidationError(f"registry_path does not exist: {notification.registry_path}")

    try:
        parsed = json.loads(registry_file.read_text(encoding="utf-8"))
        registry = validate_drive_registry_file(parsed)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise RelayValidationError(
            f"registry_path is unreadable/invalid: {notification.registry_path}: {exc}"
        ) from exc

    if registry.get("alias") != notification.alias:
        raise RelayValidationError(
            "channel token alias does not match registry alias "
            f"({notification.alias!r} != {registry.get('alias')!r})"
        )


def build_drive_source_payload(notification: DriveNotification) -> DriveSourceUpdatedPayload:
    payload: DriveSourceUpdatedPayload = {
        "alias": notification.alias,
        "registry_path": notification.registry_path,
        "file_ids": list(notification.file_ids),
        "channel_id": notification.channel_id,
        "resource_id": notification.resource_id,
        "resource_state": notification.resource_state,
        "message_number": notification.message_number,
    }
    return validate_drive_source_payload(payload)


def validate_drive_source_payload(payload: Mapping[str, Any]) -> DriveSourceUpdatedPayload:
    """Validate the stable payload contract for CI-6 dispatch events."""

    expected_fields = {
        "alias",
        "registry_path",
        "file_ids",
        "channel_id",
        "resource_id",
        "resource_state",
        "message_number",
    }
    extra_fields = sorted(set(payload.keys()) - expected_fields)
    if extra_fields:
        raise RelayValidationError(
            f"payload contains unexpected field(s): {', '.join(extra_fields)}"
        )

    required_string_fields = (
        "alias",
        "registry_path",
        "channel_id",
        "resource_id",
        "resource_state",
    )
    for field in required_string_fields:
        value = payload.get(field)
        if not isinstance(value, str) or not value:
            raise RelayValidationError(f"payload field {field!r} must be a string")
        if field == "registry_path" and len(value) > _MAX_REGISTRY_PATH_LENGTH:
            raise RelayValidationError("payload field 'registry_path' exceeds max length")
        if field != "registry_path" and len(value) > _MAX_IDENTIFIER_LENGTH:
            raise RelayValidationError(f"payload field {field!r} exceeds max length")

    message_number = payload.get("message_number")
    if not isinstance(message_number, int) or message_number <= 0:
        raise RelayValidationError(
            "payload field 'message_number' must be a positive integer"
        )

    raw_file_ids = payload.get("file_ids")
    if not isinstance(raw_file_ids, list):
        raise RelayValidationError("payload field 'file_ids' must be a list")
    if len(raw_file_ids) > _MAX_FILE_IDS:
        raise RelayValidationError(
            f"payload field 'file_ids' exceeds max count {_MAX_FILE_IDS}"
        )
    validated_file_ids: list[str] = []
    for file_id in raw_file_ids:
        if not isinstance(file_id, str):
            raise RelayValidationError("payload field 'file_ids' must contain strings")
        if len(file_id) > _MAX_IDENTIFIER_LENGTH:
            raise RelayValidationError(
                "payload field 'file_ids' contains value exceeding max length"
            )
        try:
            validated_file_ids.append(validate_file_id(file_id))
        except ValueError as exc:
            raise RelayValidationError(str(exc)) from exc

    resource_state = payload["resource_state"].lower()
    if resource_state not in _RELEVANT_RESOURCE_STATES:
        raise RelayValidationError(
            "payload field 'resource_state' must be one of the relevant Drive states"
        )

    try:
        return {
            "alias": validate_alias(payload["alias"]),
            "registry_path": _validate_registry_path_literal(payload["registry_path"]),
            "file_ids": sorted(set(validated_file_ids)),
            "channel_id": payload["channel_id"],
            "resource_id": payload["resource_id"],
            "resource_state": resource_state,
            "message_number": message_number,
        }
    except ValueError as exc:
        raise RelayValidationError(str(exc)) from exc


def relay_drive_notification(
    *,
    repo_root: Path,
    headers: Mapping[str, str],
    token_secret: str,
    dispatch_client: RepositoryDispatchClient,
    replay_cache: DriveReplayStore,
) -> DriveRelayResult:
    """Validate a Drive notification, suppress replays, and emit dispatch."""

    try:
        notification = parse_drive_notification(headers=headers, token_secret=token_secret)
        validate_drive_registry_context(repo_root=repo_root, notification=notification)
    except RelayValidationError as exc:
        return DriveRelayResult(
            status="rejected",
            reason=str(exc),
            dispatched=False,
            payload=None,
        )

    if not is_relevant_drive_resource_state(notification.resource_state):
        return DriveRelayResult(
            status="ignored",
            reason="resource_state_ignored",
            dispatched=False,
            payload=None,
        )

    replay_key = drive_replay_key(notification)
    if replay_cache.reserve(replay_key):
        return DriveRelayResult(
            status="ignored",
            reason="replay_suppressed",
            dispatched=False,
            payload=None,
        )

    try:
        payload = build_drive_source_payload(notification)
    except RelayValidationError as exc:
        replay_cache.rollback(replay_key)
        return DriveRelayResult(
            status="rejected",
            reason=str(exc),
            dispatched=False,
            payload=None,
        )

    try:
        dispatch_client.dispatch(
            event_type=_DRIVE_SOURCE_UPDATED_EVENT,
            client_payload=payload,
        )
    except Exception as exc:  # pragma: no cover - defensive envelope
        replay_cache.rollback(replay_key)
        return DriveRelayResult(
            status="failed",
            reason=f"dispatch_failed: {exc}",
            dispatched=False,
            payload=payload,
        )

    replay_cache.commit(replay_key)
    return DriveRelayResult(
        status="dispatched",
        reason="ok",
        dispatched=True,
        payload=payload,
    )


__all__ = [
    "DriveChannelTokenContext",
    "DriveNotification",
    "DriveRelayResult",
    "DriveReplayCache",
    "InMemoryDriveReplayCache",
    "DriveReplayStore",
    "DriveSourceUpdatedPayload",
    "GitHubApiDispatchClient",
    "RelayValidationError",
    "RepositoryDispatchClient",
    "RepositoryDispatchError",
    "build_drive_channel_token",
    "build_drive_source_payload",
    "drive_replay_key",
    "is_relevant_drive_resource_state",
    "parse_drive_channel_token",
    "parse_drive_notification",
    "relay_drive_notification",
    "validate_drive_source_payload",
    "validate_drive_registry_context",
]
