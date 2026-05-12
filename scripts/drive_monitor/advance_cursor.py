"""Advance Changes API cursors after successful pipeline processing.

Terminal step in the Drive monitoring pipeline.  Reads the drift report
produced by ``check_drift.py``, verifies that all entries for each alias
completed without errors, and advances the Changes API cursor in the
source registry.

The cursor must only advance when ALL entries for an alias have been
durably handled.  At-least-once semantics are safe because asset writes
use ``exclusive_create_write_once()`` which is idempotent.

Usage::

    python -m scripts.drive_monitor.advance_cursor \\
        --drift-report drift-report.json \\
        --approval approved \\
        [--repo-root /path/to/repo]

Requires ``--approval approved`` for any write operation.
"""

from __future__ import annotations

import json
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
from scripts.kb.contracts import DriveMonitorReasonCode
from scripts.drive_monitor._registry import (
    find_registry_by_alias,
    update_changes_cursor,
)

SURFACE = "drive_monitor.advance_cursor"
MODE = "advance"


def _path_rules() -> dict[str, Any]:
    return base_path_rules(
        allowed_roots=["raw/drive-sources"],
        allowed_suffixes=[".json"],
    )


def advance_cursor(
    *,
    repo_root: Path,
    drift_report_path: Path,
    approval: str = APPROVAL_NONE,
) -> SurfaceResult:
    """Advance Changes API cursors for aliases with no pipeline errors.

    Reads the drift report's ``cursors`` dict and ``errors`` list.
    For each alias in ``cursors``, advances the registry cursor only if
    no errors exist for that alias.  Aliases with errors are skipped to
    preserve at-least-once semantics.

    Parameters
    ----------
    repo_root:
        Absolute path to the knowledgebase repository root.
    drift_report_path:
        Path to the drift report JSON (output of check_drift.py).
    approval:
        Must be ``"approved"`` for any writes to occur.
    """
    if approval != APPROVAL_APPROVED:
        return approval_required_result(
            surface=SURFACE, mode=MODE, path_rules=_path_rules(),
            lock_required=True,
        )

    if not looks_like_repo_root(repo_root):
        return repo_root_failure(
            surface=SURFACE, mode=MODE, approval=approval,
            path_rules=_path_rules(),
        )

    try:
        raw = drift_report_path.read_text(encoding="utf-8")
    except OSError as exc:
        return invalid_input_result(
            surface=SURFACE, mode=MODE, approval=approval,
            path_rules=_path_rules(),
            message=f"Cannot read drift report: {exc}",
        )

    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        return invalid_input_result(
            surface=SURFACE, mode=MODE, approval=approval,
            path_rules=_path_rules(),
            message=f"Malformed JSON: {exc}",
        )

    cursors = report.get("cursors", {})
    if not cursors:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_PASS,
            reason_code=str(DriveMonitorReasonCode.NO_DRIFT),
            message="No cursors to advance.",
            path_rules=_path_rules(),
        )

    # Build set of aliases that had errors in the drift report
    error_aliases: set[str] = set()
    for err in report.get("errors", []):
        a = err.get("alias")
        if a:
            error_aliases.add(a)

    advanced = 0
    skipped = 0
    advance_errors: list[str] = []

    for alias, new_token in cursors.items():
        if alias in error_aliases:
            print(
                f"WARNING: skipping cursor advance for {alias!r} "
                f"(errors in drift report)",
                file=sys.stderr,
            )
            skipped += 1
            continue

        registry_path = find_registry_by_alias(repo_root, alias)
        if not registry_path:
            advance_errors.append(
                f"No registry found for alias {alias!r}"
            )
            continue

        try:
            update_changes_cursor(repo_root, registry_path, new_token)
            advanced += 1
            print(f"Cursor advanced for {alias!r}", file=sys.stderr)
        except OSError as exc:
            advance_errors.append(
                f"Failed to advance cursor for {alias!r}: {exc}"
            )

    message = (
        f"Cursor advance: {advanced} advanced, {skipped} skipped, "
        f"{len(advance_errors)} errors"
    )
    print(message, file=sys.stderr)
    if advance_errors:
        for e in advance_errors:
            print(f"  ERROR: {e}", file=sys.stderr)

    status = STATUS_PASS if not advance_errors else STATUS_FAIL
    return SurfaceResult(
        surface=SURFACE,
        mode=MODE,
        status=status,
        reason_code=str(DriveMonitorReasonCode.NO_DRIFT),
        message=message,
        path_rules=_path_rules(),
        summary={
            "advanced": advanced,
            "skipped": skipped,
            "error_count": len(advance_errors),
        },
    )


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Advance Changes API cursors after successful pipeline processing."
    )
    parser.add_argument(
        "--drift-report",
        metavar="PATH",
        required=True,
        help="Path to the drift report JSON (output of check_drift.py).",
    )
    parser.add_argument(
        "--repo-root",
        metavar="PATH",
        default=".",
        help="Repository root directory (default: current directory).",
    )
    parser.add_argument(
        "--approval",
        metavar="APPROVAL",
        default=APPROVAL_NONE,
        help="Must be 'approved' to perform writes.",
    )
    return parser


def _args_to_kwargs(args: Any) -> dict[str, Any]:
    return {
        "repo_root": Path(args.repo_root).resolve(),
        "drift_report_path": Path(args.drift_report),
        "approval": args.approval,
    }


def _runner(**kwargs: Any) -> SurfaceResult:
    return advance_cursor(**kwargs)


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
