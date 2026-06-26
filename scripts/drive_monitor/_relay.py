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
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, NotRequired, Protocol, TypedDict

from scripts.replay_cache import InMemoryReplayReservationCache
from scripts.github_monitor.dispatch_client import (
    GitHubApiDispatchClient,
    RepositoryDispatchClient,
    RepositoryDispatchError,
)
from scripts.drive_monitor._types import validate_drive_registry_file
from scripts.drive_monitor._validators import validate_alias, validate_file_id

_DRIVE_SOURCE_UPDATED_EVENT = "drive-source-updated"
_DRIVE_SOURCE_KIND = "drive"
_DRIVE_CHANNEL_TOKEN_PREFIX = "kbdrv1"
_HEX_DIGITS = frozenset("0123456789abcdef")
_DELIVERY_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")

_HEADER_CHANNEL_ID = "x-goog-channel-id"
_HEADER_CHANNEL_TOKEN = "x-goog-channel-token"
_HEADER_RESOURCE_ID = "x-goog-resource-id"
_HEADER_RESOURCE_STATE = "x-goog-resource-state"
_HEADER_MESSAGE_NUMBER = "x-goog-message-number"
_HEADER_FILE_ID = "x-goog-file-id"
_HEADER_FILE_IDS = "x-goog-file-ids"
_HEADER_DELIVERY_ID = "x-goog-delivery-id"
_HEADER_CHANNEL_EXPIRATION = "x-goog-channel-expiration"

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
_RENEWAL_WINDOW = timedelta(hours=1)


class DriveSourceUpdatedPayload(TypedDict):
    """Stable payload contract for event_type=drive-source-updated."""

    source_kind: str
    alias: str
    registry_path: str
    file_id: str
    change_id: str
    channel_id: str
    resource_id: str
    delivery_id: str
    observed_at: str


class DriveChannelTokenContext(TypedDict):
    """Validated context decoded from ``X-Goog-Channel-Token``."""

    alias: str
    registry_path: str
    file_ids: list[str]
    channel_id: NotRequired[str]
    resource_id: NotRequired[str]


@dataclass(frozen=True)
class DriveNotification:
    """Validated Drive notification header subset."""

    alias: str
    registry_path: str
    file_id: str
    change_id: str
    channel_id: str
    resource_id: str
    delivery_id: str
    resource_state: str
    observed_at: str
    observed_at_dt: datetime
    channel_expiration: datetime | None


@dataclass(frozen=True)
class DriveRelayResult:
    """Result envelope returned by ``relay_drive_notification()``."""

    status: str
    reason: str
    dispatched: bool
    payload: DriveSourceUpdatedPayload | None


class RelayValidationError(ValueError):
    """Raised when Drive headers/token/context are invalid."""


class DriveReplayCache(InMemoryReplayReservationCache):
    """In-memory replay suppression keyed by channel/resource/change/file tuple."""

    def __init__(self, *, ttl_seconds: int = 3600, max_entries: int = 20_000) -> None:
        super().__init__(ttl_seconds=ttl_seconds, max_entries=max_entries)


# Explicit concrete alias used in operator docs/examples.
InMemoryDriveReplayCache = DriveReplayCache


class DriveReplayStore(Protocol):
    """Replay cache/store contract for notification dedupe."""

    def reserve(self, key: str, *, now: float | None = None) -> bool:
        """Atomically reserve a key; return True when replayed."""

    def commit(self, key: str, *, now: float | None = None) -> None:
        """Commit a reserved key after successful dispatch."""

    def rollback(self, key: str) -> None:
        """Release a reserved key after dispatch failure."""


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


