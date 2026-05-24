"""Unit tests for scripts/drive_monitor/relay_http.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import scripts.drive_monitor.relay_http as relay_http
from scripts.drive_monitor._relay import DriveRelayResult
from scripts.drive_monitor.relay_http import DriveRelayWsgiApp


class _NoopDispatchClient:
    def dispatch(self, *, event_type: str, client_payload: dict[str, Any]) -> None:
        return None


def _invoke_wsgi_app(
    app: DriveRelayWsgiApp, environ: dict[str, Any]
) -> tuple[str, dict[str, str], bytes]:
    status_holder: dict[str, str] = {}
    header_holder: dict[str, str] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        status_holder["status"] = status
        header_holder.update(dict(headers))

    body = b"".join(app(environ, start_response))
    return status_holder["status"], header_holder, body


def test_healthz_returns_ok_json(tmp_path: Path) -> None:
    app = DriveRelayWsgiApp(
        repo_root=tmp_path,
        token_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
    )
    status, headers, body = _invoke_wsgi_app(
        app,
        {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/healthz",
        },
    )

    assert status.startswith("200 ")
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body.decode("utf-8")) == {"status": "ok"}


def test_non_post_returns_405(tmp_path: Path) -> None:
    app = DriveRelayWsgiApp(
        repo_root=tmp_path,
        token_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
    )
    status, _, body = _invoke_wsgi_app(
        app,
        {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/",
        },
    )

    assert status.startswith("405 ")
    assert json.loads(body.decode("utf-8")) == {"error": "method_not_allowed"}


@pytest.mark.parametrize(
    ("relay_status", "expected_http"),
    [
        ("dispatched", "202 "),
        ("ignored", "202 "),
        ("rejected", "400 "),
        ("failed", "502 "),
        ("unknown", "500 "),
    ],
)
def test_wsgi_status_mapping_for_relay_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relay_status: str, expected_http: str
) -> None:
    result = DriveRelayResult(
        status=relay_status,
        reason="reason",
        dispatched=False,
        payload=None,
    )
    monkeypatch.setattr(relay_http, "relay_drive_notification", lambda **_: result)
    app = DriveRelayWsgiApp(
        repo_root=tmp_path,
        token_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
    )
    status, _, body = _invoke_wsgi_app(
        app,
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/",
        },
    )

    assert status.startswith(expected_http)
    assert json.loads(body.decode("utf-8"))["status"] == relay_status


def test_from_env_requires_drive_channel_token_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISPATCH_TARGET_OWNER", "owner")
    monkeypatch.setenv("DISPATCH_TARGET_REPO", "repo")
    monkeypatch.setenv("DISPATCH_TOKEN", "token")
    monkeypatch.delenv("DRIVE_CHANNEL_TOKEN_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="DRIVE_CHANNEL_TOKEN_SECRET"):
        DriveRelayWsgiApp.from_env()


def test_from_env_requires_dispatch_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRIVE_CHANNEL_TOKEN_SECRET", "secret")
    monkeypatch.setenv("DISPATCH_TARGET_OWNER", "owner")
    monkeypatch.setenv("DISPATCH_TARGET_REPO", "repo")
    monkeypatch.delenv("DISPATCH_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="DISPATCH_TOKEN"):
        DriveRelayWsgiApp.from_env()


@pytest.mark.parametrize(
    ("relay_status", "internal_reason", "expected_reason"),
    [
        ("rejected", "registry_path is unreadable/invalid: raw/drive-sources/a.source-registry.json", "request_rejected"),
        ("failed", "dispatch_failed: boom", "relay_failed"),
    ],
)
def test_wsgi_sanitizes_internal_failure_reasons(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relay_status: str,
    internal_reason: str,
    expected_reason: str,
) -> None:
    result = DriveRelayResult(
        status=relay_status,
        reason=internal_reason,
        dispatched=False,
        payload=None,
    )
    monkeypatch.setattr(relay_http, "relay_drive_notification", lambda **_: result)
    app = DriveRelayWsgiApp(
        repo_root=tmp_path,
        token_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
    )
    status, _, body = _invoke_wsgi_app(
        app,
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/",
        },
    )

    assert status.startswith("400 " if relay_status == "rejected" else "502 ")
    parsed = json.loads(body.decode("utf-8"))
    assert parsed["status"] == relay_status
    assert parsed["reason"] == expected_reason


@pytest.mark.parametrize(
    ("relay_status", "reason"),
    [
        ("dispatched", "dispatch_ok"),
        ("ignored", "replay_suppressed"),
    ],
)
def test_wsgi_keeps_non_failure_reasons_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relay_status: str,
    reason: str,
) -> None:
    result = DriveRelayResult(
        status=relay_status,
        reason=reason,
        dispatched=False,
        payload=None,
    )
    monkeypatch.setattr(relay_http, "relay_drive_notification", lambda **_: result)
    app = DriveRelayWsgiApp(
        repo_root=tmp_path,
        token_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
    )
    status, _, body = _invoke_wsgi_app(
        app,
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/",
        },
    )

    assert status.startswith("202 ")
    parsed = json.loads(body.decode("utf-8"))
    assert parsed["status"] == relay_status
    assert parsed["reason"] == reason
