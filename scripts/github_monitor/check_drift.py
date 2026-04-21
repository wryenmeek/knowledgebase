"""Drift detection for monitored GitHub sources (Phase 1 — read-only).

Reads every active entry from ``*.source-registry.json`` files under
``raw/github-sources/``, queries the GitHub contents API for the current
blob SHA of each tracked file, and compares that SHA against
``last_applied_blob_sha`` from the registry.

Produces a structured drift report (``--output drift-report.json``) that the
Phase 2 write job consumes.  The surface itself performs **no repository
writes** — it is read-only.

Usage::

    python -m scripts.github_monitor.check_drift \\
        [--registry raw/github-sources/org-repo.source-registry.json] \\
        [--repo-root /path/to/repo] \\
        [--output drift-report.json]

Authentication:
    Set ``GITHUB_APP_TOKEN`` (preferred) or ``GITHUB_TOKEN`` in the
    environment.  The token is never accepted as a CLI argument because that
    would expose it in ``ps aux`` and CI logs.
"""

from __future__ import annotations

import glob as glob_module
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from scripts._optional_surface_common import (
    STATUS_FAIL,
    STATUS_PASS,
    JsonArgumentParser,
    SurfaceResult,
    base_path_rules,
    invalid_input_result,
    looks_like_repo_root,
    repo_root_failure,
    run_surface_cli,
)
from scripts.kb.contracts import GitHubMonitorReasonCode
from scripts.github_monitor._types import (
    DRIFT_REPORT_VERSION,
    DriftedEntry,
    ErrorEntry,
    UninitializedEntry,
    UpToDateEntry,
    GitHubAPIRequestError,
    GitHubAPIResponseError,
    validate_contents_response,
    validate_commits_response,
    validate_registry_file,
)
from scripts.github_monitor._validators import validate_external_path

SURFACE = "github_monitor.check_drift"
MODE = "check"

_GITHUB_API_BASE = "https://api.github.com"
_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = (1.0, 2.0, 4.0)


def _path_rules() -> dict[str, Any]:
    return base_path_rules(
        allowed_roots=["raw/github-sources"],
        allowed_suffixes=[".json"],
    )


def _get_github_token() -> str | None:
    return os.environ.get("GITHUB_APP_TOKEN") or os.environ.get("GITHUB_TOKEN")


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
                delay = float(retry_after) if retry_after else _RETRY_DELAY_SECONDS[attempt]
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


def _check_active_entry(
    entry: dict[str, Any],
    owner: str,
    repo: str,
    token: str,
) -> tuple[str, dict[str, Any]]:
    """Check one active registry entry against the GitHub API.

    Returns ``(category, data)`` where ``category`` is one of
    ``"drifted"``, ``"up_to_date"``, or ``"errors"``.
    """
    raw_path = entry.get("path", "")
    try:
        validated_path = validate_external_path(raw_path)
    except ValueError as exc:
        return "errors", ErrorEntry(
            path=raw_path,
            reason_code=str(GitHubMonitorReasonCode.FETCH_FAILED),
            message=f"Path validation failed: {exc}",
        )

    contents_url = (
        f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{validated_path}"
    )
    try:
        raw_contents = _make_github_request(contents_url, token)
        contents = validate_contents_response(raw_contents)
    except (GitHubAPIRequestError, GitHubAPIResponseError) as exc:
        reason = (
            GitHubMonitorReasonCode.UNREACHABLE
            if isinstance(exc, GitHubAPIRequestError)
            and exc.status_code in (401, 403, 404)
            else GitHubMonitorReasonCode.FETCH_FAILED
        )
        return "errors", ErrorEntry(
            path=validated_path,
            reason_code=str(reason),
            message=str(exc),
        )

    current_blob_sha: str = contents["sha"]

    # Fetch the most recent commit SHA for this file to populate compare_url.
    commits_url = (
        f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/commits"
        f"?path={validated_path}&per_page=1"
    )
    try:
        raw_commits = _make_github_request(commits_url, token)
        commits = validate_commits_response(raw_commits)
        current_commit_sha: str = commits[0]["sha"]
    except (GitHubAPIRequestError, GitHubAPIResponseError) as exc:
        return "errors", ErrorEntry(
            path=validated_path,
            reason_code=str(GitHubMonitorReasonCode.FETCH_FAILED),
            message=f"Failed to get commit SHA: {exc}",
        )

    last_applied_blob_sha: str | None = entry.get("last_applied_blob_sha")
    last_applied_commit_sha: str | None = entry.get("last_applied_commit_sha")

    # Defensive: active entry with no last_applied_blob_sha is misconfigured.
    if last_applied_blob_sha is None:
        return "errors", ErrorEntry(
            path=validated_path,
            reason_code=str(GitHubMonitorReasonCode.FETCH_FAILED),
            message=(
                "Active registry entry has null last_applied_blob_sha; "
                "set tracking_status to 'uninitialized' or complete initial ingest"
            ),
        )

    if current_blob_sha == last_applied_blob_sha:
        return "up_to_date", UpToDateEntry(
            owner=owner,
            repo=repo,
            path=validated_path,
            blob_sha=current_blob_sha,
        )

    compare_url: str | None = None
    if last_applied_commit_sha:
        compare_url = (
            f"https://github.com/{owner}/{repo}/compare/"
            f"{last_applied_commit_sha[:7]}...{current_commit_sha[:7]}"
        )
    return "drifted", DriftedEntry(
        owner=owner,
        repo=repo,
        path=validated_path,
        current_commit_sha=current_commit_sha,
        current_blob_sha=current_blob_sha,
        last_applied_commit_sha=last_applied_commit_sha,
        last_applied_blob_sha=last_applied_blob_sha,
        compare_url=compare_url,
    )


