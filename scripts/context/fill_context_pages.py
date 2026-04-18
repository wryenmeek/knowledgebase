"""Read-only context fill planning with explicit later-phase write gating."""

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
    count_placeholders,
    expand_repo_paths,
    invalid_input_result,
    looks_like_repo_root,
    repo_relative,
    repo_root_failure,
    run_surface_cli,
    write_surface_not_declared_result,
)

SURFACE = "scripts/context/fill_context_pages.py"
SUPPORTED_MODES: tuple[str, ...] = ("preview", "apply")
LOCK_REQUIRED_MODES: tuple[str, ...] = ("apply",)
ALLOWED_CONTEXT_ROOTS: tuple[str, ...] = (".github/skills", "docs", "schema")
ALLOWED_CONTEXT_SUFFIXES: tuple[str, ...] = (".md",)


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description="Preview context fill candidates without opening a direct write path."
    )
    add_common_surface_args(parser, modes=SUPPORTED_MODES, default_mode="preview")
    return parser


def _path_rules() -> dict[str, object]:
    rules = base_path_rules(
        allowed_roots=ALLOWED_CONTEXT_ROOTS,
        allowed_suffixes=ALLOWED_CONTEXT_SUFFIXES,
    )
    rules["lock_path"] = LOCK_PATH
    rules["direct_writes_declared"] = False
    return rules


def run_fill_context(
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
            allowed_roots=ALLOWED_CONTEXT_ROOTS,
            allowed_suffixes=ALLOWED_CONTEXT_SUFFIXES,
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
    for path in resolved_paths:
        text = path.read_text(encoding="utf-8")
        placeholder_count = count_placeholders(text)
        if placeholder_count == 0:
            continue
        items.append(
            {
                "path": repo_relative(normalized_repo_root, path),
                "placeholder_count": placeholder_count,
                "write_surface": "undeclared_direct_context_write",
                "resolution": "route changes back through a narrower approved writer first",
            }
        )
    if mode == "preview":
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_PASS,
            reason_code=REASON_CODE_OK,
            message="context fill preview computed",
            approval=approval,
            path_rules=path_rules,
            items=tuple(items),
            summary={"candidate_count": len(items), "lock_required_modes": list(LOCK_REQUIRED_MODES)},
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
        message="direct context page writes stay deny-by-default until a narrower post-MVP writer row exists",
    )


def run_cli(argv: Sequence[str] | None = None, *, output_stream: TextIO = sys.stdout) -> int:
    return run_surface_cli(
        argv=argv,
        parser_factory=_build_parser,
        path_rules_factory=_path_rules,
        surface=SURFACE,
        runner=run_fill_context,
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


if __name__ == "__main__":
    raise SystemExit(main())
