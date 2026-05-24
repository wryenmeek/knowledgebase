"""Direct unit tests for scripts/relay_wsgi_common.py."""

from __future__ import annotations

import json
from typing import Any

import pytest

from scripts.relay_wsgi_common import (
    extract_headers,
    handle_common_http_envelope,
    json_response,
    required_env,
)


def _capture_start_response() -> tuple[Any, dict[str, str], dict[str, str]]:
    status_holder: dict[str, str] = {}
    header_holder: dict[str, str] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        status_holder["status"] = status
        header_holder.update(dict(headers))

    return start_response, status_holder, header_holder


def test_required_env_returns_trimmed_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_REQUIRED_ENV", "  value  ")

    assert required_env("TEST_REQUIRED_ENV") == "value"


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_required_env_rejects_missing_or_blank(
    monkeypatch: pytest.MonkeyPatch, raw: str | None
) -> None:
    if raw is None:
        monkeypatch.delenv("TEST_REQUIRED_ENV", raising=False)
    else:
        monkeypatch.setenv("TEST_REQUIRED_ENV", raw)

    with pytest.raises(RuntimeError, match="TEST_REQUIRED_ENV"):
        required_env("TEST_REQUIRED_ENV")


def test_extract_headers_maps_http_keys_and_content_type() -> None:
    headers = extract_headers(
        {
            "HTTP_X_GITHUB_EVENT": "push",
            "HTTP_X_CUSTOM_HEADER": "abc",
            "CONTENT_TYPE": "application/json",
            "REQUEST_METHOD": "POST",
        }
    )

    assert headers == {
        "X-GITHUB-EVENT": "push",
        "X-CUSTOM-HEADER": "abc",
        "Content-Type": "application/json",
    }


def test_json_response_sets_status_headers_and_sorted_body() -> None:
    start_response, status_holder, header_holder = _capture_start_response()

    response = json_response(
        start_response=start_response,
        status_code=202,
        payload={"b": 2, "a": 1},
    )
    body = b"".join(response)
    parsed = json.loads(body.decode("utf-8"))

    assert status_holder["status"] == "202 Accepted"
    assert header_holder["Content-Type"] == "application/json"
    assert header_holder["Content-Length"] == str(len(body))
    assert parsed == {"a": 1, "b": 2}
    assert body.decode("utf-8").index('"a"') < body.decode("utf-8").index('"b"')


def test_json_response_unknown_status_uses_internal_server_error_reason() -> None:
    start_response, status_holder, _ = _capture_start_response()

    json_response(start_response=start_response, status_code=299, payload={"ok": True})

    assert status_holder["status"] == "299 Internal Server Error"


def test_handle_common_http_envelope_healthz_returns_ok() -> None:
    start_response, status_holder, _ = _capture_start_response()

    response = handle_common_http_envelope(
        {"REQUEST_METHOD": "GET", "PATH_INFO": "/healthz"},
        start_response,
    )
    assert response is not None
    assert status_holder["status"] == "200 OK"
    assert json.loads(b"".join(response).decode("utf-8")) == {"status": "ok"}


def test_handle_common_http_envelope_non_post_returns_405() -> None:
    start_response, status_holder, _ = _capture_start_response()

    response = handle_common_http_envelope(
        {"REQUEST_METHOD": "GET", "PATH_INFO": "/"},
        start_response,
    )
    assert response is not None
    assert status_holder["status"] == "405 Method Not Allowed"
    assert json.loads(b"".join(response).decode("utf-8")) == {
        "error": "method_not_allowed"
    }


def test_handle_common_http_envelope_post_returns_none() -> None:
    start_response, _, _ = _capture_start_response()

    assert (
        handle_common_http_envelope(
            {"REQUEST_METHOD": "POST", "PATH_INFO": "/"},
            start_response,
        )
        is None
    )
