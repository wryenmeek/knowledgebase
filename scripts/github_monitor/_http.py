"""Shared HTTP helpers for the github_monitor script family.

All three scripts (``check_drift``, ``fetch_content``, ``synthesize_diff``)
need authenticated GitHub API access.  Centralising these helpers here
eliminates duplication and ensures consistent retry / token handling.

Authentication:
    Set ``GITHUB_APP_TOKEN`` (preferred) or ``GITHUB_TOKEN`` in the
    environment.  Tokens are never accepted as CLI arguments because that
    would expose them in ``ps aux`` and CI logs.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from scripts.github_monitor._types import GitHubAPIRequestError

_GITHUB_API_BASE = "https://api.github.com"
_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = (1.0, 2.0, 4.0)
# Cap server-supplied Retry-After at this value to prevent a misbehaving
# server from holding the CI job in a sleep indefinitely.
_MAX_RETRY_DELAY = 60.0


def _get_github_token() -> str | None:
    return os.environ.get("GITHUB_APP_TOKEN") or os.environ.get("GITHUB_TOKEN")


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header value into a capped delay in seconds.

    Handles both numeric (seconds) and HTTP-date formats per RFC 7231.
    Returns ``None`` if the value cannot be parsed or is absent; callers
    should fall back to their default exponential back-off delay.

    The returned value is capped at ``_MAX_RETRY_DELAY`` to prevent a
    misbehaving server from causing an indefinitely-long sleep.
    """
    if not value:
        return None
    try:
        return min(float(value), _MAX_RETRY_DELAY)
    except (ValueError, TypeError):
        # Non-numeric value (e.g. RFC 7231 HTTP-date like
        # "Wed, 21 Oct 2015 07:28:00 GMT") — fall back to default delay.
        return None


def _make_github_request(url: str, token: str) -> Any:
    """Make an authenticated GET request to the GitHub API with retry on 5xx.

    Returns the parsed JSON body.  Raises ``GitHubAPIRequestError`` on HTTP
    4xx/5xx (after retries for 5xx) or network errors.
    """
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "knowledgebase-github-monitor/1",
        },
    )
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if (exc.code >= 500 or exc.code == 429) and attempt < _MAX_RETRIES - 1:
                last_exc = exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                delay = _parse_retry_after(retry_after) or _RETRY_DELAY_SECONDS[attempt]
                time.sleep(delay)
                continue
            raise GitHubAPIRequestError(
                url=url, status_code=exc.code, detail=exc.reason
            ) from exc
        except urllib.error.URLError as exc:
            raise GitHubAPIRequestError(
                url=url, status_code=None, detail=str(exc.reason)
            ) from exc
    # All retries exhausted on 5xx or 429 — last_exc is always set here.
    raise GitHubAPIRequestError(
        url=url,
        status_code=getattr(last_exc, "code", None),
        detail=f"request failed after {_MAX_RETRIES} retries; last error: {last_exc}",
    )
