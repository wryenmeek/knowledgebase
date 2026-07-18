"""Minimal WSGI entrypoint for Drive relay webhook handling."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable
from wsgiref.simple_server import make_server
from wsgiref.types import StartResponse, WSGIEnvironment

from scripts.drive_monitor._relay import (
    externalize_relay_reason,
    DriveReplayCache,
    GitHubApiDispatchClient,
    relay_drive_notification,
)
from scripts.relay_wsgi_common import (
    extract_headers,
    handle_common_http_envelope,
    json_response,
    required_env,
)

_STATUS_HTTP_MAP = {
    "dispatched": 202,
    "ignored": 202,
    "rejected": 400,
    "failed": 502,
}


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
            target_owner=required_env("DISPATCH_TARGET_OWNER"),
            target_repo=required_env("DISPATCH_TARGET_REPO"),
            token=required_env("DISPATCH_TOKEN"),
        )
        return cls(
            repo_root=repo_root,
            token_secret=required_env("DRIVE_CHANNEL_TOKEN_SECRET"),
            dispatch_client=dispatch_client,
        )

    def __call__(
        self, environ: WSGIEnvironment, start_response: StartResponse
    ) -> Iterable[bytes]:
        common_response = handle_common_http_envelope(environ, start_response)
        if common_response is not None:
            return common_response

        headers = extract_headers(environ)
        result = relay_drive_notification(
            repo_root=self._repo_root,
            headers=headers,
            token_secret=self._token_secret,
            dispatch_client=self._dispatch_client,
            replay_cache=self._replay_cache,
        )
        status_code = _STATUS_HTTP_MAP.get(result.status, 500)
        external_reason = externalize_relay_reason(
            status=result.status,
            reason=result.reason,
        )
        if external_reason != result.reason:
            print(
                f"[drive-relay] status={result.status} internal_reason={result.reason}",
                file=sys.stderr,
                flush=True,
            )
        return json_response(
            start_response=start_response,
            status_code=status_code,
            payload={
                "status": result.status,
                "reason": external_reason,
                "dispatched": result.dispatched,
                "payload": result.payload,
            },
        )


_APP: DriveRelayWsgiApp | None = None


def app(environ: WSGIEnvironment, start_response: StartResponse) -> Iterable[bytes]:
    """WSGI entrypoint for server runtimes (for example gunicorn)."""

    global _APP
    if _APP is None:
        _APP = DriveRelayWsgiApp.from_env()
    return _APP(environ, start_response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    # Security: Avoid defaulting to 0.0.0.0 to prevent unintended network exposure (Bandit B104)
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    args = parser.parse_args()
    application = DriveRelayWsgiApp.from_env()
    with make_server(args.host, args.port, application) as server:
        print(f"Drive relay listening on http://{args.host}:{args.port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
