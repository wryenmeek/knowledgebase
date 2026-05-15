"""Wiki coverage analytics with approval-gated persist mode.

Modes:
  summary  (default, read-only) — Scans wiki/** pages and emits a JSON
            SurfaceResult with per-namespace page counts, placeholder counts,
            stale-page counts (pages whose updated_at exceeds
            _STALE_THRESHOLD_DAYS days old), empty-namespace list, and an
            overall coverage_ratio. No file is written.

  persist  (write-capable, approval-gated) — Runs the same analysis, then
            writes a governed report artifact to
            wiki/reports/coverage-report-<date>.json.
            Requires --approval approved and acquires wiki/.kb_write.lock
            (ADR-005) before writing. Fails closed on missing approval, lock
            contention, wiki path boundary violation, or OSError.

Fail-closed invariants:
  - persist mode hard-fails without --approval approved.
  - Directory symlinks are never followed during wiki page collection
    (_collect_pages uses os.scandir with follow_symlinks=False).
  - LockUnavailableError and OSError on write propagate as STATUS_FAIL
    envelopes; no partial artifact is left on disk.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from typing import Sequence, TextIO

if __package__ in (None, ""):  # supports both 'python -m' and direct invocation without package install
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts._optional_surface_common import (
    APPROVAL_APPROVED,
    APPROVAL_NONE,
    LOCK_PATH,
    JsonArgumentParser,
    REASON_CODE_OK,
    STATUS_FAIL,
    STATUS_PASS,
    SurfaceResult,
    add_common_surface_args,
    approval_required_result,
    base_path_rules,
    count_placeholders,
    lock_unavailable_result,
    looks_like_repo_root,
    repo_relative,
    repo_root_failure,
    run_surface_cli,
    write_report_artifact,
)
from scripts.kb import page_template_utils
from scripts.kb.write_utils import LockUnavailableError

SURFACE = "scripts/reporting/coverage_report.py"
SUPPORTED_MODES: tuple[str, ...] = ("summary", "persist")
LOCK_REQUIRED_MODES: tuple[str, ...] = ("persist",)

# Top-level wiki files excluded from page counting (must be directly under wiki/)
_EXCLUDED_TOP_LEVEL: frozenset[str] = frozenset(
    {
        "index.md",
        "log.md",
        "status.md",
        "backlog.md",
        "open-questions.md",
        "redirects.md",
    }
)

_STALE_THRESHOLD_DAYS: int = 180

_DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description=(
            "Analyze wiki coverage and emit analytics; persist mode writes a governed report artifact."
        )
    )
    add_common_surface_args(
        parser, modes=SUPPORTED_MODES, default_mode="summary", include_path=False
    )
    return parser


def _path_rules() -> dict[str, object]:
    rules = base_path_rules(
        allowed_roots=("wiki",),
        allowed_suffixes=(".md",),
    )
    rules["coverage_analytics_declared"] = True
    return rules


def _detect_namespace(page_path: Path, wiki_root: Path) -> str:
    """Return the namespace for a wiki page.

    Top-level pages (parent == wiki_root) → "topical".
    All other pages → first subdirectory name under wiki/.
    """
    relative = page_path.relative_to(wiki_root)
    parts = relative.parts
    if len(parts) == 1:
        return "topical"
    return parts[0]


def _parse_updated_at(frontmatter: dict[str, str]) -> datetime | None:
    """Parse the updated_at frontmatter field into an aware datetime, or None."""
    raw = frontmatter.get("updated_at", "").strip("\"'")
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _is_stale(frontmatter: dict[str, str], now: datetime) -> bool:
    """Return True if the page's updated_at is older than _STALE_THRESHOLD_DAYS."""
    updated_at = _parse_updated_at(frontmatter)
    if updated_at is None:
        # Intentional: pages without updated_at (pre-dates the field requirement) are
        # treated as non-stale to avoid false positives. Operators should prioritize
        # adding updated_at to legacy pages separately.
        return False
    return (now - updated_at).days > _STALE_THRESHOLD_DAYS


