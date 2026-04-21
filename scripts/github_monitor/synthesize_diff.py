"""Generate diff-based change notes for drifted GitHub sources (Phase 3).

Reads the drift report produced by ``check_drift.py``, computes a unified
diff between the previously applied asset and the newly fetched asset for
each drifted entry, appends a dated ``## Change Note`` section to the
corresponding wiki page, and advances ``last_applied_*`` in the source
registry only after the wiki write is confirmed.

Lock ordering (ADR-012): acquires ``wiki/.kb_write.lock`` FIRST, then
``raw/.github-sources.lock`` inside that context.

Usage::

    python -m scripts.github_monitor.synthesize_diff \\
        --drift-report drift-report.json \\
        --approval approved \\
        [--repo-root /path/to/repo]

Requires ``--approval approved`` for any write operation.
"""

from __future__ import annotations

import contextlib
import difflib
import hashlib
import json
import sys
import tempfile
import os
from datetime import datetime, timezone
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
from scripts.kb.contracts import GitHubMonitorReasonCode, GITHUB_SOURCES_LOCK_PATH
from scripts.kb import write_utils
from scripts.github_monitor._registry import (
    find_registry_for,
    update_last_applied,
)
from scripts.github_monitor._types import (
    DriftedEntry,
    validate_drift_report,
)
from scripts.github_monitor._validators import validate_external_path

SURFACE = "github_monitor.synthesize_diff"
MODE = "synthesize"

# Files above this byte limit get a truncated diff notice.
_DIFF_SIZE_LIMIT = 100_000
# Maximum lines to include in the rendered diff before truncation.
_DIFF_MAX_LINES = 200


def _path_rules() -> dict[str, Any]:
    return base_path_rules(
        allowed_roots=["wiki", "raw/github-sources"],
        allowed_suffixes=[".md", ".json"],
    )


def _is_binary(data: bytes) -> bool:
    """Return True if *data* appears to be a non-text (binary) file."""
    return b"\x00" in data


def _render_diff(
    old_text: str,
    new_text: str,
    old_label: str,
    new_label: str,
) -> str:
    """Produce a unified diff string for embedding in a wiki change note."""
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{old_label}",
            tofile=f"b/{new_label}",
        )
    )
    if not diff_lines:
        return ""
    if len(diff_lines) > _DIFF_MAX_LINES:
        diff_lines = diff_lines[:_DIFF_MAX_LINES]
        diff_lines.append(
            f"\n... diff truncated at {_DIFF_MAX_LINES} lines "
            f"({len(diff_lines)} total) ...\n"
        )
    return "".join(diff_lines)


def _build_change_note(
    entry: DriftedEntry,
    diff_text: str,
    *,
    is_binary: bool = False,
    is_new: bool = False,
    now: datetime | None = None,
) -> str:
    """Build the ``## Change Note`` markdown block to append to the wiki page."""
    if now is None:
        now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    owner = entry["owner"]
    repo = entry["repo"]
    path = entry["path"]
    compare_url = entry.get("compare_url")

    compare_link = (
        f" ([compare on GitHub]({compare_url}))" if compare_url else ""
    )
    source_ref = f"`{owner}/{repo}/{path}`{compare_link}"

    lines: list[str] = [
        "",
        "---",
        "",
        f"## Change Note — {date_str}",
        "",
        f"**Source:** {source_ref}  ",
        f"**New blob SHA:** `{entry['current_blob_sha']}`  ",
        f"**Previous blob SHA:** `{entry.get('last_applied_blob_sha') or 'none (new)'}`",
        "",
    ]

    if is_binary:
        lines.append("*Binary file changed — no diff available.*")
    elif is_new:
        lines += [
            "~~~~diff",
            diff_text.rstrip("\n"),
            "~~~~",
        ]
    elif diff_text:
        lines += [
            "~~~~diff",
            diff_text.rstrip("\n"),
            "~~~~",
        ]
    else:
        lines.append("*Content is identical to previous version (metadata-only change).*")

    lines.append("")
    return "\n".join(lines)


