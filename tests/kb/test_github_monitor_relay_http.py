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
) -> tuple[str, dict[str, str], bytes]:
    status_holder: dict[str, str] = {}
    header_holder: dict[str, str] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        status_holder["status"] = status
        header_holder.update(dict(headers))

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


def test_from_env_rejects_invalid_max_body_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISPATCH_TARGET_OWNER", "owner")
    monkeypatch.setenv("DISPATCH_TARGET_REPO", "repo")
    monkeypatch.setenv("DISPATCH_TOKEN", "token")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("MAX_GITHUB_WEBHOOK_BODY_BYTES", "-1")

    with pytest.raises(RuntimeError, match="MAX_GITHUB_WEBHOOK_BODY_BYTES"):
        GitHubRelayWsgiApp.from_env()