def _collect_pages(wiki_root: Path) -> list[Path]:
    """Collect all wiki pages, excluding canonical top-level artifact files.

    Uses a manual os.scandir walk that never follows directory symlinks,
    eliminating the symlink-traversal DoS vector that rglob introduces.
    Uses ``Path.is_relative_to`` for boundary enforcement — never ``startswith``.
    """
    resolved_wiki = wiki_root.resolve()
    pages: list[Path] = []
    stack: list[Path] = [resolved_wiki]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as exc:
            sys.stderr.write(f"warning: scandir failed for {current}: {exc}\n")
            continue
        for entry in entries:
            if entry.is_symlink():
                continue  # never follow symlinks
            entry_path = Path(entry.path)
            if entry.is_dir(follow_symlinks=False):
                candidate = entry_path.resolve()
                if candidate.is_relative_to(resolved_wiki):
                    stack.append(candidate)
            elif entry.is_file(follow_symlinks=False) and entry.name.endswith(".md"):
                # Exclude canonical top-level artifact files
                if entry_path.parent.resolve() == resolved_wiki and entry.name in _EXCLUDED_TOP_LEVEL:
                    continue
                pages.append(entry_path)
    return sorted(pages)


def _compute_coverage(
    wiki_root: Path,
    normalized_repo_root: Path,
) -> tuple[list[dict], dict]:
    """Compute per-page items and aggregated coverage statistics.

    Returns:
        page_items: list of per-page dicts (path, namespace, is_placeholder, is_stale)
        summary_stats: aggregated coverage statistics dict
    """
    now = datetime.now(timezone.utc)
    pages = _collect_pages(wiki_root)
    topical_ns = page_template_utils.TOPICAL_NAMESPACES

    pages_by_namespace: dict[str, int] = {}
    placeholder_pages_by_namespace: dict[str, int] = {}
    stale_pages_by_namespace: dict[str, int] = {}
    page_items: list[dict] = []
    total_placeholders = 0
    total_stale = 0

    for page in pages:
        text = page.read_text(encoding="utf-8")
        frontmatter = page_template_utils.parse_page_frontmatter(text)
        ns = _detect_namespace(page, wiki_root)
        is_placeholder = count_placeholders(text) > 0
        is_stale_page = _is_stale(frontmatter, now)

        pages_by_namespace[ns] = pages_by_namespace.get(ns, 0) + 1
        if is_placeholder:
            total_placeholders += 1
            placeholder_pages_by_namespace[ns] = (
                placeholder_pages_by_namespace.get(ns, 0) + 1
            )
        if is_stale_page:
            total_stale += 1
            stale_pages_by_namespace[ns] = stale_pages_by_namespace.get(ns, 0) + 1

        page_items.append(
            {
                "path": repo_relative(normalized_repo_root, page.resolve()),
                "namespace": ns,
                "is_placeholder": is_placeholder,
                "is_stale": is_stale_page,
            }
        )

    total_pages = len(pages)
    coverage_ratio = (
        1.0
        if total_pages == 0
        else (total_pages - total_placeholders) / total_pages
    )

    # empty_namespaces: TOPICAL_NAMESPACES declared entries with 0 pages
    empty_namespaces = sorted(
        ns for ns in topical_ns if pages_by_namespace.get(ns, 0) == 0
    )

    summary_stats = {
        "total_pages": total_pages,
        "pages_by_namespace": pages_by_namespace,
        "placeholder_pages_by_namespace": placeholder_pages_by_namespace,
        "stale_pages_by_namespace": stale_pages_by_namespace,
        "empty_namespaces": empty_namespaces,
        "total_stale": total_stale,
        "total_placeholders": total_placeholders,
        "coverage_ratio": coverage_ratio,
    }
    return page_items, summary_stats


