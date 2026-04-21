"""Fetch content for drifted GitHub sources (Phase 2 — write-capable).

Reads the drift report produced by ``check_drift.py``, downloads the current
file bytes from the GitHub contents API for every drifted entry, writes them
to ``raw/assets/{owner}/{repo}/{commit_sha}/{path}`` using
``exclusive_create_write_once()``, and advances ``last_fetched_commit_sha``
and ``last_fetched_blob_sha`` in the source registry.

This script does NOT modify ``last_applied_*`` fields — that is the
responsibility of ``synthesize_diff.py`` (Phase 3).

Usage::

    python -m scripts.github_monitor.fetch_content \\
        --drift-report drift-report.json \\
        --approval approved \\
        [--repo-root /path/to/repo]

Requires ``--approval approved`` for any write operation.  Authentication:
set ``GITHUB_APP_TOKEN`` (preferred) or ``GITHUB_TOKEN`` in the environment.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from scripts._optional_surface_common import (
    APPROVAL_APPROVED,
    APPROVAL_NONE,
    STATUS_FAIL,
    STATUS_PASS,
    JsonArgumentParser,
    SurfaceResult,
    approval_required_result,
    base_path_rules,
    invalid_input_result,
    looks_like_repo_root,
    repo_root_failure,
    run_surface_cli,
)
from scripts.kb.contracts import GitHubMonitorReasonCode
from scripts.kb.write_utils import exclusive_create_write_once
from scripts.github_monitor._registry import find_registry_for, update_last_fetched
from scripts.github_monitor._types import (
    DriftedEntry,
    validate_contents_response,
    validate_drift_report,
    GitHubAPIRequestError,
    GitHubAPIResponseError,
)
from scripts.github_monitor._validators import build_asset_path, validate_external_path
from scripts.github_monitor.check_drift import _get_github_token, _make_github_request

SURFACE = "github_monitor.fetch_content"
MODE = "fetch"

_GITHUB_API_BASE = "https://api.github.com"


def _path_rules() -> dict[str, Any]:
    return base_path_rules(
        allowed_roots=["raw/assets", "raw/github-sources"],
        allowed_suffixes=None,
    )


def _fetch_and_store_asset(
    repo_root: Path,
    entry: DriftedEntry,
    github_token: str,
) -> tuple[bool, str, str]:
    """Fetch asset bytes from GitHub and write to raw/assets/.

    Returns ``(success, commit_sha, sha256_hex)``.
    ``commit_sha`` is the commit SHA used as the directory segment.
    ``sha256_hex`` is the SHA-256 hex digest of the raw bytes.

    On error raises ``GitHubAPIRequestError``, ``GitHubAPIResponseError``,
    or ``ValueError`` (path traversal / asset path bounds check).
    """
    owner = entry["owner"]
    repo = entry["repo"]
    path = validate_external_path(entry["path"])
    commit_sha = entry["current_commit_sha"]
    expected_blob_sha = entry["current_blob_sha"]

    contents_url = (
        f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}"
        f"?ref={commit_sha}"
    )
    raw = _make_github_request(contents_url, github_token)
    contents = validate_contents_response(raw)

    if contents["sha"] != expected_blob_sha:
        raise ValueError(
            f"GitHub API returned blob SHA {contents['sha']!r} but drift report "
            f"expected {expected_blob_sha!r} for {owner}/{repo}/{path}"
        )

    raw_bytes = base64.b64decode(contents["content"].replace("\n", ""))
    sha256_hex = hashlib.sha256(raw_bytes).hexdigest()

    asset_path = build_asset_path(repo_root, owner, repo, commit_sha, path)
    exclusive_create_write_once(asset_path, raw_bytes)

    return True, commit_sha, sha256_hex


def fetch_content(
    *,
    repo_root: Path,
    drift_report_path: Path,
    github_token: str,
) -> SurfaceResult:
    """Core logic: fetch assets for all drifted entries in the drift report."""
    try:
        raw_report = json.loads(drift_report_path.read_text(encoding="utf-8"))
        report = validate_drift_report(raw_report)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_FAIL,
            reason_code=str(GitHubMonitorReasonCode.FETCH_FAILED),
            message=f"Failed to read/validate drift report: {exc}",
            path_rules=_path_rules(),
        )

    drifted: list[DriftedEntry] = report["drifted"]
    if not drifted:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_PASS,
            reason_code=str(GitHubMonitorReasonCode.NO_DRIFT),
            message="No drifted entries in drift report; nothing to fetch.",
            summary={"fetched_count": 0, "error_count": 0},
        )

    fetched: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for entry in drifted:
        owner = entry["owner"]
        repo = entry["repo"]
        path = entry["path"]

        try:
            _, commit_sha, _sha256 = _fetch_and_store_asset(
                repo_root, entry, github_token
            )
        except (GitHubAPIRequestError, GitHubAPIResponseError, ValueError, OSError) as exc:
            reason = (
                str(GitHubMonitorReasonCode.UNREACHABLE)
                if isinstance(exc, GitHubAPIRequestError) and exc.status_code in (401, 403, 404)
                else str(GitHubMonitorReasonCode.FETCH_FAILED)
            )
            errors.append(
                {
                    "path": path,
                    "reason_code": reason,
                    "message": str(exc),
                }
            )
            continue

        # Update registry under raw/.github-sources.lock.
        registry_path = find_registry_for(repo_root, owner, repo)
        if registry_path is None:
            errors.append(
                {
                    "path": path,
                    "reason_code": str(GitHubMonitorReasonCode.FETCH_FAILED),
                    "message": f"No registry file found for {owner}/{repo}",
                }
            )
            continue

        try:
            update_last_fetched(
                repo_root,
                registry_path,
                path,
                commit_sha=entry["current_commit_sha"],
                blob_sha=entry["current_blob_sha"],
            )
        except OSError as exc:
            errors.append(
                {
                    "path": path,
                    "reason_code": str(GitHubMonitorReasonCode.REGISTRY_LOCKED),
                    "message": f"Registry update failed: {exc}",
                }
            )
            continue

        fetched.append(
            {
                "owner": owner,
                "repo": repo,
                "path": path,
                "commit_sha": entry["current_commit_sha"],
                "blob_sha": entry["current_blob_sha"],
                "status": STATUS_PASS,
                "reason_code": str(GitHubMonitorReasonCode.NO_DRIFT),
                "message": f"Asset fetched and stored",
            }
        )

    status = STATUS_PASS if not errors else STATUS_FAIL
    reason_code = (
        str(GitHubMonitorReasonCode.FETCH_FAILED)
        if errors
        else str(GitHubMonitorReasonCode.NO_DRIFT)
    )
    message = (
        f"fetch complete: {len(fetched)} fetched, {len(errors)} errors"
    )

    return SurfaceResult(
        surface=SURFACE,
        mode=MODE,
        status=status,
        reason_code=reason_code,
        message=message,
        approval=APPROVAL_APPROVED,
        summary={
            "fetched_count": len(fetched),
            "error_count": len(errors),
        },
        items=tuple(
            {
                "path": str(e.get("path", "")),
                "status": STATUS_FAIL,
                "reason_code": str(e.get("reason_code", "")),
                "message": str(e.get("message", "")),
            }
            for e in errors
        ),
    )


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Fetch content for drifted GitHub source files."
    )
    parser.add_argument(
        "--drift-report",
        required=True,
        metavar="PATH",
        help="Path to the drift report JSON produced by check_drift.py.",
    )
    parser.add_argument(
        "--approval",
        default=APPROVAL_NONE,
        choices=[APPROVAL_NONE, APPROVAL_APPROVED],
        help="Pass 'approved' to enable write operations.",
    )
    parser.add_argument(
        "--repo-root",
        metavar="PATH",
        default=".",
        help="Path to the knowledgebase repository root (default: current directory).",
    )
    return parser


def _args_to_kwargs(args: Any) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()

    if not looks_like_repo_root(repo_root):
        return {"_sentinel": "repo_root_missing", "repo_root": repo_root}

    if args.approval != APPROVAL_APPROVED:
        return {"_sentinel": "approval_required"}

    token = _get_github_token()
    if not token:
        return {
            "_sentinel": "invalid_input",
            "message": (
                "No GitHub token found. Set GITHUB_APP_TOKEN or GITHUB_TOKEN "
                "in the environment."
            ),
        }

    drift_report_path = Path(args.drift_report).resolve()
    if not drift_report_path.exists():
        return {
            "_sentinel": "invalid_input",
            "message": f"--drift-report path does not exist: {args.drift_report}",
        }

    return {
        "repo_root": repo_root,
        "drift_report_path": drift_report_path,
        "github_token": token,
    }


def _runner(**kwargs: Any) -> SurfaceResult:
    sentinel = kwargs.get("_sentinel")
    if sentinel == "repo_root_missing":
        return repo_root_failure(
            surface=SURFACE,
            mode=MODE,
            approval=APPROVAL_NONE,
            path_rules=_path_rules(),
        )
    if sentinel == "approval_required":
        return approval_required_result(
            surface=SURFACE,
            mode=MODE,
            path_rules=_path_rules(),
            lock_required=True,
        )
    if sentinel == "invalid_input":
        return invalid_input_result(
            surface=SURFACE,
            mode=MODE,
            approval=APPROVAL_NONE,
            message=kwargs.get("message", "invalid input"),
            path_rules=_path_rules(),
        )
    return fetch_content(
        repo_root=kwargs["repo_root"],
        drift_report_path=kwargs["drift_report_path"],
        github_token=kwargs["github_token"],
    )


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    output_stream: Any = sys.stdout,
) -> int:
    return run_surface_cli(
        argv=argv,
        parser_factory=_build_parser,
        path_rules_factory=_path_rules,
        surface=SURFACE,
        runner=_runner,
        args_to_kwargs=_args_to_kwargs,
        output_stream=output_stream,
    )


if __name__ == "__main__":
    sys.exit(run_cli())