def check_drift(
    *,
    repo_root: Path,
    registry_paths: Sequence[Path],
    github_token: str,
    output_path: Path | None,
) -> SurfaceResult:
    """Run drift detection across all provided registry files.

    This is the core runner invoked by ``run_surface_cli``.  It is
    intentionally side-effect-free except for writing the optional
    ``output_path`` JSON file (an untracked CI artifact, not a governed
    repository write).
    """
    drifted: list[DriftedEntry] = []
    up_to_date: list[UpToDateEntry] = []
    uninitialized: list[UninitializedEntry] = []
    errors: list[ErrorEntry] = []

    for registry_path in registry_paths:
        try:
            raw = json.loads(registry_path.read_text(encoding="utf-8"))
            registry = validate_registry_file(raw)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(
                ErrorEntry(
                    path=str(registry_path.relative_to(repo_root)),
                    reason_code=str(GitHubMonitorReasonCode.FETCH_FAILED),
                    message=f"Registry read/validation error: {exc}",
                )
            )
            continue

        owner: str = registry["owner"]
        repo: str = registry["repo"]
        registry_rel = str(registry_path.relative_to(repo_root))

        for entry in registry.get("entries", []):
            status = entry.get("tracking_status", "")

            if status == "uninitialized":
                uninitialized.append(
                    UninitializedEntry(
                        owner=owner,
                        repo=repo,
                        path=entry.get("path", ""),
                        tracking_status="uninitialized",
                    )
                )
                continue

            if status in ("paused", "archived", "unreachable"):
                continue

            if status != "active":
                errors.append(
                    ErrorEntry(
                        path=entry.get("path", ""),
                        reason_code=str(GitHubMonitorReasonCode.FETCH_FAILED),
                        message=f"Unknown tracking_status {status!r} in {registry_rel}",
                    )
                )
                continue

            category, entry_data = _check_active_entry(entry, owner, repo, github_token)
            if category == "drifted":
                drifted.append(entry_data)  # type: ignore[arg-type]
            elif category == "up_to_date":
                up_to_date.append(entry_data)  # type: ignore[arg-type]
            else:
                errors.append(entry_data)  # type: ignore[arg-type]

    has_drift = len(drifted) > 0

    report = {
        "version": DRIFT_REPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry": (
            str(registry_paths[0].relative_to(repo_root))
            if len(registry_paths) == 1
            else f"raw/github-sources/*.source-registry.json ({len(registry_paths)} files)"
        ),
        "has_drift": has_drift,
        "drifted": drifted,
        "up_to_date": up_to_date,
        "uninitialized": uninitialized,
        "errors": errors,
    }

    report_json = json.dumps(report, indent=2, default=str)
    if output_path is not None:
        output_path.write_text(report_json, encoding="utf-8")

    status = STATUS_PASS if not errors else STATUS_FAIL
    reason_code = (
        str(GitHubMonitorReasonCode.FETCH_FAILED)
        if errors
        else (
            str(GitHubMonitorReasonCode.DRIFT_DETECTED)
            if has_drift
            else str(GitHubMonitorReasonCode.NO_DRIFT)
        )
    )
    message = (
        f"drift check complete: {len(drifted)} drifted, "
        f"{len(up_to_date)} up_to_date, "
        f"{len(uninitialized)} uninitialized, "
        f"{len(errors)} errors"
    )

    return SurfaceResult(
        surface=SURFACE,
        mode=MODE,
        status=status,
        reason_code=reason_code,
        message=message,
        summary={
            "has_drift": has_drift,
            "drifted_count": len(drifted),
            "up_to_date_count": len(up_to_date),
            "uninitialized_count": len(uninitialized),
            "error_count": len(errors),
            "output_path": str(output_path) if output_path else None,
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
        description="Detect drift in monitored GitHub source files."
    )
    parser.add_argument(
        "--registry",
        metavar="PATH",
        help=(
            "Path to a specific registry file.  If omitted and --registry-glob is "
            "not given, defaults to raw/github-sources/*.source-registry.json."
        ),
    )
    parser.add_argument(
        "--registry-glob",
        metavar="GLOB",
        help="Glob pattern for registry files (relative to repo root).",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="Write the drift report JSON to this file (default: write to stdout).",
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

    # Resolve registry files.
    registry_paths: list[Path] = []
    if args.registry:
        p = (repo_root / args.registry).resolve()
        if not p.is_relative_to(repo_root):
            return {
                "_sentinel": "invalid_input",
                "message": f"--registry path escapes repository root: {args.registry}",
            }
        if not p.exists():
            return {
                "_sentinel": "invalid_input",
                "message": f"--registry path does not exist: {args.registry}",
            }
        registry_paths.append(p)
    else:
        pattern = args.registry_glob or "raw/github-sources/*.source-registry.json"
        matched = sorted(
            Path(m).resolve()
            for m in glob_module.glob(str(repo_root / pattern))
            if Path(m).is_file()
        )
        for m in matched:
            if not m.is_relative_to(repo_root):
                return {
                    "_sentinel": "invalid_input",
                    "message": f"Matched registry path escapes repository root: {m}",
                }
        registry_paths = matched

    if not registry_paths:
        return {
            "_sentinel": "invalid_input",
            "message": (
                "No registry files found. Create a *.source-registry.json file "
                "under raw/github-sources/ to begin monitoring."
            ),
        }

    token = _get_github_token()
    if not token:
        return {
            "_sentinel": "invalid_input",
            "message": (
                "No GitHub token found. Set GITHUB_APP_TOKEN or GITHUB_TOKEN "
                "in the environment."
            ),
        }

    output_path: Path | None = None
    if args.output:
        output_path = Path(args.output).resolve()

    return {
        "repo_root": repo_root,
        "registry_paths": registry_paths,
        "github_token": token,
        "output_path": output_path,
    }


def _runner(**kwargs: Any) -> SurfaceResult:
    sentinel = kwargs.get("_sentinel")
    if sentinel == "repo_root_missing":
        return repo_root_failure(
            surface=SURFACE,
            mode=MODE,
            approval="none",
            path_rules=_path_rules(),
        )
    if sentinel == "invalid_input":
        return invalid_input_result(
            surface=SURFACE,
            mode=MODE,
            approval="none",
            message=kwargs.get("message", "invalid input"),
            path_rules=_path_rules(),
        )
    return check_drift(
        repo_root=kwargs["repo_root"],
        registry_paths=kwargs["registry_paths"],
        github_token=kwargs["github_token"],
        output_path=kwargs["output_path"],
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
