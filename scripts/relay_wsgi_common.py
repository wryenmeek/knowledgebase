"""Shared WSGI helpers for relay HTTP wrappers."""

from __future__ import annotations

import json
import os
from typing import Any, Iterable, Mapping
from wsgiref.types import StartResponse, WSGIEnvironment

_STATUS_REASON_MAP = {
    200: "OK",
    202: "Accepted",
    400: "Bad Request",
    405: "Method Not Allowed",
    413: "Payload Too Large",
    500: "Internal Server Error",
    502: "Bad Gateway",
}


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def extract_headers(environ: WSGIEnvironment) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in environ.items():
        if not key.startswith("HTTP_"):
            continue
        header_name = key[5:].replace("_", "-")
        headers[header_name] = value
    if "CONTENT_TYPE" in environ:
        headers["Content-Type"] = environ["CONTENT_TYPE"]
    return headers


def json_response(
    *,
    start_response: StartResponse,
    status_code: int,
    payload: Mapping[str, Any],
) -> list[bytes]:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    start_response(
        f"{status_code} {_STATUS_REASON_MAP.get(status_code, 'Internal Server Error')}",
        [
            ("Content-Type", "application/json"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


def handle_common_http_envelope(
    environ: WSGIEnvironment,
    start_response: StartResponse,
) -> Iterable[bytes] | None:
    method = str(environ.get("REQUEST_METHOD", "")).upper()
    path = str(environ.get("PATH_INFO", "/"))

    if path == "/healthz":
        return json_response(
            start_response=start_response,
            status_code=200,
            payload={"status": "ok"},
        )

    if method != "POST":
        return json_response(
            start_response=start_response,
            status_code=405,
            payload={"error": "method_not_allowed"},
        )

    return None


__all__ = [
    "extract_headers",
    "handle_common_http_envelope",
    "json_response",
    "required_env",
]
