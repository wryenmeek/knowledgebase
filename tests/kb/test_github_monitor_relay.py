"""Unit tests for scripts/github_monitor/_relay.py."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from scripts.github_monitor._relay import (
    GitHubDeliveryReplayCache,
    RelayValidationError,
    RepositoryDispatchError,
    extract_changed_paths,
    parse_github_push_event,
    relay_github_push_event,
    validate_github_signature,
    validate_upstream_source_payload,
)


def _sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _push_body(
    *,
    owner: str = "upstream-owner",
    repo: str = "upstream-repo",
    commits: list[dict[str, Any]] | None = None,
) -> bytes:
    payload = {
        "repository": {
            "name": repo,
            "owner": {"login": owner},
        },
        "commits": commits
        or [
            {
                "added": [],
                "modified": [],
                "removed": [],
            }
        ],
    }
    return json.dumps(payload).encode("utf-8")


def _headers(
    body: bytes,
    *,
    secret: str,
    event_name: str = "push",
    delivery_id: str = "delivery-123",
) -> dict[str, str]:
    return {
        "X-GitHub-Event": event_name,
        "X-GitHub-Delivery": delivery_id,
        "X-Hub-Signature-256": _sign(secret, body),
    }


def _write_registry(
    repo_root: Path,
    *,
    owner: str = "upstream-owner",
    repo: str = "upstream-repo",
    entries: list[dict[str, Any]] | None = None,
    filename: str = "upstream.source-registry.json",
) -> Path:
    registry_dir = repo_root / "raw" / "github-sources"
    registry_dir.mkdir(parents=True, exist_ok=True)
    path = registry_dir / filename
    path.write_text(
        json.dumps(
            {
                "version": "1",
                "owner": owner,
                "repo": repo,
                "entries": entries or [],
            }
        ),
        encoding="utf-8",
    )
    return path


class _RecordingDispatchClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    def dispatch(self, *, event_type: str, client_payload: Mapping[str, Any]) -> None:
        self.calls.append((event_type, client_payload))


class _FailingDispatchClient:
    def dispatch(self, *, event_type: str, client_payload: Mapping[str, Any]) -> None:
        raise RepositoryDispatchError("boom")


def test_validate_github_signature_accepts_valid_signature() -> None:
    secret = "top-secret"
    body = b'{"ok": true}'
    assert validate_github_signature(
        webhook_secret=secret,
        body=body,
        signature_header=_sign(secret, body),
    )


def test_validate_github_signature_rejects_invalid_signature() -> None:
    assert not validate_github_signature(
        webhook_secret="top-secret",
        body=b'{"ok": true}',
        signature_header="sha256=" + ("0" * 63),
    )


def test_extract_changed_paths_merges_added_modified_removed() -> None:
    changed = extract_changed_paths(
        {
            "commits": [
                {
                    "added": ["a.md"],
                    "modified": ["b.md"],
                    "removed": ["c.md"],
                },
                {
                    "added": ["b.md"],
                    "modified": [],
                    "removed": [],
                },
            ]
        }
    )
    assert changed == ("a.md", "b.md", "c.md")


def test_relay_filters_paths_to_monitored_entries(tmp_path: Path) -> None:
    _write_registry(
        tmp_path,
        entries=[
            {"path": "docs/guide.md", "tracking_status": "active"},
            {"path": "docs/paused.md", "tracking_status": "paused"},
        ],
    )
    body = _push_body(
        commits=[
            {
                "added": ["docs/paused.md"],
                "modified": ["docs/guide.md", "untracked.md"],
                "removed": [],
            }
        ]
    )
    client = _RecordingDispatchClient()
    result = relay_github_push_event(
        repo_root=tmp_path,
        headers=_headers(body, secret="secret-1"),
        body=body,
        webhook_secret="secret-1",
        dispatch_client=client,
        replay_cache=GitHubDeliveryReplayCache(),
    )

    assert result.status == "dispatched"
    assert result.dispatched_count == 1
    assert len(client.calls) == 1
    event_type, payload = client.calls[0]
    assert event_type == "upstream-source-updated"
    assert payload["registry_path"] == "raw/github-sources/upstream.source-registry.json"
    assert payload["owner"] == "upstream-owner"
    assert payload["repo"] == "upstream-repo"
    assert payload["changed_paths"] == ["docs/guide.md"]
    assert payload["delivery_id"] == "delivery-123"
    assert payload["event_name"] == "push"


def test_relay_ignores_when_no_registry_path_intersection(tmp_path: Path) -> None:
    _write_registry(
        tmp_path,
        entries=[{"path": "docs/guide.md", "tracking_status": "active"}],
    )
    body = _push_body(
        commits=[
            {
                "added": [],
                "modified": ["docs/other.md"],
                "removed": [],
            }
        ]
    )
    result = relay_github_push_event(
        repo_root=tmp_path,
        headers=_headers(body, secret="secret-1"),
        body=body,
        webhook_secret="secret-1",
        dispatch_client=_RecordingDispatchClient(),
        replay_cache=GitHubDeliveryReplayCache(),
    )

    assert result.status == "ignored"
    assert result.reason == "no_registry_match_or_path_intersection"
    assert result.dispatched_count == 0


def test_relay_fails_closed_on_invalid_signature(tmp_path: Path) -> None:
    _write_registry(
        tmp_path,
        entries=[{"path": "docs/guide.md", "tracking_status": "active"}],
    )
    body = _push_body(
        commits=[
            {
                "added": [],
                "modified": ["docs/guide.md"],
                "removed": [],
            }
        ]
    )
    headers = _headers(body, secret="secret-1")
    headers["X-Hub-Signature-256"] = "sha256=bad"
    result = relay_github_push_event(
        repo_root=tmp_path,
        headers=headers,
        body=body,
        webhook_secret="secret-1",
        dispatch_client=_RecordingDispatchClient(),
        replay_cache=GitHubDeliveryReplayCache(),
    )

    assert result.status == "rejected"
    assert result.dispatched_count == 0


def test_relay_dispatch_failure_returns_failed_result(tmp_path: Path) -> None:
    _write_registry(
        tmp_path,
        entries=[{"path": "docs/guide.md", "tracking_status": "active"}],
    )
    body = _push_body(
        commits=[
            {
                "added": [],
                "modified": ["docs/guide.md"],
                "removed": [],
            }
        ]
    )
    result = relay_github_push_event(
        repo_root=tmp_path,
        headers=_headers(body, secret="secret-1"),
        body=body,
        webhook_secret="secret-1",
        dispatch_client=_FailingDispatchClient(),
        replay_cache=GitHubDeliveryReplayCache(),
    )

    assert result.status == "failed"
    assert result.dispatched_count == 0


def test_relay_dispatch_failure_does_not_consume_replay_key(tmp_path: Path) -> None:
    _write_registry(
        tmp_path,
        entries=[{"path": "docs/guide.md", "tracking_status": "active"}],
    )
    body = _push_body(
        commits=[{"added": [], "modified": ["docs/guide.md"], "removed": []}]
    )
    replay_cache = GitHubDeliveryReplayCache()
    failed = relay_github_push_event(
        repo_root=tmp_path,
        headers=_headers(body, secret="secret-1", delivery_id="delivery-retry"),
        body=body,
        webhook_secret="secret-1",
        dispatch_client=_FailingDispatchClient(),
        replay_cache=replay_cache,
    )
    successful_client = _RecordingDispatchClient()
    retried = relay_github_push_event(
        repo_root=tmp_path,
        headers=_headers(body, secret="secret-1", delivery_id="delivery-retry"),
        body=body,
        webhook_secret="secret-1",
        dispatch_client=successful_client,
        replay_cache=replay_cache,
    )

    assert failed.status == "failed"
    assert retried.status == "dispatched"
    assert len(successful_client.calls) == 1


def test_validate_upstream_source_payload_requires_contract_fields() -> None:
    with pytest.raises(RelayValidationError):
        validate_upstream_source_payload(
            {
                "registry_path": "raw/github-sources/a.source-registry.json",
                "owner": "owner",
                "repo": "repo",
                "changed_paths": ["docs/guide.md"],
                "delivery_id": "delivery-1",
            }
        )


def test_validate_github_signature_rejects_missing_and_malformed_headers() -> None:
    body = b'{"ok": true}'
    assert not validate_github_signature(
        webhook_secret="secret",
        body=body,
        signature_header=None,
    )
    assert not validate_github_signature(
        webhook_secret="secret",
        body=body,
        signature_header="md5=abc",
    )
    assert not validate_github_signature(
        webhook_secret="secret",
        body=body,
        signature_header="sha256=zzzz",
    )


def test_parse_push_event_requires_event_and_delivery_headers() -> None:
    body = _push_body()
    with pytest.raises(RelayValidationError):
        parse_github_push_event(
            headers={"X-GitHub-Delivery": "delivery-1"},
            body=body,
            webhook_secret="secret-1",
        )
    with pytest.raises(RelayValidationError):
        parse_github_push_event(
            headers={"X-GitHub-Event": "push"},
            body=body,
            webhook_secret="secret-1",
        )


def test_relay_ignores_non_push_events(tmp_path: Path) -> None:
    body = _push_body()
    result = relay_github_push_event(
        repo_root=tmp_path,
        headers=_headers(body, secret="secret-1", event_name="ping"),
        body=body,
        webhook_secret="secret-1",
        dispatch_client=_RecordingDispatchClient(),
        replay_cache=GitHubDeliveryReplayCache(),
    )
    assert result.status == "ignored"
    assert result.reason == "event_not_push"


def test_relay_treats_uninitialized_registry_entries_as_monitored(tmp_path: Path) -> None:
    _write_registry(
        tmp_path,
        entries=[{"path": "docs/new.md", "tracking_status": "uninitialized"}],
    )
    body = _push_body(
        commits=[{"added": ["docs/new.md"], "modified": [], "removed": []}]
    )
    result = relay_github_push_event(
        repo_root=tmp_path,
        headers=_headers(body, secret="secret-1"),
        body=body,
        webhook_secret="secret-1",
        dispatch_client=_RecordingDispatchClient(),
        replay_cache=GitHubDeliveryReplayCache(),
    )
    assert result.status == "dispatched"
    assert result.payloads[0]["changed_paths"] == ["docs/new.md"]


def test_relay_rejects_when_registry_file_is_invalid(tmp_path: Path) -> None:
    registry_dir = tmp_path / "raw" / "github-sources"
    registry_dir.mkdir(parents=True, exist_ok=True)
    (registry_dir / "broken.source-registry.json").write_text("not json", encoding="utf-8")
    body = _push_body(
        commits=[{"added": ["docs/new.md"], "modified": [], "removed": []}]
    )
    result = relay_github_push_event(
        repo_root=tmp_path,
        headers=_headers(body, secret="secret-1"),
        body=body,
        webhook_secret="secret-1",
        dispatch_client=_RecordingDispatchClient(),
        replay_cache=GitHubDeliveryReplayCache(),
    )
    assert result.status == "rejected"
    assert "registry file is unreadable/invalid" in result.reason


def test_relay_suppresses_replayed_delivery_ids(tmp_path: Path) -> None:
    _write_registry(
        tmp_path,
        entries=[{"path": "docs/guide.md", "tracking_status": "active"}],
    )
    body = _push_body(
        commits=[{"added": [], "modified": ["docs/guide.md"], "removed": []}]
    )
    replay_cache = GitHubDeliveryReplayCache()
    client = _RecordingDispatchClient()
    first = relay_github_push_event(
        repo_root=tmp_path,
        headers=_headers(body, secret="secret-1", delivery_id="delivery-xyz"),
        body=body,
        webhook_secret="secret-1",
        dispatch_client=client,
        replay_cache=replay_cache,
    )
    second = relay_github_push_event(
        repo_root=tmp_path,
        headers=_headers(body, secret="secret-1", delivery_id="delivery-xyz"),
        body=body,
        webhook_secret="secret-1",
        dispatch_client=client,
        replay_cache=replay_cache,
    )
    assert first.status == "dispatched"
    assert second.status == "ignored"
    assert second.reason == "replay_suppressed"
    assert len(client.calls) == 1


def test_relay_reports_partial_dispatch_count_on_multi_registry_failure(tmp_path: Path) -> None:
    _write_registry(
        tmp_path,
        entries=[{"path": "docs/guide.md", "tracking_status": "active"}],
        filename="first.source-registry.json",
    )
    _write_registry(
        tmp_path,
        entries=[{"path": "docs/guide.md", "tracking_status": "active"}],
        filename="second.source-registry.json",
    )
    body = _push_body(
        commits=[{"added": [], "modified": ["docs/guide.md"], "removed": []}]
    )

    class _FailsOnSecondDispatch:
        def __init__(self) -> None:
            self.calls = 0

        def dispatch(
            self, *, event_type: str, client_payload: Mapping[str, Any]
        ) -> None:
            self.calls += 1
            if self.calls == 2:
                raise RepositoryDispatchError("second dispatch failed")

    client = _FailsOnSecondDispatch()
    result = relay_github_push_event(
        repo_root=tmp_path,
        headers=_headers(body, secret="secret-1"),
        body=body,
        webhook_secret="secret-1",
        dispatch_client=client,
        replay_cache=GitHubDeliveryReplayCache(),
    )
    assert result.status == "failed"
    assert result.dispatched_count == 1


def test_validate_upstream_source_payload_rejects_invalid_registry_path() -> None:
    with pytest.raises(RelayValidationError):
        validate_upstream_source_payload(
            {
                "registry_path": "../raw/github-sources/a.source-registry.json",
                "owner": "owner",
                "repo": "repo",
                "changed_paths": ["docs/guide.md"],
                "delivery_id": "delivery-1",
                "event_name": "push",
            }
        )


def test_validate_upstream_source_payload_rejects_unexpected_fields() -> None:
    with pytest.raises(RelayValidationError):
        validate_upstream_source_payload(
            {
                "registry_path": "raw/github-sources/a.source-registry.json",
                "owner": "owner",
                "repo": "repo",
                "changed_paths": ["docs/guide.md"],
                "delivery_id": "delivery-1",
                "event_name": "push",
                "unexpected": "field",
            }
        )


def test_validate_upstream_source_payload_rejects_too_many_changed_paths() -> None:
    with pytest.raises(RelayValidationError):
        validate_upstream_source_payload(
            {
                "registry_path": "raw/github-sources/a.source-registry.json",
                "owner": "owner",
                "repo": "repo",
                "changed_paths": [f"docs/{i}.md" for i in range(201)],
                "delivery_id": "delivery-1",
                "event_name": "push",
            }
        )


def test_relay_rejects_invalid_changed_paths_in_push_body(tmp_path: Path) -> None:
    body = _push_body(
        commits=[{"added": ["../escape.md"], "modified": [], "removed": []}]
    )
    result = relay_github_push_event(
        repo_root=tmp_path,
        headers=_headers(body, secret="secret-1"),
        body=body,
        webhook_secret="secret-1",
        dispatch_client=_RecordingDispatchClient(),
        replay_cache=GitHubDeliveryReplayCache(),
    )
    assert result.status == "rejected"
    assert "invalid changed path" in result.reason