def _synthesize_one(
    repo_root: Path,
    entry: DriftedEntry,
) -> tuple[bool, dict[str, Any]]:
    """Synthesize a change note for one drifted entry.

    Returns ``(success, result_info)`` where result_info contains fields
    for the SurfaceResult items list.

    Does NOT write to the wiki or registry — the caller handles those writes
    inside the correct lock context.
    """
    owner = entry["owner"]
    repo = entry["repo"]
    try:
        path = validate_external_path(entry["path"])
    except ValueError as exc:
        return False, {
            "path": entry.get("path", ""),
            "reason_code": str(GitHubMonitorReasonCode.FETCH_FAILED),
            "message": f"Path validation failed: {exc}",
        }

    last_applied_commit = entry.get("last_applied_commit_sha")
    current_commit = entry["current_commit_sha"]

    # New asset path (from fetch_content.py).
    new_asset = repo_root / "raw" / "assets" / owner / repo / current_commit / path
    if not new_asset.exists():
        return False, {
            "path": path,
            "reason_code": str(GitHubMonitorReasonCode.FETCH_FAILED),
            "message": (
                f"New asset not found at {new_asset.relative_to(repo_root)}; "
                "run fetch_content.py first"
            ),
        }

    new_bytes = new_asset.read_bytes()

    if _is_binary(new_bytes):
        return True, {
            "path": path,
            "note_type": "binary",
            "new_bytes": None,
            "diff_text": "",
            "is_binary": True,
            "is_new": False,
        }

    new_text = new_bytes.decode("utf-8", errors="replace")

    # Old asset path (from last applied version).
    if last_applied_commit:
        old_asset = (
            repo_root / "raw" / "assets" / owner / repo / last_applied_commit / path
        )
        if old_asset.exists():
            old_text = old_asset.read_bytes().decode("utf-8", errors="replace")
        else:
            old_text = ""
    else:
        old_text = ""

    diff_text = _render_diff(
        old_text,
        new_text,
        old_label=path,
        new_label=path,
    )

    return True, {
        "path": path,
        "note_type": "text",
        "new_bytes": new_bytes,
        "diff_text": diff_text,
        "is_binary": False,
        "is_new": not bool(last_applied_commit),
    }


