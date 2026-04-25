"""Persist a rejection record to ``raw/rejected/`` under lock.

Usage::

    python -m scripts.kb.log_rejection \\
        --repo-root . \\
        --approval approved \\
        --slug cms-manual-chapter-4 \\
        --sha256 <64-hex> \\
        --rejected-date 2025-07-16T14:30:00Z \\
        --source-path raw/inbox/some-document.pdf \\
        --rejection-reason "Missing provenance metadata" \\
        --rejection-category provenance_missing \\
        --reviewed-by operator

This script is the **only** authorized writer of
``raw/rejected/*.rejection.md`` per the ``schema/rejection-registry-contract.md``
and ``AGENTS.md`` write-surface matrix.

Implements:
- Slug + sha256 + category validation (``rejection_validators.py``)
- Write-once semantics (fail if file already exists)
- sha256 deduplication (scan existing records)
- ``raw/.rejection-registry.lock`` acquisition (ADR-005 semantics)
- Symlink path checks (``write_utils.check_no_symlink_path``)
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from scripts._optional_surface_common import (
    APPROVAL_APPROVED,
    STATUS_FAIL,
    STATUS_PASS,
    JsonArgumentParser,
    SurfaceResult,
    base_path_rules,
    run_surface_cli,
)
from scripts.kb import contracts, write_utils
from scripts.kb.rejection_validators import (
    validate_category,
    validate_filename,
    validate_sha256,
    validate_slug,
)

SURFACE = "skill.log-intake-rejection"
MODE = "write"

_REJECTED_DIR = Path("raw/rejected")


def _path_rules() -> dict[str, Any]:
    return base_path_rules(
        allowed_roots=["raw/rejected"],
        allowed_suffixes=[".rejection.md"],
    )


def _scan_existing_sha256(rejected_dir: Path) -> set[str]:
    """Scan existing rejection records and collect their sha256 values."""
    sha256s: set[str] = set()
    if not rejected_dir.is_dir():
        return sha256s
    for f in rejected_dir.glob("*.rejection.md"):
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("sha256:"):
                sha256s.add(stripped[len("sha256:"):].strip())
                break
    return sha256s


def log_rejection(
    *,
    repo_root: Path,
    slug: str,
    sha256: str,
    rejected_date: str,
    source_path: str,
    rejection_reason: str,
    rejection_category: str,
    reviewed_by: str,
) -> SurfaceResult:
    """Write a rejection record to ``raw/rejected/``.

    Returns a ``SurfaceResult`` indicating success or failure.
    """
    # --- field validation ---------------------------------------------------
    all_errors: list[str] = []
    all_errors.extend(validate_slug(slug))
    all_errors.extend(validate_sha256(sha256))
    all_errors.extend(validate_category(rejection_category))

    filename = f"{slug}--{sha256[:8]}.rejection.md"
    all_errors.extend(validate_filename(filename))

    if all_errors:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_FAIL,
            reason_code="invalid_input",
            message=f"Validation failed: {'; '.join(all_errors)}",
            path_rules=_path_rules(),
        )

    rejected_dir = repo_root / _REJECTED_DIR
    target = rejected_dir / filename

    # --- symlink check ------------------------------------------------------
    try:
        write_utils.check_no_symlink_path(target)
    except OSError as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_FAIL,
            reason_code="symlink_detected",
            message=str(exc),
            path_rules=_path_rules(),
        )

    # --- deduplication by sha256 --------------------------------------------
    existing = _scan_existing_sha256(rejected_dir)
    if sha256 in existing:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_FAIL,
            reason_code="duplicate_sha256",
            message=f"A rejection record with sha256 {sha256[:16]}… already exists.",
            path_rules=_path_rules(),
        )

    # --- write-once check ---------------------------------------------------
    if target.exists():
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_FAIL,
            reason_code="record_exists",
            message=f"Rejection record already exists: {target}",
            path_rules=_path_rules(),
        )

    # --- compose record -----------------------------------------------------
    record = (
        f"---\n"
        f"slug: {slug}\n"
        f"sha256: {sha256}\n"
        f"rejected_date: {rejected_date}\n"
        f"source_path: {source_path}\n"
        f"rejection_reason: {rejection_reason}\n"
        f"rejection_category: {rejection_category}\n"
        f"reviewed_by: {reviewed_by}\n"
        f"reconsidered_date: null\n"
        f"---\n\n"
        f"# {slug}\n\n"
        f"## What was attempted\n\n"
        f"Source `{source_path}` was submitted for intake.\n\n"
        f"## What was missing\n\n"
        f"{rejection_reason}\n\n"
        f"## Notes\n\n"
        f"Rejected by {reviewed_by} on {rejected_date}.\n"
    )

    # --- acquire lock and write ---------------------------------------------
    try:
        with write_utils.exclusive_write_lock(
            repo_root,
            lock_path=contracts.REJECTION_REGISTRY_LOCK_PATH,
        ):
            rejected_dir.mkdir(parents=True, exist_ok=True)
            write_utils.check_no_symlink_path(target)
            if target.exists():
                return SurfaceResult(
                    surface=SURFACE,
                    mode=MODE,
                    status=STATUS_FAIL,
                    reason_code="record_exists",
                    message=f"Record appeared during lock: {target}",
                    path_rules=_path_rules(),
                )
            target.write_text(record, encoding="utf-8")
    except write_utils.LockUnavailableError:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_FAIL,
            reason_code="lock_unavailable",
            message=f"Cannot acquire {contracts.REJECTION_REGISTRY_LOCK_PATH}",
            path_rules=_path_rules(),
        )
    except OSError as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_FAIL,
            reason_code="write_error",
            message=f"Write failed: {exc}",
            path_rules=_path_rules(),
        )

    return SurfaceResult(
        surface=SURFACE,
        mode=MODE,
        status=STATUS_PASS,
        reason_code="ok",
        message=f"Rejection record written: {target.relative_to(repo_root)}",
        path_rules=_path_rules(),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Log a rejected source to raw/rejected/."
    )
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    parser.add_argument("--approval", default="none",
                        help="Approval gate (must be 'approved').")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--rejected-date", required=True)
    parser.add_argument("--source-path", required=True)
    parser.add_argument("--rejection-reason", required=True)
    parser.add_argument("--rejection-category", required=True)
    parser.add_argument("--reviewed-by", required=True)
    return parser


def _args_to_kwargs(args: Any) -> dict[str, Any]:
    return {
        "repo_root": Path(args.repo_root),
        "slug": args.slug,
        "sha256": args.sha256,
        "rejected_date": args.rejected_date,
        "source_path": args.source_path,
        "rejection_reason": args.rejection_reason,
        "rejection_category": args.rejection_category,
        "reviewed_by": args.reviewed_by,
    }


def _runner(**kwargs: Any) -> SurfaceResult:
    return log_rejection(**kwargs)


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
