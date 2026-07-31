"""Batch policy-gated persistence for high-value query outputs.

Handles N queries in one governed operation: validates each entry, acquires
the wiki write lock (wiki/.kb_write.lock, ADR-005) once for the entire
batch, writes all policy-passing entries to wiki/analyses/**, regenerates
wiki/index.md once after all entries, and appends a single batch summary
entry to wiki/log.md.

Supported modes: apply (SUPPORTED_MODES = ("apply",)).

Writable paths: wiki/analyses/** (write-once per query fingerprint),
wiki/index.md (regenerated once), wiki/log.md (single append-only summary).

Maximum batch size: MAX_BATCH_SIZE = 100 entries per run.

Fail-closed invariants:
  - --batch-file must resolve within the repository boundary.
  - Malformed or missing batch JSON → hard fail, no lock acquired.
  - Batch size > MAX_BATCH_SIZE → hard fail, no lock acquired.
  - Lock unavailable → all pre-validated entries marked failed; top-level
    status = fail.
  - Per-entry policy rejection → status = skipped; not a top-level failure.
  - Per-entry OSError → that entry is rolled back and marked failed;
    remaining entries continue.
  - Index update failure after writes is logged as a warning (intentional
    divergence from persist_query.py rollback — see inline comment).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Sequence, TextIO

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.kb import contracts, update_index, write_utils
from scripts.kb.persist_query import (
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_MIN_SOURCES,
    DEFAULT_UPDATED_AT,
    PersistQueryInputError,
    PersistRequest,
    _analysis_relative_path,
    _evaluate_policy,
    _render_analysis_markdown,
    _validate_request,
)
from scripts.kb.write_utils import (
    append_log_only_state_changes,
    rollback_file_state,
    write_text_capturing_previous_safe,
)

SURFACE = "scripts/kb/batch_persist_query.py"
SUPPORTED_MODES = ("apply",)
MAX_BATCH_SIZE: int = 100

__all__ = ["SURFACE", "SUPPORTED_MODES", "MAX_BATCH_SIZE", "run_batch_cli", "main"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Batch policy-gated query persistence: handles N queries in one "
            "governed operation with a single lock acquisition."
        ),
    )
    parser.add_argument(
        "--batch-file",
        required=True,
        help="Path to batch JSON file (array of entry objects).",
    )
    parser.add_argument(
        "--wiki-root",
        default="wiki",
        help="Wiki root directory (must resolve to repository wiki/).",
    )
    parser.add_argument(
        "--schema",
        default="AGENTS.md",
        help="Schema/contract file path for validation.",
    )
    parser.add_argument(
        "--result-json",
        action="store_true",
        help="Compatibility flag; JSON envelope is emitted for all runs.",
    )
    parser.add_argument(
        "--min-confidence",
        type=int,
        default=DEFAULT_MIN_CONFIDENCE,
        help=f"Minimum confidence threshold applied to all entries (default: {DEFAULT_MIN_CONFIDENCE}).",
    )
    parser.add_argument(
        "--min-sources",
        type=int,
        default=DEFAULT_MIN_SOURCES,
        help=f"Minimum source count threshold applied to all entries (default: {DEFAULT_MIN_SOURCES}).",
    )
    parser.add_argument(
        "--updated-at",
        default=DEFAULT_UPDATED_AT,
        help=f"Deterministic updated_at timestamp (default: {DEFAULT_UPDATED_AT}).",
    )
    return parser


def _entry_namespace(
    entry: dict[str, Any],
    *,
    wiki_root: str,
    schema: str,
    min_confidence: int,
    min_sources: int,
    updated_at: str,
) -> SimpleNamespace:
    """Build an argparse.Namespace-compatible object from a batch JSON entry."""
    return SimpleNamespace(
        query=entry.get("query", ""),
        result_summary=entry.get("result_summary", ""),
        source=list(entry.get("sources", [])),
        confidence=entry.get("confidence", 0),
        unresolved_contradiction=bool(entry.get("unresolved_contradiction", False)),
        wiki_root=wiki_root,
        schema=schema,
        min_confidence=min_confidence,
        min_sources=min_sources,
        require_no_contradiction=True,
        updated_at=updated_at,
        sensitivity=entry.get("sensitivity", "internal"),
    )


def _entry_result(
    query: str,
    *,
    status: str,
    reason_code: str,
    analysis_path: str | None = None,
) -> dict[str, Any]:
    return {
        "query": query,
        "status": status,
        "reason_code": reason_code,
        "analysis_path": analysis_path,
    }


def _build_batch_log_entry(n_written: int, written_paths: list[str]) -> str:
    """Build a single batch summary log entry for wiki/log.md."""
    if n_written == 0:
        return "- batch_persist_query: 0 written"
    paths_sample = written_paths[:5]
    suffix = f", ... ({n_written - 5} more)" if n_written > 5 else ""
    return f"- batch_persist_query: {n_written} written — {', '.join(paths_sample)}{suffix}"


def _emit_fail(
    *,
    output_stream: TextIO,
    reason_code: str,
    total: int,
    entries: list[dict[str, Any]],
) -> None:
    """Write a top-level failure envelope and return."""
    n_failed = sum(1 for e in entries if e is not None and e.get("status") == "failed")
    n_skipped = sum(
        1 for e in entries if e is not None and e.get("status") == "skipped"
    )
    n_written = sum(
        1 for e in entries if e is not None and e.get("status") == "written"
    )
    envelope = {
        "status": "fail",
        "surface": SURFACE,
        "mode": "apply",
        "reason_code": reason_code,
        "total": total,
        "written": n_written,
        "skipped": n_skipped,
        "failed": n_failed,
        "entries": [e for e in entries if e is not None],
    }
    output_stream.write(json.dumps(envelope, sort_keys=True))
    output_stream.write("\n")


# ---------------------------------------------------------------------------
# Core batch execution
# ---------------------------------------------------------------------------


def _execute_batch(
    args: argparse.Namespace,
    repo_root: Path,
    *,
    output_stream: TextIO,
    error_stream: TextIO,
) -> int:
    """Execute the full batch operation and emit a JSON envelope.

    Returns the exit code (0 for pass, 1 for hard failure).
    """
    # ------------------------------------------------------------------ #
    # 1. Resolve and load batch file                                       #
    # ------------------------------------------------------------------ #
    batch_file = Path(args.batch_file)
    if not batch_file.is_absolute():
        batch_file = repo_root / batch_file
    batch_file = batch_file.resolve()
    if not batch_file.is_relative_to(repo_root):
        _emit_fail(
            output_stream=output_stream,
            reason_code=contracts.ReasonCode.INVALID_INPUT.value,
            total=0,
            entries=[],
        )
        error_stream.write(
            f"error: --batch-file must resolve within the repository boundary: {args.batch_file}\n"
        )
        return 1

    if not batch_file.exists():
        _emit_fail(
            output_stream=output_stream,
            reason_code=contracts.ReasonCode.INVALID_INPUT.value,
            total=0,
            entries=[],
        )
        error_stream.write(f"error: batch file does not exist: {batch_file}\n")
        return 1

    try:
        raw_text = batch_file.read_text(encoding="utf-8")
        batch: Any = json.loads(raw_text)
    except (json.JSONDecodeError, OSError) as exc:
        _emit_fail(
            output_stream=output_stream,
            reason_code=contracts.ReasonCode.INVALID_INPUT.value,
            total=0,
            entries=[],
        )
        error_stream.write(f"error: failed to load batch file: {exc}\n")
        return 1

    if not isinstance(batch, list):
        _emit_fail(
            output_stream=output_stream,
            reason_code=contracts.ReasonCode.INVALID_INPUT.value,
            total=0,
            entries=[],
        )
        error_stream.write("error: batch JSON must be a list/array\n")
        return 1

    total = len(batch)
    if total > MAX_BATCH_SIZE:
        _emit_fail(
            output_stream=output_stream,
            reason_code=contracts.ReasonCode.INVALID_INPUT.value,
            total=total,
            entries=[],
        )
        error_stream.write(
            f"error: batch size {total} exceeds maximum {MAX_BATCH_SIZE}\n"
        )
        return 1

    # ------------------------------------------------------------------ #
    # 2. Empty batch — succeed immediately without touching the lock       #
    # ------------------------------------------------------------------ #
    if total == 0:
        envelope = {
            "status": "pass",
            "surface": SURFACE,
            "mode": "apply",
            "reason_code": contracts.ReasonCode.OK.value,
            "total": 0,
            "written": 0,
            "skipped": 0,
            "failed": 0,
            "entries": [],
        }
        output_stream.write(json.dumps(envelope, sort_keys=True))
        output_stream.write("\n")
        return 0

    # ------------------------------------------------------------------ #
    # 3. Pre-validate all entries (before acquiring the lock)              #
    # ------------------------------------------------------------------ #
    # entry_results[i] = None until the entry is processed.
    entry_results: list[dict[str, Any] | None] = [None] * total
    validated: list[tuple[int, PersistRequest]] = []

    for i, raw_entry in enumerate(batch):
        query_text = raw_entry.get("query", "") if isinstance(raw_entry, dict) else ""
        if not isinstance(raw_entry, dict):
            entry_results[i] = _entry_result(
                query_text,
                status="failed",
                reason_code=contracts.ReasonCode.INVALID_INPUT.value,
            )
            continue

        ns = _entry_namespace(
            raw_entry,
            wiki_root=args.wiki_root,
            schema=args.schema,
            min_confidence=args.min_confidence,
            min_sources=args.min_sources,
            updated_at=args.updated_at,
        )
        try:
            request = _validate_request(ns, repo_root)
            validated.append((i, request))
        except PersistQueryInputError as exc:
            error_stream.write(f"error: entry {i} validation failed: {exc}\n")
            entry_results[i] = _entry_result(
                query_text,
                status="failed",
                reason_code=contracts.ReasonCode.INVALID_INPUT.value,
            )

    # ------------------------------------------------------------------ #
    # 4. Acquire write lock ONCE for the entire batch                      #
    # ------------------------------------------------------------------ #
    # Determine wiki_root from the first validated request (they all share it).
    if validated:
        wiki_root_path = validated[0][1].wiki_root
    else:
        # All entries failed pre-validation — equivalent to an invalid batch (no work can
        # proceed). This is distinct from per-entry policy rejection (which is a skip, not a
        # hard failure). Emit fail so callers/CI don't silently treat total failure as success.
        _emit_fail(
            output_stream=output_stream,
            reason_code=contracts.ReasonCode.INVALID_INPUT.value,
            total=total,
            entries=[e for e in entry_results if e is not None],
        )
        return 1

    written_paths: list[str] = []

    try:
        with write_utils.exclusive_write_lock(repo_root):
            # -------------------------------------------------------------- #
            # 5. Process each validated entry within the lock                 #
            # -------------------------------------------------------------- #
            for idx, request in validated:
                raw_entry = batch[idx]
                query_text = (
                    raw_entry.get("query", "") if isinstance(raw_entry, dict) else ""
                )

                policy_passed, policy_reason = _evaluate_policy(request)
                if not policy_passed:
                    entry_results[idx] = _entry_result(
                        query_text,
                        status="skipped",
                        reason_code=policy_reason,
                    )
                    continue

                # Write the analysis file
                analysis_relative = _analysis_relative_path(request, repo_root)
                analysis_absolute = repo_root / analysis_relative
                analysis_markdown = _render_analysis_markdown(
                    request, analysis_relative.as_posix()
                )
                # Verify the analysis path stays inside wiki/analyses/ before writing.
                analyses_root = (repo_root / "wiki" / "analyses").resolve()
                if not analysis_absolute.resolve().is_relative_to(analyses_root):
                    raise OSError(
                        f"analysis path escapes wiki/analyses/: {analysis_absolute}"
                    )

                snapshot: str | None = None
                try:
                    changed, snapshot = write_text_capturing_previous_safe(
                        analysis_absolute, analysis_markdown
                    )
                    rel_str = analysis_relative.as_posix()
                    entry_results[idx] = _entry_result(
                        query_text,
                        status="written",
                        reason_code=contracts.ReasonCode.OK.value,
                        analysis_path=rel_str,
                    )
                    if changed:
                        written_paths.append(rel_str)
                except OSError as exc:
                    # Roll back this single file and mark the entry as failed.
                    try:
                        rollback_file_state([(analysis_absolute, snapshot)])
                    except OSError:
                        pass
                    entry_results[idx] = _entry_result(
                        query_text,
                        status="failed",
                        reason_code=contracts.ReasonCode.WRITE_FAILED.value,
                    )
                    error_stream.write(f"error: write failed for entry {idx}: {exc}\n")

            # -------------------------------------------------------------- #
            # 6. Update index once after all entries                          #
            # -------------------------------------------------------------- #
            try:
                update_index.generate_and_write_index(wiki_root_path)
            except (OSError, update_index.IndexGenerationError) as exc:
                # Intentional divergence from persist_query.py: in batch mode, rolling back
                # N already-confirmed writes would be more destructive than a stale index.
                # The index is advisory; it will be regenerated on the next successful run.
                error_stream.write(f"warning: index update failed: {exc}\n")

            # -------------------------------------------------------------- #
            # 7. Append a single batch summary log entry                      #
            # -------------------------------------------------------------- #
            n_newly_written = len(written_paths)
            if n_newly_written > 0:
                log_entry = _build_batch_log_entry(n_newly_written, written_paths)
                append_log_only_state_changes(
                    repo_root,
                    log_entry,
                    state_changed=True,
                )

    except write_utils.LockUnavailableError as exc:
        # Mark all pre-validated entries as failed due to lock contention.
        for idx, _ in validated:
            raw_entry = batch[idx]
            query_text = (
                raw_entry.get("query", "") if isinstance(raw_entry, dict) else ""
            )
            entry_results[idx] = _entry_result(
                query_text,
                status="failed",
                reason_code=contracts.ReasonCode.LOCK_UNAVAILABLE.value,
            )
        error_stream.write(f"error: {exc.failure_reason}\n")
        _emit_fail(
            output_stream=output_stream,
            reason_code=contracts.ReasonCode.LOCK_UNAVAILABLE.value,
            total=total,
            entries=[e for e in entry_results if e is not None],
        )
        return 1

    # ------------------------------------------------------------------ #
    # 8. Emit final pass envelope                                          #
    # ------------------------------------------------------------------ #
    _finalize_envelope(
        output_stream=output_stream, total=total, entry_results=entry_results
    )
    return 0


def _finalize_envelope(
    *,
    output_stream: TextIO,
    total: int,
    entry_results: list[dict[str, Any] | None],
) -> None:
    """Emit a 'pass' envelope with per-entry counts."""
    resolved = [e for e in entry_results if e is not None]
    n_written = sum(1 for e in resolved if e["status"] == "written")
    n_skipped = sum(1 for e in resolved if e["status"] == "skipped")
    n_failed = sum(1 for e in resolved if e["status"] == "failed")
    envelope = {
        "status": "pass",
        "surface": SURFACE,
        "mode": "apply",
        "reason_code": contracts.ReasonCode.OK.value,
        "total": total,
        "written": n_written,
        "skipped": n_skipped,
        "failed": n_failed,
        "entries": resolved,
    }
    output_stream.write(json.dumps(envelope, sort_keys=True))
    output_stream.write("\n")


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------


def run_batch_cli(
    argv: Sequence[str] | None = None,
    *,
    output_stream: TextIO = sys.stdout,
    error_stream: TextIO = sys.stderr,
    repo_root: str | Path = ".",
) -> int:
    """CLI wrapper for batch policy-gated query persistence."""
    repo_root_path = Path(repo_root).resolve()
    parser = _build_parser()

    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        if int(exc.code) == 0:
            return 0
        _emit_fail(
            output_stream=output_stream,
            reason_code=contracts.ReasonCode.INVALID_INPUT.value,
            total=0,
            entries=[],
        )
        return 1

    return _execute_batch(
        args,
        repo_root_path,
        output_stream=output_stream,
        error_stream=error_stream,
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run_batch_cli(argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