def synthesize_diff(
    *,
    repo_root: Path,
    drift_report_path: Path,
) -> SurfaceResult:
    """Core logic: synthesize change notes for all drifted entries."""
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
            message="No drifted entries in drift report; nothing to synthesize.",
            approval=APPROVAL_APPROVED,
            summary={"synthesized_count": 0, "error_count": 0},
        )

    synthesized: list[str] = []
    errors: list[dict[str, Any]] = []

    # Acquire wiki write lock first (ADR-012 lock ordering).
    try:
        wiki_lock_ctx = write_utils.exclusive_write_lock(repo_root)
        wiki_lock_ctx.__enter__()
    except write_utils.LockUnavailableError as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_FAIL,
            reason_code="lock_unavailable",
            message=str(exc),
            approval=APPROVAL_APPROVED,
            path_rules=_path_rules(),
        )

    now = datetime.now(timezone.utc)

    try:
        for entry in drifted:
            owner = entry["owner"]
            repo = entry["repo"]
            path = entry["path"]

            # Find registry file.
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

            # Check that fetch_content.py has run: last_fetched_blob_sha must match.
            try:
                raw_registry = json.loads(registry_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(
                    {
                        "path": path,
                        "reason_code": str(GitHubMonitorReasonCode.FETCH_FAILED),
                        "message": f"Failed to read registry: {exc}",
                    }
                )
                continue

            reg_entry = next(
                (e for e in raw_registry.get("entries", []) if e.get("path") == path),
                None,
            )
            if reg_entry is None:
                errors.append(
                    {
                        "path": path,
                        "reason_code": str(GitHubMonitorReasonCode.FETCH_FAILED),
                        "message": f"Entry {path!r} not found in registry",
                    }
                )
                continue

            if reg_entry.get("last_fetched_blob_sha") != entry["current_blob_sha"]:
                errors.append(
                    {
                        "path": path,
                        "reason_code": str(GitHubMonitorReasonCode.FETCH_FAILED),
                        "message": (
                            f"last_fetched_blob_sha in registry does not match "
                            f"drift report current_blob_sha; run fetch_content.py first"
                        ),
                    }
                )
                continue

            # Find the wiki page.
            wiki_page_rel = reg_entry.get("wiki_page")
            if not wiki_page_rel:
                errors.append(
                    {
                        "path": path,
                        "reason_code": str(GitHubMonitorReasonCode.UNINITIALIZED_SOURCE),
                        "message": (
                            f"Registry entry for {path!r} has no wiki_page set; "
                            "complete initial ingest first"
                        ),
                    }
                )
                continue

            wiki_page_path = repo_root / wiki_page_rel
            if not wiki_page_path.exists():
                errors.append(
                    {
                        "path": path,
                        "reason_code": str(GitHubMonitorReasonCode.FETCH_FAILED),
                        "message": (
                            f"Wiki page not found: {wiki_page_rel}"
                        ),
                    }
                )
                continue

            # Build the change note.
            ok, info = _synthesize_one(repo_root, entry)
            if not ok:
                errors.append(
                    {
                        "path": info["path"],
                        "status": STATUS_FAIL,
                        "reason_code": info["reason_code"],
                        "message": info["message"],
                    }
                )
                continue

            change_note = _build_change_note(
                entry,
                info["diff_text"],
                is_binary=info["is_binary"],
                is_new=info["is_new"],
                now=now,
            )

            # Write the change note to the wiki page (atomic temp file).
            existing_content = wiki_page_path.read_text(encoding="utf-8")
            new_content = existing_content.rstrip("\n") + "\n" + change_note

            fd, tmp_str = tempfile.mkstemp(
                dir=wiki_page_path.parent, prefix=f".{wiki_page_path.name}."
            )
            tmp = Path(tmp_str)
            try:
                try:
                    os.write(fd, new_content.encode("utf-8"))
                finally:
                    os.close(fd)
                os.replace(tmp, wiki_page_path)
            except OSError as exc:
                with contextlib.suppress(OSError):
                    tmp.unlink()
                errors.append(
                    {
                        "path": path,
                        "reason_code": str(GitHubMonitorReasonCode.FETCH_FAILED),
                        "message": f"Failed to write wiki page: {exc}",
                    }
                )
                continue

            # Advance last_applied_* in the registry (under registry lock, inside wiki lock).
            new_bytes = info.get("new_bytes") or (
                wiki_page_path.read_bytes() if info["is_binary"] else
                (repo_root / "raw" / "assets" / owner / repo
                 / entry["current_commit_sha"] / path).read_bytes()
            )
            sha256_hex = hashlib.sha256(new_bytes).hexdigest()

            try:
                update_last_applied(
                    repo_root,
                    registry_path,
                    path,
                    commit_sha=entry["current_commit_sha"],
                    blob_sha=entry["current_blob_sha"],
                    sha256=sha256_hex,
                    applied_at=now.isoformat(),
                )
            except OSError as exc:
                errors.append(
                    {
                        "path": path,
                        "reason_code": str(GitHubMonitorReasonCode.REGISTRY_LOCKED),
                        "message": f"Registry update failed after wiki write: {exc}",
                    }
                )
                # Note: wiki page was already written but registry wasn't updated.
                # The next run will re-synthesize this entry (idempotent change note append).
                continue

            synthesized.append(path)

    finally:
        wiki_lock_ctx.__exit__(None, None, None)

    status = STATUS_PASS if not errors else STATUS_FAIL
    reason_code = (
        str(GitHubMonitorReasonCode.FETCH_FAILED)
        if errors
        else str(GitHubMonitorReasonCode.DRIFT_DETECTED)
        if synthesized
        else str(GitHubMonitorReasonCode.NO_DRIFT)
    )
    message = (
        f"synthesis complete: {len(synthesized)} synthesized, {len(errors)} errors"
    )

    return SurfaceResult(
        surface=SURFACE,
        mode=MODE,
        status=status,
        reason_code=reason_code,
        message=message,
        approval=APPROVAL_APPROVED,
        summary={
            "synthesized_count": len(synthesized),
            "error_count": len(errors),
            "synthesized_paths": synthesized,
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
        description="Synthesize diff-based change notes for drifted GitHub sources."
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

    drift_report_path = Path(args.drift_report).resolve()
    if not drift_report_path.exists():
        return {
            "_sentinel": "invalid_input",
            "message": f"--drift-report path does not exist: {args.drift_report}",
        }

    return {
        "repo_root": repo_root,
        "drift_report_path": drift_report_path,
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
    return synthesize_diff(
        repo_root=kwargs["repo_root"],
        drift_report_path=kwargs["drift_report_path"],
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
