"""Minimal WSGI entrypoint for GitHub relay webhook handling."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterable
from wsgiref.simple_server import make_server
from wsgiref.types import StartResponse, WSGIEnvironment

from scripts.github_monitor._relay import (
    GitHubDeliveryReplayCache,
    GitHubRelayResult,
    GitHubApiDispatchClient,
    relay_github_push_event,
)

_STATUS_HTTP_MAP = {
    "dispatched": 202,
    "ignored": 202,
    "rejected": 400,
    "failed": 502,
}
_STATUS_REASON_MAP = {
    202: "Accepted",
    400: "Bad Request",
    413: "Payload Too Large",
    500: "Internal Server Error",
    502: "Bad Gateway",
}
_DEFAULT_MAX_BODY_BYTES = 1_048_576


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def _extract_headers(environ: WSGIEnvironment) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in environ.items():
        if not key.startswith("HTTP_"):
            continue
        header_name = key[5:].replace("_", "-")
        headers[header_name] = value
    if "CONTENT_TYPE" in environ:
        headers["Content-Type"] = environ["CONTENT_TYPE"]
    return headers


class RequestBodyError(ValueError):
    """Raised when the HTTP request body is invalid or unsafe."""

    def __init__(self, reason: str, *, status_code: int = 400) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


def _load_max_body_bytes() -> int:
    raw_value = os.environ.get("MAX_GITHUB_WEBHOOK_BODY_BYTES", "").strip()
    if not raw_value:
        return _DEFAULT_MAX_BODY_BYTES
    try:
        parsed = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(
            "MAX_GITHUB_WEBHOOK_BODY_BYTES must be a positive integer"
        ) from exc
    if parsed <= 0:
        raise RuntimeError("MAX_GITHUB_WEBHOOK_BODY_BYTES must be a positive integer")
    return parsed


def _read_request_body(environ: WSGIEnvironment, *, max_body_bytes: int) -> bytes:
    content_length_raw = str(environ.get("CONTENT_LENGTH", "")).strip()
    if not content_length_raw:
        raise RequestBodyError("missing_content_length")
    try:
        content_length = int(content_length_raw)
    except ValueError as exc:
        raise RequestBodyError("invalid_content_length") from exc
    if content_length <= 0:
        raise RequestBodyError("invalid_content_length")
    if content_length > max_body_bytes:
        raise RequestBodyError("request_body_too_large", status_code=413)
    body_stream = environ.get("wsgi.input")
    if body_stream is None:
        raise RequestBodyError("missing_request_body_stream")
    body = body_stream.read(content_length)
    if len(body) != content_length:
        raise RequestBodyError("incomplete_request_body")
    return body


def _serialize_result(result: GitHubRelayResult) -> bytes:
    return json.dumps(
        {
            "status": result.status,
            "reason": result.reason,
            "dispatched_count": result.dispatched_count,
            "payloads": result.payloads,
        },
        sort_keys=True,
    ).encode("utf-8")


class GitHubRelayWsgiApp:
    """Minimal WSGI wrapper around ``relay_github_push_event``."""

    def __init__(
        self,
        *,
        repo_root: Path,
        webhook_secret: str,
        dispatch_client: GitHubApiDispatchClient,
        max_body_bytes: int = _DEFAULT_MAX_BODY_BYTES,
    ) -> None:
        if max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be positive")
        self._repo_root = repo_root
        self._webhook_secret = webhook_secret
        self._dispatch_client = dispatch_client
        self._max_body_bytes = max_body_bytes
        self._replay_cache = GitHubDeliveryReplayCache()

    @classmethod
    def from_env(cls) -> "GitHubRelayWsgiApp":
        repo_root_raw = os.environ.get("REPO_ROOT", ".")
        repo_root = Path(repo_root_raw).resolve()
        dispatch_client = GitHubApiDispatchClient(
            target_owner=_required_env("DISPATCH_TARGET_OWNER"),
            target_repo=_required_env("DISPATCH_TARGET_REPO"),
            token=_required_env("DISPATCH_TOKEN"),
        )
        return cls(
            repo_root=repo_root,
            webhook_secret=_required_env("GITHUB_WEBHOOK_SECRET"),
            dispatch_client=dispatch_client,
            max_body_bytes=_load_max_body_bytes(),
        )

    def __call__(
        self, environ: WSGIEnvironment, start_response: StartResponse
    ) -> Iterable[bytes]:
        method = str(environ.get("REQUEST_METHOD", "")).upper()
        path = str(environ.get("PATH_INFO", "/"))

        if path == "/healthz":
            body = json.dumps({"status": "ok"}).encode("utf-8")
            start_response(
                "200 OK",
                [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(body))),
                ],
            )
            return [body]

        if method != "POST":
            body = json.dumps({"error": "method_not_allowed"}).encode("utf-8")
            start_response(
                "405 Method Not Allowed",
                [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(body))),
                ],
            )
            return [body]

        headers = _extract_headers(environ)
        try:
            body = _read_request_body(environ, max_body_bytes=self._max_body_bytes)
        except RequestBodyError as exc:
            rejected_body = json.dumps(
                {
                    "status": "rejected",
                    "reason": exc.reason,
                    "dispatched_count": 0,
                    "payloads": [],
                },
                sort_keys=True,
            ).encode("utf-8")
            start_response(
                f"{exc.status_code} {_STATUS_REASON_MAP.get(exc.status_code, 'Bad Request')}",
                [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(rejected_body))),
                ],
            )
            return [rejected_body]
        result = relay_github_push_event(
            repo_root=self._repo_root,
            headers=headers,
            body=body,
            webhook_secret=self._webhook_secret,
            dispatch_client=self._dispatch_client,
            replay_cache=self._replay_cache,
        )
        status_code = _STATUS_HTTP_MAP.get(result.status, 500)
        serialized = _serialize_result(result)
        start_response(
            f"{status_code} {_STATUS_REASON_MAP.get(status_code, 'Internal Server Error')}",
            [
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(serialized))),
            ],
        )
        return [serialized]


_APP: GitHubRelayWsgiApp | None = None


def app(environ: WSGIEnvironment, start_response: StartResponse) -> Iterable[bytes]:
    """WSGI entrypoint for server runtimes (for example gunicorn)."""

    global _APP
    if _APP is None:
        _APP = GitHubRelayWsgiApp.from_env()
    return _APP(environ, start_response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    args = parser.parse_args()
    application = GitHubRelayWsgiApp.from_env()
    with make_server(args.host, args.port, application) as server:
        print(f"GitHub relay listening on http://{args.host}:{args.port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
