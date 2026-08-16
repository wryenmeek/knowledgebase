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
) -> tuple[str, list[tuple[str, str]], bytes]:
    status_holder: dict[str, str] = {}
    header_holder: list[tuple[str, str]] = []

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        status_holder["status"] = status
        header_holder.extend(headers)

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
    headers = dict(headers)
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


def test_from_env_builds_app_with_valid_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("DRIVE_CHANNEL_TOKEN_SECRET", "secret")
    monkeypatch.setenv("DISPATCH_TARGET_OWNER", "owner")
    monkeypatch.setenv("DISPATCH_TARGET_REPO", "repo")
    monkeypatch.setenv("DISPATCH_TOKEN", "token")

    app = DriveRelayWsgiApp.from_env()
    captured: dict[str, Any] = {}

    def _fake_relay_drive_notification(**kwargs: Any) -> DriveRelayResult:
        captured.update(kwargs)
        return DriveRelayResult(
            status="ignored",
            reason="replay_suppressed",
            dispatched=False,
            payload=None,
        )

    monkeypatch.setattr(relay_http, "relay_drive_notification", _fake_relay_drive_notification)
    status, _, body = _invoke_wsgi_app(
        app,
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/",
        },
    )

    assert status.startswith("202 ")
    assert json.loads(body.decode("utf-8"))["status"] == "ignored"
    assert captured["repo_root"] == tmp_path.resolve()
    assert captured["token_secret"] == "secret"


def test_module_app_bootstraps_once_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    created: dict[str, int] = {"count": 0}
    fake_app = DriveRelayWsgiApp(
        repo_root=tmp_path,
        token_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
    )

    def _fake_from_env(cls: type[DriveRelayWsgiApp]) -> DriveRelayWsgiApp:
        created["count"] += 1
        return fake_app

    monkeypatch.setattr(relay_http, "_APP", None)
    monkeypatch.setattr(
        relay_http.DriveRelayWsgiApp, "from_env", classmethod(_fake_from_env)
    )

    status1, _, body1 = _invoke_wsgi_app(
        relay_http.app,  # type: ignore[arg-type]
        {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/healthz",
        },
    )
    status2, _, body2 = _invoke_wsgi_app(
        relay_http.app,  # type: ignore[arg-type]
        {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/healthz",
        },
    )

    assert created["count"] == 1
    assert status1.startswith("200 ")
    assert status2.startswith("200 ")
    assert json.loads(body1.decode("utf-8")) == {"status": "ok"}
    assert json.loads(body2.decode("utf-8")) == {"status": "ok"}


def test_main_wires_make_server_with_from_env_app(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_app = DriveRelayWsgiApp(
        repo_root=tmp_path,
        token_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
    )
    server_state: dict[str, Any] = {}

    class _FakeServer:
        def __init__(self, host: str, port: int, application: Any) -> None:
            server_state["host"] = host
            server_state["port"] = port
            server_state["application"] = application

        def __enter__(self) -> "_FakeServer":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

        def serve_forever(self) -> None:
            server_state["served"] = True

    monkeypatch.setattr(
        relay_http.DriveRelayWsgiApp, "from_env", classmethod(lambda cls: fake_app)
    )
    monkeypatch.setattr(
        relay_http, "make_server", lambda host, port, app: _FakeServer(host, port, app)
    )
    monkeypatch.setattr(
        relay_http.sys, "argv", ["relay_http.py", "--host", "127.0.0.1", "--port", "9099"]
    )

    relay_http.main()

    assert server_state["host"] == "127.0.0.1"
    assert server_state["port"] == 9099
    assert server_state["application"] is fake_app
    assert server_state["served"] is True


@pytest.mark.parametrize(
    ("host_env", "expected_host"),
    [
        (None, "127.0.0.1"),
        ("", "127.0.0.1"),
        ("   ", "127.0.0.1"),
        ("10.0.0.5", "10.0.0.5"),
    ],
)
def test_main_host_default_from_env_when_flag_omitted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    host_env: str | None,
    expected_host: str,
) -> None:
    """Bandit B104: --host must default to localhost, not 0.0.0.0, and only
    bind to a non-loopback address when HOST is explicitly set to one."""
    fake_app = DriveRelayWsgiApp(
        repo_root=tmp_path,
        token_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
    )
    server_state: dict[str, Any] = {}

    class _FakeServer:
        def __init__(self, host: str, port: int, application: Any) -> None:
            server_state["host"] = host

        def __enter__(self) -> "_FakeServer":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

        def serve_forever(self) -> None:
            server_state["served"] = True

    if host_env is None:
        monkeypatch.delenv("HOST", raising=False)
    else:
        monkeypatch.setenv("HOST", host_env)

    monkeypatch.setattr(
        relay_http.DriveRelayWsgiApp, "from_env", classmethod(lambda cls: fake_app)
    )
    monkeypatch.setattr(
        relay_http, "make_server", lambda host, port, app: _FakeServer(host, port, app)
    )
    monkeypatch.setattr(
        relay_http.sys, "argv", ["relay_http.py", "--port", "9099"]
    )

    relay_http.main()

    assert server_state["host"] == expected_host
    assert server_state["served"] is True


def test_main_host_flag_overrides_host_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_app = DriveRelayWsgiApp(
        repo_root=tmp_path,
        token_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
    )
    server_state: dict[str, Any] = {}

    class _FakeServer:
        def __init__(self, host: str, port: int, application: Any) -> None:
            server_state["host"] = host

        def __enter__(self) -> "_FakeServer":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

        def serve_forever(self) -> None:
            server_state["served"] = True

    monkeypatch.setenv("HOST", "10.0.0.5")
    monkeypatch.setattr(
        relay_http.DriveRelayWsgiApp, "from_env", classmethod(lambda cls: fake_app)
    )
    monkeypatch.setattr(
        relay_http, "make_server", lambda host, port, app: _FakeServer(host, port, app)
    )
    monkeypatch.setattr(
        relay_http.sys,
        "argv",
        ["relay_http.py", "--host", "192.168.1.1", "--port", "9099"],
    )

    relay_http.main()

    assert server_state["host"] == "192.168.1.1"
    assert server_state["served"] is True


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
