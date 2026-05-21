"""Unit tests for scripts/drive_monitor/_relay.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from scripts.drive_monitor._relay import (
    DriveReplayCache,
    RelayValidationError,
    RepositoryDispatchError,
    build_drive_channel_token,
    parse_drive_channel_token,
    relay_drive_notification,
    validate_drive_source_payload,
)


def _write_registry(repo_root: Path, *, alias: str = "my-alias") -> str:
    registry_dir = repo_root / "raw" / "drive-sources"
    registry_dir.mkdir(parents=True, exist_ok=True)
    registry_path = registry_dir / f"{alias}.source-registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": "1",
                "alias": alias,
                "credential_secret_name": "GDRIVE_SA_KEY",
                "changes_page_token": None,
                "last_full_scan_at": None,
                "folder_entries": [
                    {
                        "folder_id": "FOLDER_1",
                        "folder_name": "Folder One",
                        "wiki_namespace": "test/",
                        "tracking_status": "active",
                    }
                ],
                "file_entries": [],
            }
        ),
        encoding="utf-8",
    )
    return f"raw/drive-sources/{alias}.source-registry.json"


def _headers(
    *,
    token: str,
    resource_state: str = "update",
    message_number: str = "1",
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    base = {
        "X-Goog-Channel-ID": "channel-123",
        "X-Goog-Channel-Token": token,
        "X-Goog-Resource-ID": "resource-456",
        "X-Goog-Resource-State": resource_state,
        "X-Goog-Message-Number": message_number,
    }
    if extra:
        base.update(extra)
    return base


class _RecordingDispatchClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    def dispatch(self, *, event_type: str, client_payload: Mapping[str, Any]) -> None:
        self.calls.append((event_type, client_payload))


class _FailingDispatchClient:
    def dispatch(self, *, event_type: str, client_payload: Mapping[str, Any]) -> None:
        raise RepositoryDispatchError("boom")


def test_build_and_parse_drive_channel_token_round_trip() -> None:
    token = build_drive_channel_token(
        alias="my-alias",
        registry_path="raw/drive-sources/my-alias.source-registry.json",
        token_secret="relay-secret",
        file_ids=["FILE_1", "FILE_2"],
    )
    context = parse_drive_channel_token(token=token, token_secret="relay-secret")
    assert context["alias"] == "my-alias"
    assert context["registry_path"] == "raw/drive-sources/my-alias.source-registry.json"
    assert context["file_ids"] == ["FILE_1", "FILE_2"]


def test_parse_drive_channel_token_rejects_invalid_signature() -> None:
    token = build_drive_channel_token(
        alias="my-alias",
        registry_path="raw/drive-sources/my-alias.source-registry.json",
        token_secret="relay-secret",
    )
    prefix, payload, signature = token.split(".")
    tampered = f"{prefix}.{payload}.{signature[:-1]}0"
    with pytest.raises(RelayValidationError):
        parse_drive_channel_token(token=tampered, token_secret="relay-secret")


def test_relay_ignores_sync_heartbeat_notifications(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path, alias="my-alias")
    token = build_drive_channel_token(
        alias="my-alias",
        registry_path=registry_path,
        token_secret="relay-secret",
    )
    client = _RecordingDispatchClient()
    result = relay_drive_notification(
        repo_root=tmp_path,
        headers=_headers(token=token, resource_state="sync"),
        token_secret="relay-secret",
        dispatch_client=client,
        replay_cache=DriveReplayCache(),
    )
    assert result.status == "ignored"
    assert result.reason == "resource_state_ignored"
    assert not result.dispatched
    assert client.calls == []


def test_relay_dispatches_relevant_drive_notification(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path, alias="my-alias")
    token = build_drive_channel_token(
        alias="my-alias",
        registry_path=registry_path,
        token_secret="relay-secret",
        file_ids=["FILE_TOKEN"],
    )
    client = _RecordingDispatchClient()
    result = relay_drive_notification(
        repo_root=tmp_path,
        headers=_headers(
            token=token,
            resource_state="update",
            extra={"X-Goog-File-ID": "FILE_HDR"},
        ),
        token_secret="relay-secret",
        dispatch_client=client,
        replay_cache=DriveReplayCache(),
    )
    assert result.status == "dispatched"
    assert result.dispatched
    assert len(client.calls) == 1
    event_type, payload = client.calls[0]
    assert event_type == "drive-source-updated"
    assert payload["alias"] == "my-alias"
    assert payload["registry_path"] == registry_path
    assert payload["file_ids"] == ["FILE_HDR", "FILE_TOKEN"]
    assert payload["channel_id"] == "channel-123"
    assert payload["resource_id"] == "resource-456"
    assert payload["resource_state"] == "update"
    assert payload["message_number"] == 1


def test_relay_replay_suppression_uses_header_key(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path, alias="my-alias")
    token = build_drive_channel_token(
        alias="my-alias",
        registry_path=registry_path,
        token_secret="relay-secret",
    )
    cache = DriveReplayCache()
    client = _RecordingDispatchClient()
    first = relay_drive_notification(
        repo_root=tmp_path,
        headers=_headers(token=token, resource_state="update", message_number="5"),
        token_secret="relay-secret",
        dispatch_client=client,
        replay_cache=cache,
    )
    second = relay_drive_notification(
        repo_root=tmp_path,
        headers=_headers(token=token, resource_state="update", message_number="5"),
        token_secret="relay-secret",
        dispatch_client=client,
        replay_cache=cache,
    )
    assert first.status == "dispatched"
    assert second.status == "ignored"
    assert second.reason == "replay_suppressed"
    assert len(client.calls) == 1


def test_relay_rejects_alias_registry_mismatch(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path, alias="expected-alias")
    token = build_drive_channel_token(
        alias="different-alias",
        registry_path=registry_path,
        token_secret="relay-secret",
    )
    result = relay_drive_notification(
        repo_root=tmp_path,
        headers=_headers(token=token, resource_state="update"),
        token_secret="relay-secret",
        dispatch_client=_RecordingDispatchClient(),
        replay_cache=DriveReplayCache(),
    )
    assert result.status == "rejected"
    assert "alias" in result.reason


def test_relay_dispatch_failure_returns_failed_result(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path, alias="my-alias")
    token = build_drive_channel_token(
        alias="my-alias",
        registry_path=registry_path,
        token_secret="relay-secret",
    )
    result = relay_drive_notification(
        repo_root=tmp_path,
        headers=_headers(token=token, resource_state="update"),
        token_secret="relay-secret",
        dispatch_client=_FailingDispatchClient(),
        replay_cache=DriveReplayCache(),
    )
    assert result.status == "failed"
    assert not result.dispatched


def test_relay_dispatch_failure_does_not_consume_replay_key(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path, alias="my-alias")
    token = build_drive_channel_token(
        alias="my-alias",
        registry_path=registry_path,
        token_secret="relay-secret",
    )
    replay_cache = DriveReplayCache()
    failed = relay_drive_notification(
        repo_root=tmp_path,
        headers=_headers(token=token, resource_state="update", message_number="55"),
        token_secret="relay-secret",
        dispatch_client=_FailingDispatchClient(),
        replay_cache=replay_cache,
    )
    successful_client = _RecordingDispatchClient()
    retried = relay_drive_notification(
        repo_root=tmp_path,
        headers=_headers(token=token, resource_state="update", message_number="55"),
        token_secret="relay-secret",
        dispatch_client=successful_client,
        replay_cache=replay_cache,
    )

    assert failed.status == "failed"
    assert retried.status == "dispatched"
    assert len(successful_client.calls) == 1


def test_relay_payload_validation_rejection_does_not_consume_replay_key(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path, alias="my-alias")
    token = build_drive_channel_token(
        alias="my-alias",
        registry_path=registry_path,
        token_secret="relay-secret",
    )
    replay_cache = DriveReplayCache()
    oversized_header = ",".join(f"FILE_{i}" for i in range(201))
    rejected = relay_drive_notification(
        repo_root=tmp_path,
        headers=_headers(
            token=token,
            resource_state="update",
            message_number="56",
            extra={"X-Goog-File-IDs": oversized_header},
        ),
        token_secret="relay-secret",
        dispatch_client=_RecordingDispatchClient(),
        replay_cache=replay_cache,
    )
    successful_client = _RecordingDispatchClient()
    retried = relay_drive_notification(
        repo_root=tmp_path,
        headers=_headers(token=token, resource_state="update", message_number="56"),
        token_secret="relay-secret",
        dispatch_client=successful_client,
        replay_cache=replay_cache,
    )

    assert rejected.status == "rejected"
    assert retried.status == "dispatched"
    assert len(successful_client.calls) == 1


def test_validate_drive_source_payload_requires_message_number() -> None:
    with pytest.raises(RelayValidationError):
        validate_drive_source_payload(
            {
                "alias": "my-alias",
                "registry_path": "raw/drive-sources/my-alias.source-registry.json",
                "file_ids": [],
                "channel_id": "channel-123",
                "resource_id": "resource-456",
                "resource_state": "update",
            }
        )


def test_parse_drive_channel_token_rejects_invalid_format() -> None:
    with pytest.raises(RelayValidationError):
        parse_drive_channel_token(token="not-a-valid-token", token_secret="relay-secret")


def test_relay_rejects_missing_required_headers(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path, alias="my-alias")
    token = build_drive_channel_token(
        alias="my-alias",
        registry_path=registry_path,
        token_secret="relay-secret",
    )
    headers = _headers(token=token, resource_state="update")
    del headers["X-Goog-Channel-ID"]
    result = relay_drive_notification(
        repo_root=tmp_path,
        headers=headers,
        token_secret="relay-secret",
        dispatch_client=_RecordingDispatchClient(),
        replay_cache=DriveReplayCache(),
    )
    assert result.status == "rejected"
    assert "x-goog-channel-id" in result.reason


def test_relay_rejects_non_integer_message_number(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path, alias="my-alias")
    token = build_drive_channel_token(
        alias="my-alias",
        registry_path=registry_path,
        token_secret="relay-secret",
    )
    result = relay_drive_notification(
        repo_root=tmp_path,
        headers=_headers(token=token, message_number="abc"),
        token_secret="relay-secret",
        dispatch_client=_RecordingDispatchClient(),
        replay_cache=DriveReplayCache(),
    )
    assert result.status == "rejected"
    assert "message-number" in result.reason


def test_relay_rejects_non_positive_message_number(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path, alias="my-alias")
    token = build_drive_channel_token(
        alias="my-alias",
        registry_path=registry_path,
        token_secret="relay-secret",
    )
    result = relay_drive_notification(
        repo_root=tmp_path,
        headers=_headers(token=token, message_number="0"),
        token_secret="relay-secret",
        dispatch_client=_RecordingDispatchClient(),
        replay_cache=DriveReplayCache(),
    )
    assert result.status == "rejected"
    assert "positive" in result.reason


def test_replay_cache_allows_next_message_number(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path, alias="my-alias")
    token = build_drive_channel_token(
        alias="my-alias",
        registry_path=registry_path,
        token_secret="relay-secret",
    )
    cache = DriveReplayCache()
    client = _RecordingDispatchClient()
    first = relay_drive_notification(
        repo_root=tmp_path,
        headers=_headers(token=token, message_number="10"),
        token_secret="relay-secret",
        dispatch_client=client,
        replay_cache=cache,
    )
    second = relay_drive_notification(
        repo_root=tmp_path,
        headers=_headers(token=token, message_number="11"),
        token_secret="relay-secret",
        dispatch_client=client,
        replay_cache=cache,
    )
    assert first.status == "dispatched"
    assert second.status == "dispatched"
    assert len(client.calls) == 2


def test_replay_cache_expires_old_entries() -> None:
    cache = DriveReplayCache(ttl_seconds=1)
    key = "channel-123:resource-456:22"
    assert cache.check_and_record(key, now=0.0) is False
    assert cache.check_and_record(key, now=0.5) is True
    assert cache.check_and_record(key, now=1.1) is False


def test_validate_drive_source_payload_rejects_invalid_registry_path() -> None:
    with pytest.raises(RelayValidationError):
        validate_drive_source_payload(
            {
                "alias": "my-alias",
                "registry_path": "../raw/drive-sources/my-alias.source-registry.json",
                "file_ids": [],
                "channel_id": "channel-123",
                "resource_id": "resource-456",
                "resource_state": "update",
                "message_number": 1,
            }
        )


def test_validate_drive_source_payload_rejects_non_string_file_ids() -> None:
    with pytest.raises(RelayValidationError):
        validate_drive_source_payload(
            {
                "alias": "my-alias",
                "registry_path": "raw/drive-sources/my-alias.source-registry.json",
                "file_ids": [123],
                "channel_id": "channel-123",
                "resource_id": "resource-456",
                "resource_state": "update",
                "message_number": 1,
            }
        )


def test_validate_drive_source_payload_rejects_unexpected_fields() -> None:
    with pytest.raises(RelayValidationError):
        validate_drive_source_payload(
            {
                "alias": "my-alias",
                "registry_path": "raw/drive-sources/my-alias.source-registry.json",
                "file_ids": [],
                "channel_id": "channel-123",
                "resource_id": "resource-456",
                "resource_state": "update",
                "message_number": 1,
                "unexpected": "field",
            }
        )


def test_validate_drive_source_payload_rejects_too_many_file_ids() -> None:
    with pytest.raises(RelayValidationError):
        validate_drive_source_payload(
            {
                "alias": "my-alias",
                "registry_path": "raw/drive-sources/my-alias.source-registry.json",
                "file_ids": [f"FILE_{i}" for i in range(201)],
                "channel_id": "channel-123",
                "resource_id": "resource-456",
                "resource_state": "update",
                "message_number": 1,
            }
        )
