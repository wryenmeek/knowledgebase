"""Unit tests for scripts/github_monitor/relay_http.py."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

import scripts.github_monitor.relay_http as relay_http
from scripts.github_monitor._relay import GitHubRelayResult
from scripts.github_monitor.relay_http import GitHubRelayWsgiApp


class _NoopDispatchClient:
    def dispatch(self, *, event_type: str, client_payload: dict[str, Any]) -> None:
        return None


def _invoke_wsgi_app(
    app: GitHubRelayWsgiApp, environ: dict[str, Any]
) -> tuple[str, list[tuple[str, str]], bytes]:
    status_holder: dict[str, str] = {}
    header_holder: list[tuple[str, str]] = []

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        status_holder["status"] = status
        header_holder.extend(headers)

    body = b"".join(app(environ, start_response))
    return status_holder["status"], header_holder, body


def test_healthz_returns_ok_json(tmp_path: Path) -> None:
    app = GitHubRelayWsgiApp(
        repo_root=tmp_path,
        webhook_secret="secret",
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
    app = GitHubRelayWsgiApp(
        repo_root=tmp_path,
        webhook_secret="secret",
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


def test_oversized_request_body_returns_413(tmp_path: Path) -> None:
    app = GitHubRelayWsgiApp(
        repo_root=tmp_path,
        webhook_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
        max_body_bytes=4,
    )
    payload = b"12345"
    status, _, body = _invoke_wsgi_app(
        app,
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/",
            "CONTENT_LENGTH": str(len(payload)),
            "wsgi.input": io.BytesIO(payload),
        },
    )

    assert status.startswith("413 ")
    parsed = json.loads(body.decode("utf-8"))
    assert parsed["status"] == "rejected"
    assert parsed["reason"] == "request_body_too_large"


def test_max_sized_request_body_is_accepted_and_relayed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def _fake_relay_github_push_event(**kwargs: Any) -> GitHubRelayResult:
        captured.update(kwargs)
        return GitHubRelayResult(
            status="ignored",
            reason="replay_suppressed",
            dispatched_count=0,
            payloads=(),
        )

    monkeypatch.setattr(relay_http, "relay_github_push_event", _fake_relay_github_push_event)
    app = GitHubRelayWsgiApp(
        repo_root=tmp_path,
        webhook_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
        max_body_bytes=4,
    )
    payload = b"1234"
    status, _, body = _invoke_wsgi_app(
        app,
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/",
            "CONTENT_LENGTH": str(len(payload)),
            "wsgi.input": io.BytesIO(payload),
        },
    )

    assert status.startswith("202 ")
    parsed = json.loads(body.decode("utf-8"))
    assert parsed["status"] == "ignored"
    assert parsed["reason"] == "replay_suppressed"
    assert captured["body"] == payload


def test_missing_content_length_returns_400_rejected(tmp_path: Path) -> None:
    app = GitHubRelayWsgiApp(
        repo_root=tmp_path,
        webhook_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
    )
    status, _, body = _invoke_wsgi_app(
        app,
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/",
            "wsgi.input": io.BytesIO(b"{}"),
        },
    )

    assert status.startswith("400 ")
    parsed = json.loads(body.decode("utf-8"))
    assert parsed["status"] == "rejected"
    assert parsed["reason"] == "missing_content_length"


def test_invalid_content_length_returns_400_rejected(tmp_path: Path) -> None:
    app = GitHubRelayWsgiApp(
        repo_root=tmp_path,
        webhook_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
    )
    status, _, body = _invoke_wsgi_app(
        app,
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/",
            "CONTENT_LENGTH": "not-a-number",
            "wsgi.input": io.BytesIO(b"{}"),
        },
    )

    assert status.startswith("400 ")
    parsed = json.loads(body.decode("utf-8"))
    assert parsed["status"] == "rejected"
    assert parsed["reason"] == "invalid_content_length"


@pytest.mark.parametrize("content_length", ["0", "-7"])
def test_zero_or_negative_content_length_returns_400_rejected(
    tmp_path: Path, content_length: str
) -> None:
    app = GitHubRelayWsgiApp(
        repo_root=tmp_path,
        webhook_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
    )
    status, _, body = _invoke_wsgi_app(
        app,
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/",
            "CONTENT_LENGTH": content_length,
            "wsgi.input": io.BytesIO(b"{}"),
        },
    )

    assert status.startswith("400 ")
    parsed = json.loads(body.decode("utf-8"))
    assert parsed["status"] == "rejected"
    assert parsed["reason"] == "invalid_content_length"


def test_missing_wsgi_input_returns_400_rejected(tmp_path: Path) -> None:
    app = GitHubRelayWsgiApp(
        repo_root=tmp_path,
        webhook_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
    )
    status, _, body = _invoke_wsgi_app(
        app,
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/",
            "CONTENT_LENGTH": "2",
        },
    )

    assert status.startswith("400 ")
    parsed = json.loads(body.decode("utf-8"))
    assert parsed["status"] == "rejected"
    assert parsed["reason"] == "missing_request_body_stream"


def test_incomplete_request_body_returns_400_rejected(tmp_path: Path) -> None:
    app = GitHubRelayWsgiApp(
        repo_root=tmp_path,
        webhook_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
    )
    status, _, body = _invoke_wsgi_app(
        app,
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/",
            "CONTENT_LENGTH": "4",
            "wsgi.input": io.BytesIO(b"{}"),
        },
    )

    assert status.startswith("400 ")
    parsed = json.loads(body.decode("utf-8"))
    assert parsed["status"] == "rejected"
    assert parsed["reason"] == "incomplete_request_body"


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
    result = GitHubRelayResult(
        status=relay_status,
        reason="reason",
        dispatched_count=0,
        payloads=(),
    )
    monkeypatch.setattr(relay_http, "relay_github_push_event", lambda **_: result)
    app = GitHubRelayWsgiApp(
        repo_root=tmp_path,
        webhook_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
    )
    payload = b"{}"
    status, _, body = _invoke_wsgi_app(
        app,
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/",
            "CONTENT_LENGTH": str(len(payload)),
            "wsgi.input": io.BytesIO(payload),
        },
    )

    assert status.startswith(expected_http)
    assert json.loads(body.decode("utf-8"))["status"] == relay_status


def test_from_env_requires_webhook_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISPATCH_TARGET_OWNER", "owner")
    monkeypatch.setenv("DISPATCH_TARGET_REPO", "repo")
    monkeypatch.setenv("DISPATCH_TOKEN", "token")
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="GITHUB_WEBHOOK_SECRET"):
        GitHubRelayWsgiApp.from_env()


def test_from_env_builds_app_with_valid_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("DISPATCH_TARGET_OWNER", "owner")
    monkeypatch.setenv("DISPATCH_TARGET_REPO", "repo")
    monkeypatch.setenv("DISPATCH_TOKEN", "token")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("MAX_GITHUB_WEBHOOK_BODY_BYTES", "2048")

    app = GitHubRelayWsgiApp.from_env()
    captured: dict[str, Any] = {}

    def _fake_relay_github_push_event(**kwargs: Any) -> GitHubRelayResult:
        captured.update(kwargs)
        return GitHubRelayResult(
            status="ignored",
            reason="replay_suppressed",
            dispatched_count=0,
            payloads=(),
        )

    monkeypatch.setattr(relay_http, "relay_github_push_event", _fake_relay_github_push_event)
    status, _, body = _invoke_wsgi_app(
        app,
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/",
            "CONTENT_LENGTH": "2",
            "wsgi.input": io.BytesIO(b"{}"),
        },
    )
    oversized_status, _, oversized_body = _invoke_wsgi_app(
        app,
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/",
            "CONTENT_LENGTH": "2049",
            "wsgi.input": io.BytesIO(b"x" * 2049),
        },
    )

    assert status.startswith("202 ")
    assert json.loads(body.decode("utf-8"))["status"] == "ignored"
    assert captured["repo_root"] == tmp_path.resolve()
    assert captured["webhook_secret"] == "secret"
    assert oversized_status.startswith("413 ")
    oversized_parsed = json.loads(oversized_body.decode("utf-8"))
    assert oversized_parsed["status"] == "rejected"
    assert oversized_parsed["reason"] == "request_body_too_large"


def test_from_env_rejects_invalid_max_body_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISPATCH_TARGET_OWNER", "owner")
    monkeypatch.setenv("DISPATCH_TARGET_REPO", "repo")
    monkeypatch.setenv("DISPATCH_TOKEN", "token")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("MAX_GITHUB_WEBHOOK_BODY_BYTES", "-1")

    with pytest.raises(RuntimeError, match="MAX_GITHUB_WEBHOOK_BODY_BYTES"):
        GitHubRelayWsgiApp.from_env()


def test_from_env_rejects_non_integer_max_body_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISPATCH_TARGET_OWNER", "owner")
    monkeypatch.setenv("DISPATCH_TARGET_REPO", "repo")
    monkeypatch.setenv("DISPATCH_TOKEN", "token")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("MAX_GITHUB_WEBHOOK_BODY_BYTES", "not-an-integer")

    with pytest.raises(RuntimeError, match="MAX_GITHUB_WEBHOOK_BODY_BYTES"):
        GitHubRelayWsgiApp.from_env()


def test_module_app_bootstraps_once_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    created: dict[str, int] = {"count": 0}
    fake_app = GitHubRelayWsgiApp(
        repo_root=tmp_path,
        webhook_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
    )

    def _fake_from_env(cls: type[GitHubRelayWsgiApp]) -> GitHubRelayWsgiApp:
        created["count"] += 1
        return fake_app

    monkeypatch.setattr(relay_http, "_APP", None)
    monkeypatch.setattr(
        relay_http.GitHubRelayWsgiApp, "from_env", classmethod(_fake_from_env)
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
    fake_app = GitHubRelayWsgiApp(
        repo_root=tmp_path,
        webhook_secret="secret",
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
        relay_http.GitHubRelayWsgiApp, "from_env", classmethod(lambda cls: fake_app)
    )
    monkeypatch.setattr(
        relay_http, "make_server", lambda host, port, app: _FakeServer(host, port, app)
    )
    monkeypatch.setattr(
        relay_http.sys, "argv", ["relay_http.py", "--host", "127.0.0.1", "--port", "8099"]
    )

    relay_http.main()

    assert server_state["host"] == "127.0.0.1"
    assert server_state["port"] == 8099
    assert server_state["application"] is fake_app
    assert server_state["served"] is True


@pytest.mark.parametrize(
    ("relay_status", "internal_reason", "expected_reason"),
    [
        ("rejected", "registry file is unreadable/invalid: raw/github-sources/x.source-registry.json", "request_rejected"),
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
    result = GitHubRelayResult(
        status=relay_status,
        reason=internal_reason,
        dispatched_count=0,
        payloads=(),
    )
    monkeypatch.setattr(relay_http, "relay_github_push_event", lambda **_: result)
    app = GitHubRelayWsgiApp(
        repo_root=tmp_path,
        webhook_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
    )
    payload = b"{}"
    status, _, body = _invoke_wsgi_app(
        app,
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/",
            "CONTENT_LENGTH": str(len(payload)),
            "wsgi.input": io.BytesIO(payload),
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
    result = GitHubRelayResult(
        status=relay_status,
        reason=reason,
        dispatched_count=0,
        payloads=(),
    )
    monkeypatch.setattr(relay_http, "relay_github_push_event", lambda **_: result)
    app = GitHubRelayWsgiApp(
        repo_root=tmp_path,
        webhook_secret="secret",
        dispatch_client=_NoopDispatchClient(),  # type: ignore[arg-type]
    )
    payload = b"{}"
    status, _, body = _invoke_wsgi_app(
        app,
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/",
            "CONTENT_LENGTH": str(len(payload)),
            "wsgi.input": io.BytesIO(payload),
        },
    )

    assert status.startswith("202 ")
    parsed = json.loads(body.decode("utf-8"))
    assert parsed["status"] == relay_status
    assert parsed["reason"] == reason