def _empty_coverage_stats() -> dict:
    """Return coverage stats for an empty or missing wiki directory."""
    return {
        "total_pages": 0,
        "pages_by_namespace": {},
        "placeholder_pages_by_namespace": {},
        "stale_pages_by_namespace": {},
        "empty_namespaces": sorted(page_template_utils.TOPICAL_NAMESPACES),
        "total_stale": 0,
        "total_placeholders": 0,
        "coverage_ratio": 1.0,
    }


def run_coverage_report(
    *,
    repo_root: str | Path = ".",
    mode: str,
    approval: str = APPROVAL_NONE,
) -> SurfaceResult:
    path_rules = _path_rules()
    normalized_repo_root = Path(repo_root).resolve()
    if not looks_like_repo_root(normalized_repo_root):
        return repo_root_failure(
            surface=SURFACE, mode=mode, approval=approval, path_rules=path_rules
        )

    wiki_root = normalized_repo_root / "wiki"

    if wiki_root.is_dir():
        page_items, summary_stats = _compute_coverage(wiki_root, normalized_repo_root)
    else:
        page_items = []
        summary_stats = _empty_coverage_stats()

    if mode == "summary":
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_PASS,
            reason_code=REASON_CODE_OK,
            message="wiki coverage report computed",
            approval=approval,
            path_rules=path_rules,
            items=tuple(page_items),
            summary=summary_stats,
        )

    # persist mode
    if approval != APPROVAL_APPROVED:
        return approval_required_result(
            surface=SURFACE,
            mode=mode,
            path_rules=path_rules,
            lock_required=True,
        )

    artifact = {
        "report_type": "coverage-report",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": ["wiki"],
        "surface": SURFACE,
        "findings": page_items,
        "summary": {
            "total_pages": summary_stats["total_pages"],
            "total_placeholders": summary_stats["total_placeholders"],
            "total_stale": summary_stats["total_stale"],
            "coverage_ratio": summary_stats["coverage_ratio"],
            "pages_by_namespace": summary_stats["pages_by_namespace"],
            "placeholder_pages_by_namespace": summary_stats["placeholder_pages_by_namespace"],
            "stale_pages_by_namespace": summary_stats["stale_pages_by_namespace"],
            "empty_namespaces": summary_stats["empty_namespaces"],
        },
    }
    try:
        written_path = write_report_artifact(
            normalized_repo_root, "coverage-report", artifact
        )
    except LockUnavailableError as exc:
        return lock_unavailable_result(
            surface=SURFACE,
            mode=mode,
            approval=approval,
            path_rules=path_rules,
            exc=exc,
        )
    except OSError as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_FAIL,
            reason_code="write_failed",
            message=f"report write failed: {exc}",
            approval=approval,
            lock_path=LOCK_PATH,
            lock_required=True,
            path_rules=path_rules,
        )
    return SurfaceResult(
        surface=SURFACE,
        mode=mode,
        status=STATUS_PASS,
        reason_code=REASON_CODE_OK,
        message=f"wiki coverage report persisted to {repo_relative(normalized_repo_root, written_path)}",
        approval=approval,
        lock_path=LOCK_PATH,
        lock_required=True,
        path_rules=path_rules,
        items=tuple(page_items),
        summary={
            **summary_stats,
            "written_path": repo_relative(normalized_repo_root, written_path),
        },
    )


def run_cli(argv: Sequence[str] | None = None, *, output_stream: TextIO = sys.stdout) -> int:
    return run_surface_cli(
        argv=argv,
        parser_factory=_build_parser,
        path_rules_factory=_path_rules,
        surface=SURFACE,
        runner=run_coverage_report,
        args_to_kwargs=lambda a: {
            "repo_root": a.repo_root,
            "mode": a.mode,
            "approval": a.approval,
        },
        output_stream=output_stream,
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv=argv)


__all__ = [
    "SURFACE",
    "SUPPORTED_MODES",
    "run_coverage_report",
    "run_cli",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())
