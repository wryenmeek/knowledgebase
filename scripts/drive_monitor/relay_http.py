"""Minimal WSGI entrypoint for Drive relay webhook handling."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterable
from wsgiref.simple_server import make_server
from wsgiref.types import StartResponse, WSGIEnvironment

from scripts.drive_monitor._relay import (
    DriveReplayCache,
    GitHubApiDispatchClient,
    relay_drive_notification,
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
    500: "Internal Server Error",
    502: "Bad Gateway",
}


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


class DriveRelayWsgiApp:
    """Minimal WSGI wrapper around ``relay_drive_notification``."""

    def __init__(
        self,
        *,
        repo_root: Path,
        token_secret: str,
        dispatch_client: GitHubApiDispatchClient,
    ) -> None:
        self._repo_root = repo_root
        self._token_secret = token_secret
        self._dispatch_client = dispatch_client
        self._replay_cache = DriveReplayCache()

    @classmethod
    def from_env(cls) -> "DriveRelayWsgiApp":
        repo_root_raw = os.environ.get("REPO_ROOT", ".")
        repo_root = Path(repo_root_raw).resolve()
        dispatch_client = GitHubApiDispatchClient(
            target_owner=_required_env("DISPATCH_TARGET_OWNER"),
            target_repo=_required_env("DISPATCH_TARGET_REPO"),
            token=_required_env("DISPATCH_TOKEN"),
        )
        return cls(
            repo_root=repo_root,
            token_secret=_required_env("DRIVE_CHANNEL_TOKEN_SECRET"),
            dispatch_client=dispatch_client,
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
        result = relay_drive_notification(
            repo_root=self._repo_root,
            headers=headers,
            token_secret=self._token_secret,
            dispatch_client=self._dispatch_client,
            replay_cache=self._replay_cache,
        )
        status_code = _STATUS_HTTP_MAP.get(result.status, 500)
        body = json.dumps(
            {
                "status": result.status,
                "reason": result.reason,
                "dispatched": result.dispatched,
                "payload": result.payload,
            },
            sort_keys=True,
        ).encode("utf-8")
        start_response(
            f"{status_code} {_STATUS_REASON_MAP.get(status_code, 'Internal Server Error')}",
            [
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]


_APP: DriveRelayWsgiApp | None = None


def app(environ: WSGIEnvironment, start_response: StartResponse) -> Iterable[bytes]:
    """WSGI entrypoint for server runtimes (for example gunicorn)."""

    global _APP
    if _APP is None:
        _APP = DriveRelayWsgiApp.from_env()
    return _APP(environ, start_response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    args = parser.parse_args()
    application = DriveRelayWsgiApp.from_env()
    with make_server(args.host, args.port, application) as server:
        print(f"Drive relay listening on http://{args.host}:{args.port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
