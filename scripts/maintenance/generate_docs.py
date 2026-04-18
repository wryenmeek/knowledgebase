"""Approval-gated maintenance doc generation planning surface."""

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
    LOCK_PATH,
    REASON_CODE_OK,
    STATUS_PASS,
    SurfaceResult,
    add_common_surface_args,
    approval_required_result,
    base_path_rules,
    expand_repo_paths,
    invalid_input_result,
    looks_like_repo_root,
    repo_relative,
    repo_root_failure,
    run_surface_cli,
    write_surface_not_declared_result,
)

SURFACE = "scripts/maintenance/generate_docs.py"
SUPPORTED_MODES: tuple[str, ...] = ("inventory", "plan", "apply")
LOCK_REQUIRED_MODES: tuple[str, ...] = ("apply",)
ALLOWED_INPUT_ROOTS: tuple[str, ...] = (".github/skills", "docs", "schema", "scripts")
ALLOWED_INPUT_SUFFIXES: tuple[str, ...] = (".md", ".py")


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description="Inventory or plan maintenance doc generation without opening undeclared writes."
    )
    add_common_surface_args(parser, modes=SUPPORTED_MODES, default_mode="inventory")
    return parser


def _path_rules() -> dict[str, object]:
    rules = base_path_rules(
        allowed_roots=ALLOWED_INPUT_ROOTS,
        allowed_suffixes=ALLOWED_INPUT_SUFFIXES,
    )
    rules["lock_path"] = LOCK_PATH
    rules["direct_writes_declared"] = False
    return rules


def run_generate_docs(
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
            allowed_roots=ALLOWED_INPUT_ROOTS,
            allowed_suffixes=ALLOWED_INPUT_SUFFIXES,
        )
    except ValueError as exc:
        return invalid_input_result(
            surface=SURFACE,
            mode=mode,
            approval=approval,
            message=str(exc),
            path_rules=path_rules,
        )
    items = tuple(
        {
            "path": repo_relative(normalized_repo_root, path),
            "kind": "script" if path.suffix == ".py" else "document",
            "size_bytes": path.stat().st_size,
        }
        for path in resolved_paths
    )
    if mode in {"inventory", "plan"}:
        message = "maintenance doc inventory computed" if mode == "inventory" else "maintenance doc generation plan computed"
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_PASS,
            reason_code=REASON_CODE_OK,
            message=message,
            approval=approval,
            path_rules=path_rules,
            items=items,
            summary={
                "selected_count": len(items),
                "script_targets": sum(1 for item in items if item["kind"] == "script"),
                "document_targets": sum(1 for item in items if item["kind"] == "document"),
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
        message="scripts/maintenance/** has no narrower write row for generated docs yet; apply remains blocked",
    )


def run_cli(argv: Sequence[str] | None = None, *, output_stream: TextIO = sys.stdout) -> int:
    return run_surface_cli(
        argv=argv,
        parser_factory=_build_parser,
        path_rules_factory=_path_rules,
        surface=SURFACE,
        runner=run_generate_docs,
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
    "run_generate_docs",
    "run_cli",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())
