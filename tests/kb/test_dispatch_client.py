"""Unit tests for scripts/github_monitor/dispatch_client.py."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import pytest

from scripts.github_monitor.dispatch_client import (
    GitHubApiDispatchClient,
    RepositoryDispatchError,
)


class _Response:
    def __init__(self, status: int = 204) -> None:
        self.status = status

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


def test_dispatch_posts_expected_request_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def _urlopen(request: urllib.request.Request, timeout: int) -> _Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response(status=204)

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)

    client = GitHubApiDispatchClient(
        target_owner="owner",
        target_repo="repo",
        token="token-123",
    )
    client.dispatch(
        event_type="upstream-source-updated",
        client_payload={"registry_path": "raw/github-sources/source.source-registry.json"},
    )

    request: urllib.request.Request = captured["request"]
    assert request.full_url == "https://api.github.com/repos/owner/repo/dispatches"
    assert request.get_method() == "POST"
    assert captured["timeout"] == 30
    body = json.loads(request.data.decode("utf-8"))
    assert body["event_type"] == "upstream-source-updated"
    assert body["client_payload"]["registry_path"] == "raw/github-sources/source.source-registry.json"
    normalized_headers = {key.lower(): value for key, value in request.headers.items()}
    assert normalized_headers["authorization"] == "Bearer token-123"
    assert normalized_headers["content-type"] == "application/json"


def test_dispatch_maps_http_error_to_repository_dispatch_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _urlopen(request: urllib.request.Request, timeout: int) -> _Response:
        raise urllib.error.HTTPError(
            url=request.full_url,
            code=502,
            msg="Bad Gateway",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    client = GitHubApiDispatchClient(
        target_owner="owner",
        target_repo="repo",
        token="token-123",
    )
    with pytest.raises(RepositoryDispatchError, match="HTTP 502"):
        client.dispatch(event_type="upstream-source-updated", client_payload={"k": "v"})


def test_dispatch_maps_non_exception_http_error_status_to_repository_dispatch_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _urlopen(request: urllib.request.Request, timeout: int) -> _Response:
        return _Response(status=500)

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    client = GitHubApiDispatchClient(
        target_owner="owner",
        target_repo="repo",
        token="token-123",
    )
    with pytest.raises(RepositoryDispatchError, match="HTTP 500"):
        client.dispatch(event_type="upstream-source-updated", client_payload={"k": "v"})


def test_dispatch_maps_url_error_to_repository_dispatch_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _urlopen(request: urllib.request.Request, timeout: int) -> _Response:
        raise urllib.error.URLError(reason="network unreachable")

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    client = GitHubApiDispatchClient(
        target_owner="owner",
        target_repo="repo",
        token="token-123",
    )
    with pytest.raises(RepositoryDispatchError, match="network unreachable"):
        client.dispatch(event_type="upstream-source-updated", client_payload={"k": "v"})


def test_client_constructor_requires_owner_repo_and_token() -> None:
    with pytest.raises(ValueError):
        GitHubApiDispatchClient(target_owner="", target_repo="repo", token="token")
    with pytest.raises(ValueError):
        GitHubApiDispatchClient(target_owner="owner", target_repo="", token="token")
    with pytest.raises(ValueError):
        GitHubApiDispatchClient(target_owner="owner", target_repo="repo", token="")