def _validate_identifier(*, field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RelayValidationError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > _MAX_IDENTIFIER_LENGTH:
        raise RelayValidationError(f"{field_name} exceeds max length")
    return normalized


def _validate_change_id(value: str) -> str:
    normalized = _validate_identifier(field_name="change_id", value=value)
    try:
        parsed = int(normalized)
    except ValueError as exc:
        raise RelayValidationError("x-goog-message-number must be an integer") from exc
    if parsed <= 0:
        raise RelayValidationError("x-goog-message-number must be positive")
    return str(parsed)


def _validate_delivery_id(value: str) -> str:
    normalized = _validate_identifier(field_name="delivery_id", value=value)
    if not _DELIVERY_ID_RE.fullmatch(normalized):
        raise RelayValidationError("delivery_id contains unsafe characters")
    return normalized


def _decode_b64url(value: str) -> bytes:
    padding = "=" * ((4 - (len(value) % 4)) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _build_delivery_id(
    *,
    channel_id: str,
    resource_id: str,
    change_id: str,
    file_id: str,
) -> str:
    seed = f"{channel_id}:{resource_id}:{change_id}:{file_id}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"drv-{digest[:32]}"


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


def _parse_channel_expiration(raw_value: str | None) -> datetime | None:
    if raw_value is None:
        return None
    value = raw_value.strip()
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError) as exc:
        raise RelayValidationError("invalid x-goog-channel-expiration header") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_drive_channel_token(
    *,
    alias: str,
    registry_path: str,
    token_secret: str,
    file_ids: list[str] | None = None,
    channel_id: str | None = None,
    resource_id: str | None = None,
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
    if len(validated_file_ids) > _MAX_FILE_IDS:
        raise RelayValidationError(f"file_ids exceeds max count {_MAX_FILE_IDS}")

    context: DriveChannelTokenContext = {
        "alias": validated_alias,
        "registry_path": validated_registry_path,
        "file_ids": sorted(set(validated_file_ids)),
    }
    if channel_id is not None:
        context["channel_id"] = _validate_identifier(
            field_name="channel_id", value=channel_id
        )
    if resource_id is not None:
        context["resource_id"] = _validate_identifier(
            field_name="resource_id", value=resource_id
        )

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
    raw_file_ids = raw_context.get("file_ids")
    raw_channel_id = raw_context.get("channel_id")
    raw_resource_id = raw_context.get("resource_id")

    if raw_file_ids is None:
        raw_file_ids = []
    if not isinstance(alias, str) or not alias:
        raise RelayValidationError("Drive channel token alias is required")
    if not isinstance(registry_path, str) or not registry_path:
        raise RelayValidationError("Drive channel token registry_path is required")
    if not isinstance(raw_file_ids, list):
        raise RelayValidationError("Drive channel token file_ids must be a list")
    if len(raw_file_ids) > _MAX_FILE_IDS:
        raise RelayValidationError(
            f"Drive channel token file_ids exceeds max count {_MAX_FILE_IDS}"
        )

    validated_file_ids: list[str] = []
    for file_id in raw_file_ids:
        if not isinstance(file_id, str):
            raise RelayValidationError("Drive channel token file_ids must contain strings")
        try:
            validated_file_ids.append(validate_file_id(file_id))
        except ValueError as exc:
            raise RelayValidationError(str(exc)) from exc

    context: DriveChannelTokenContext = {
        "alias": validate_alias(alias),
        "registry_path": _validate_registry_path_literal(registry_path),
        "file_ids": sorted(set(validated_file_ids)),
    }
    if raw_channel_id is not None:
        if not isinstance(raw_channel_id, str):
            raise RelayValidationError("Drive channel token channel_id must be a string")
        context["channel_id"] = _validate_identifier(
            field_name="channel_id", value=raw_channel_id
        )
    if raw_resource_id is not None:
        if not isinstance(raw_resource_id, str):
            raise RelayValidationError("Drive channel token resource_id must be a string")
        context["resource_id"] = _validate_identifier(
            field_name="resource_id", value=raw_resource_id
        )
    return context


def _extract_file_id(
    *,
    headers: Mapping[str, str],
    token_context: DriveChannelTokenContext,
) -> str:
    token_file_ids = token_context.get("file_ids", [])
    token_file_id_allowlist = set(token_file_ids)

    file_id: str
    raw_single = headers.get(_HEADER_FILE_ID)
    if raw_single:
        try:
            file_id = validate_file_id(raw_single.strip())
        except ValueError as exc:
            raise RelayValidationError(str(exc)) from exc
    else:
        raw_multiple = headers.get(_HEADER_FILE_IDS)
        if raw_multiple:
            parsed_ids: set[str] = set()
            for value in raw_multiple.split(","):
                trimmed = value.strip()
                if not trimmed:
                    continue
                try:
                    parsed_ids.add(validate_file_id(trimmed))
                except ValueError as exc:
                    raise RelayValidationError(str(exc)) from exc
            if len(parsed_ids) != 1:
                raise RelayValidationError(
                    "x-goog-file-ids must contain exactly one unique file_id"
                )
            file_id = next(iter(parsed_ids))
        elif len(token_file_ids) == 1:
            file_id = token_file_ids[0]
        elif len(token_file_ids) > 1:
            raise RelayValidationError(
                "Drive channel token file_ids is ambiguous; include x-goog-file-id header"
            )
        else:
            raise RelayValidationError(
                "missing file_id context (x-goog-file-id or token file_ids)"
            )

    if token_file_id_allowlist and file_id not in token_file_id_allowlist:
        raise RelayValidationError(
            "x-goog-file-id is outside signed channel token file_ids allowlist"
        )
    return file_id


def parse_drive_notification(
    *, headers: Mapping[str, str], token_secret: str
) -> DriveNotification:
    """Validate and parse Drive webhook headers into a typed object."""

    normalized_headers = _normalize_headers(headers)
    channel_id = _validate_identifier(
        field_name="channel_id",
        value=_require_header(normalized_headers, _HEADER_CHANNEL_ID),
    )
    channel_token = _require_header(normalized_headers, _HEADER_CHANNEL_TOKEN)
    resource_id = _validate_identifier(
        field_name="resource_id",
        value=_require_header(normalized_headers, _HEADER_RESOURCE_ID),
    )
    resource_state = _require_header(normalized_headers, _HEADER_RESOURCE_STATE).lower()
    change_id = _validate_change_id(
        _require_header(normalized_headers, _HEADER_MESSAGE_NUMBER)
    )
    token_context = parse_drive_channel_token(
        token=channel_token,
        token_secret=token_secret,
    )

    expected_channel_id = token_context.get("channel_id")
    if expected_channel_id and expected_channel_id != channel_id:
        raise RelayValidationError(
            "x-goog-channel-id does not match signed channel token context"
        )
    expected_resource_id = token_context.get("resource_id")
    if expected_resource_id and expected_resource_id != resource_id:
        raise RelayValidationError(
            "x-goog-resource-id does not match signed channel token context"
        )

    file_id = _extract_file_id(headers=normalized_headers, token_context=token_context)
    observed_at_dt = _current_utc_datetime()
    observed_at = _format_utc_iso8601(observed_at_dt)
    channel_expiration = _parse_channel_expiration(
        normalized_headers.get(_HEADER_CHANNEL_EXPIRATION)
    )
    delivery_id_header = normalized_headers.get(_HEADER_DELIVERY_ID)
    delivery_id = (
        _validate_delivery_id(delivery_id_header.strip())
        if delivery_id_header and delivery_id_header.strip()
        else _build_delivery_id(
            channel_id=channel_id,
            resource_id=resource_id,
            change_id=change_id,
            file_id=file_id,
        )
    )

    return DriveNotification(
        alias=token_context["alias"],
        registry_path=token_context["registry_path"],
        file_id=file_id,
        change_id=change_id,
        channel_id=channel_id,
        resource_id=resource_id,
        delivery_id=delivery_id,
        resource_state=resource_state,
        observed_at=observed_at,
        observed_at_dt=observed_at_dt,
        channel_expiration=channel_expiration,
    )


def is_relevant_drive_resource_state(resource_state: str) -> bool:
    """Return whether a Drive resource_state should trigger dispatch."""

    normalized = resource_state.strip().lower()
    if normalized in _IGNORED_RESOURCE_STATES:
        return False
    return normalized in _RELEVANT_RESOURCE_STATES


def _channel_lifecycle_state(notification: DriveNotification) -> str:
    if notification.channel_expiration is None:
        return "expiration_unknown"
    if notification.channel_expiration <= notification.observed_at_dt:
        return "expired"
    if notification.channel_expiration - notification.observed_at_dt <= _RENEWAL_WINDOW:
        return "renewal_due"
    return "active"


def drive_replay_key(notification: DriveNotification) -> str:
    """Stable replay key from Drive header tuple."""

    return (
        f"{notification.channel_id}:"
        f"{notification.resource_id}:"
        f"{notification.change_id}:"
        f"{notification.file_id}"
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
        "source_kind": _DRIVE_SOURCE_KIND,
        "alias": notification.alias,
        "registry_path": notification.registry_path,
        "file_id": notification.file_id,
        "change_id": notification.change_id,
        "channel_id": notification.channel_id,
        "resource_id": notification.resource_id,
        "delivery_id": notification.delivery_id,
        "observed_at": notification.observed_at,
    }
    return validate_drive_source_payload(payload)


def validate_drive_source_payload(payload: Mapping[str, Any]) -> DriveSourceUpdatedPayload:
    """Validate the stable payload contract for CI-6 dispatch events."""

    expected_fields = {
        "source_kind",
        "alias",
        "registry_path",
        "file_id",
        "change_id",
        "channel_id",
        "resource_id",
        "delivery_id",
        "observed_at",
    }
    # ⚡ Bolt: Use dict view set operations to avoid intermediate set creation
    extra_fields = sorted(payload.keys() - expected_fields)
    if extra_fields:
        raise RelayValidationError(
            f"payload contains unexpected field(s): {', '.join(extra_fields)}"
        )

    source_kind = payload.get("source_kind")
    if source_kind != _DRIVE_SOURCE_KIND:
        raise RelayValidationError("payload field 'source_kind' must be 'drive'")

    required_string_fields = (
        "alias",
        "registry_path",
        "file_id",
        "change_id",
        "channel_id",
        "resource_id",
        "delivery_id",
        "observed_at",
    )
    normalized_values: dict[str, str] = {}
    for field in required_string_fields:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise RelayValidationError(f"payload field {field!r} must be a string")
        normalized_values[field] = value.strip()

    if len(normalized_values["registry_path"]) > _MAX_REGISTRY_PATH_LENGTH:
        raise RelayValidationError("payload field 'registry_path' exceeds max length")
    for field in ("alias", "file_id", "change_id", "channel_id", "resource_id", "delivery_id"):
        if len(normalized_values[field]) > _MAX_IDENTIFIER_LENGTH:
            raise RelayValidationError(f"payload field {field!r} exceeds max length")

    try:
        alias = validate_alias(normalized_values["alias"])
        registry_path = _validate_registry_path_literal(normalized_values["registry_path"])
        file_id = validate_file_id(normalized_values["file_id"])
        change_id = _validate_change_id(normalized_values["change_id"])
        channel_id = _validate_identifier(
            field_name="channel_id", value=normalized_values["channel_id"]
        )
        resource_id = _validate_identifier(
            field_name="resource_id", value=normalized_values["resource_id"]
        )
        delivery_id = _validate_delivery_id(normalized_values["delivery_id"])
        observed_at = _format_utc_iso8601(_parse_observed_at(normalized_values["observed_at"]))
    except ValueError as exc:
        raise RelayValidationError(str(exc)) from exc

    return {
        "source_kind": _DRIVE_SOURCE_KIND,
        "alias": alias,
        "registry_path": registry_path,
        "file_id": file_id,
        "change_id": change_id,
        "channel_id": channel_id,
        "resource_id": resource_id,
        "delivery_id": delivery_id,
        "observed_at": observed_at,
    }


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

    lifecycle_state = _channel_lifecycle_state(notification)
    if lifecycle_state == "expired":
        return DriveRelayResult(
            status="ignored",
            reason="channel_expired",
            dispatched=False,
            payload=None,
        )

    if not is_relevant_drive_resource_state(notification.resource_state):
        ignored_reason = "resource_state_ignored"
        if lifecycle_state == "renewal_due":
            ignored_reason = "channel_renewal_due"
        return DriveRelayResult(
            status="ignored",
            reason=ignored_reason,
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


def externalize_relay_reason(*, status: str, reason: str) -> str:
    """Return an external-safe reason string for HTTP/webhook responses."""

    if status == "rejected":
        return "request_rejected"
    if status == "failed":
        return "relay_failed"
    return reason


__all__ = [
    "externalize_relay_reason",
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
