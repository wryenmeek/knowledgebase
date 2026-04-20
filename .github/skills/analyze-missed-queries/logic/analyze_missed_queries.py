"""Read-only wiki coverage gap analysis from available evidence."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
import sys
from typing import Sequence, TextIO

if __package__ in (None, ""):  # supports both 'python -m' and direct invocation without package install
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts._optional_surface_common import (
    APPROVAL_NONE,
    JsonArgumentParser,
    REASON_CODE_OK,
    STATUS_PASS,
    SurfaceResult,
    expand_repo_paths,
    invalid_input_result,
    looks_like_repo_root,
    repo_relative,
    repo_root_failure,
    run_surface_cli,
)

SURFACE = ".github/skills/analyze-missed-queries/logic/analyze_missed_queries.py"
SUPPORTED_MODES: tuple[str, ...] = ("scan",)
ALLOWED_WIKI_ROOTS: tuple[str, ...] = ("wiki",)
ALLOWED_WIKI_SUFFIXES: tuple[str, ...] = (".md",)

# Markers that indicate a page has evidence gaps or is incomplete
_GAP_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"TODO", "placeholder TODO marker"),
    (r"PLACEHOLDER", "placeholder PLACEHOLDER marker"),
    (r"confidence:\s*low", "low confidence frontmatter"),
    (r"\bTBD\b", "TBD (to be determined) text"),
    (r"\?\?\?", "unresolved question markers"),
    (r"sources:\s*\[\s*\]", "empty sources list in frontmatter"),
)


def _path_rules() -> dict[str, object]:
    return {
        "allowed_roots": list(ALLOWED_WIKI_ROOTS),
        "allowed_suffixes": list(ALLOWED_WIKI_SUFFIXES),
        "direct_writes_declared": False,
        "read_only": True,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description="Scan wiki pages for coverage gaps: missing citations, low confidence, placeholder markers."
    )
    parser.add_argument(
        "--mode",
        choices=SUPPORTED_MODES,
        default="scan",
        help="scan: enumerate coverage gaps from wiki evidence.",
    )
    parser.add_argument(
        "--path",
        action="append",
        dest="path",
        default=None,
        metavar="PATH",
        help="Wiki path(s) to scan. Defaults to all wiki/** pages.",
    )
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--approval", default=APPROVAL_NONE, help="Unused; reserved.")
    return parser


def _scan_page_for_gaps(page_path: Path) -> list[dict]:
    """Return gap findings for a single wiki page."""
    try:
        content = page_path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [
        {"gap_type": label, "pattern": pattern}
        for pattern, label in _GAP_PATTERNS
        if re.search(pattern, content, re.IGNORECASE)
    ]


def run_analyze_missed_queries(
    *,
    repo_root: str | Path = ".",
    mode: str = "scan",
    paths: Sequence[str] | None = None,
    approval: str = APPROVAL_NONE,
) -> SurfaceResult:
    path_rules = _path_rules()
    normalized_repo_root = Path(repo_root).resolve()
    if not looks_like_repo_root(normalized_repo_root):
        return repo_root_failure(surface=SURFACE, mode=mode, approval=approval, path_rules=path_rules)

    try:
        resolved_paths = expand_repo_paths(
            normalized_repo_root,
            list(paths or ()),
            allowed_roots=ALLOWED_WIKI_ROOTS,
            allowed_suffixes=ALLOWED_WIKI_SUFFIXES,
        )
    except ValueError as exc:
        return invalid_input_result(
            surface=SURFACE,
            mode=mode,
            approval=approval,
            message=str(exc),
            path_rules=path_rules,
        )

    items = []
    for page_path in resolved_paths:
        gaps = _scan_page_for_gaps(page_path)
        if gaps:
            items.append(
                {
                    "path": repo_relative(normalized_repo_root, page_path),
                    "gap_count": len(gaps),
                    "gaps": gaps,
                }
            )

    return SurfaceResult(
        surface=SURFACE,
        mode=mode,
        status=STATUS_PASS,
        reason_code=REASON_CODE_OK,
        message=f"coverage gap scan complete: {len(items)}/{len(resolved_paths)} pages have gaps",
        approval=approval,
        path_rules=path_rules,
        items=tuple(items),
        summary={
            "scanned_count": len(resolved_paths),
            "gap_page_count": len(items),
        },
    )


def run_cli(argv: Sequence[str] | None = None, *, output_stream: TextIO = sys.stdout) -> int:
    return run_surface_cli(
        argv=argv,
        parser_factory=_build_parser,
        path_rules_factory=_path_rules,
        surface=SURFACE,
        runner=run_analyze_missed_queries,
        args_to_kwargs=lambda a: {
            "repo_root": a.repo_root,
            "mode": a.mode,
            "paths": a.path,
            "approval": a.approval,
        },
        output_stream=output_stream,
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv=argv)


__all__ = [
    "SURFACE",
    "SUPPORTED_MODES",
    "ALLOWED_WIKI_ROOTS",
    "run_analyze_missed_queries",
    "run_cli",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())
