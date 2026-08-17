"""Shared repository_dispatch HTTP client for webhook relays."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Mapping, Protocol

_GITHUB_API_BASE = "https://api.github.com"


class RepositoryDispatchError(OSError):
    """Raised when repository_dispatch API requests fail."""


class RepositoryDispatchClient(Protocol):
    """Abstract dispatch client used by relay logic."""

    def dispatch(self, *, event_type: str, client_payload: Mapping[str, Any]) -> None:
        """Emit a repository_dispatch event."""


class GitHubApiDispatchClient:
    """Thin repository_dispatch wrapper around the GitHub REST API."""

    def __init__(
        self,
        *,
        target_owner: str,
        target_repo: str,
        token: str,
        base_url: str = _GITHUB_API_BASE,
        timeout_seconds: int = 30,
    ) -> None:
        if not target_owner or not target_repo:
            raise ValueError("target_owner and target_repo are required")
        if not token:
            raise ValueError("token is required")
        self._target_owner = target_owner
        self._target_repo = target_repo
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def dispatch(self, *, event_type: str, client_payload: Mapping[str, Any]) -> None:
        payload = {
            "event_type": event_type,
            "client_payload": dict(client_payload),
        }
        url = (
            f"{self._base_url}/repos/"
            f"{self._target_owner}/{self._target_repo}/dispatches"
        )
        # SECURITY: Validate URL scheme to prevent unintended protocol access (e.g., file://) (Bandit B310)
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL scheme: {url}")

        request = urllib.request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "knowledgebase-webhook-relay/1",
            },
        )
        try:
            with urllib.request.urlopen(  # nosec B310
                request, timeout=self._timeout_seconds
            ) as response:
                if getattr(response, "status", 204) >= 400:
                    raise RepositoryDispatchError(
                        f"repository_dispatch failed with HTTP {response.status}"
                    )
        except urllib.error.HTTPError as exc:
            raise RepositoryDispatchError(
                f"repository_dispatch failed with HTTP {exc.code}: {exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RepositoryDispatchError(
                f"repository_dispatch request failed: {exc.reason}"
            ) from exc


__all__ = [
    "GitHubApiDispatchClient",
    "RepositoryDispatchClient",
    "RepositoryDispatchError",
]
