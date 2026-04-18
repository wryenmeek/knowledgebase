"""Read-only content quality reporting with explicit no-persist boundary."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence, TextIO

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts._optional_surface_common import (
    APPROVAL_APPROVED,
    APPROVAL_NONE,
    JsonArgumentParser,
    REASON_CODE_OK,
    STATUS_PASS,
    SurfaceResult,
    add_common_surface_args,
    approval_required_result,
    base_path_rules,
    count_placeholders,
    expand_repo_paths,
    invalid_input_result,
    looks_like_repo_root,
    repo_relative,
    repo_root_failure,
    run_surface_cli,
    write_surface_not_declared_result,
)
from scripts.kb import page_template_utils

SURFACE = "scripts/reporting/content_quality_report.py"
SUPPORTED_MODES: tuple[str, ...] = ("summary", "placeholder-audit", "persist")
LOCK_REQUIRED_MODES: tuple[str, ...] = ("persist",)
ALLOWED_REPORT_ROOTS: tuple[str, ...] = ("docs", "wiki")
ALLOWED_REPORT_SUFFIXES: tuple[str, ...] = (".md",)


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description="Summarize repo-local content quality without persisting report artifacts."
    )
    add_common_surface_args(parser, modes=SUPPORTED_MODES, default_mode="summary")
    return parser


def _path_rules() -> dict[str, object]:
    rules = base_path_rules(
        allowed_roots=ALLOWED_REPORT_ROOTS,
        allowed_suffixes=ALLOWED_REPORT_SUFFIXES,
    )
    rules["durable_report_schema_declared"] = False
    return rules


def _frontmatter_keys(text: str) -> set[str]:
    frontmatter, _body = page_template_utils.extract_frontmatter(text)
    if frontmatter is None:
        return set()
    return set(page_template_utils.parse_frontmatter(frontmatter).keys())


def run_quality_report(
    *,
    repo_root: str | Path = ".",
    mode: str,
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
            allowed_roots=ALLOWED_REPORT_ROOTS,
            allowed_suffixes=ALLOWED_REPORT_SUFFIXES,
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
    missing_sources = 0
    missing_updated_at = 0
    placeholder_files = 0
    for path in resolved_paths:
        text = path.read_text(encoding="utf-8")
        frontmatter_keys = _frontmatter_keys(text)
        has_sources = "sources" in frontmatter_keys
        has_updated_at = "updated_at" in frontmatter_keys
        placeholder_count = count_placeholders(text)
        missing_sources += 0 if has_sources else 1
        missing_updated_at += 0 if has_updated_at else 1
        placeholder_files += 1 if placeholder_count else 0
        items.append(
            {
                "path": repo_relative(normalized_repo_root, path),
                "missing_sources": not has_sources,
                "missing_updated_at": not has_updated_at,
                "placeholder_count": placeholder_count,
            }
        )
    if mode in {"summary", "placeholder-audit"}:
        reported_items = tuple(items if mode == "summary" else [item for item in items if item["placeholder_count"] > 0])
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_PASS,
            reason_code=REASON_CODE_OK,
            message="content quality report computed",
            approval=approval,
            path_rules=path_rules,
            items=reported_items,
            summary={
                "selected_count": len(items),
                "missing_sources_count": missing_sources,
                "missing_updated_at_count": missing_updated_at,
                "placeholder_file_count": placeholder_files,
            },
        )
    if approval != APPROVAL_APPROVED:
        return approval_required_result(
            surface=SURFACE,
            mode=mode,
            path_rules=path_rules,
            lock_required=True,
        )
    return write_surface_not_declared_result(
        surface=SURFACE,
        mode=mode,
        approval=approval,
        path_rules=path_rules,
        lock_required=True,
        message="scripts/reporting/** cannot persist report artifacts until a schema-backed durable output contract exists",
    )


def run_cli(argv: Sequence[str] | None = None, *, output_stream: TextIO = sys.stdout) -> int:
    return run_surface_cli(
        argv=argv,
        parser_factory=_build_parser,
        path_rules_factory=_path_rules,
        surface=SURFACE,
        runner=run_quality_report,
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
    "run_quality_report",
    "run_cli",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())
