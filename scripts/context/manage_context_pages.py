"""Approval-gated context page inventory and planning surface."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
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
    STATUS_FAIL,
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
)

SURFACE = "scripts/context/manage_context_pages.py"
SUPPORTED_MODES: tuple[str, ...] = ("inventory", "plan-fill", "publish-status")
LOCK_REQUIRED_MODES: tuple[str, ...] = ("publish-status",)
ALLOWED_CONTEXT_ROOTS: tuple[str, ...] = (".github/skills", "docs", "schema")
ALLOWED_CONTEXT_SUFFIXES: tuple[str, ...] = (".md",)
DEFAULT_LIMIT = 50
SYNC_WRAPPER = ".github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py"
STAGED_STATUS_ROOTS: tuple[str, ...] = ("docs/staged",)
STAGED_STATUS_SUFFIXES: tuple[str, ...] = (".md",)


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description="Manage repo-local context page inventories and plans.")
    add_common_surface_args(parser, modes=SUPPORTED_MODES, default_mode="inventory")
    parser.add_argument(
        "--changed-path",
        action="append",
        default=[],
        help="Optional changed paths used to narrow plan-fill output.",
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--staged-status-path", help="Repo-relative staged status file used by publish-status.")
    return parser


def _path_rules() -> dict[str, object]:
    rules = base_path_rules(
        allowed_roots=ALLOWED_CONTEXT_ROOTS,
        allowed_suffixes=ALLOWED_CONTEXT_SUFFIXES,
    )
    rules["lock_path"] = LOCK_PATH
    rules["delegated_writer"] = SYNC_WRAPPER
    return rules


def _collect_items(repo_root: Path, paths: Sequence[str], *, limit: int) -> tuple[dict[str, object], ...]:
    items = []
    for path in expand_repo_paths(
        repo_root,
        paths,
        allowed_roots=ALLOWED_CONTEXT_ROOTS,
        allowed_suffixes=ALLOWED_CONTEXT_SUFFIXES,
    )[: max(limit, 0)]:
        text = path.read_text(encoding="utf-8")
        items.append(
            {
                "path": repo_relative(repo_root, path),
                "size_bytes": path.stat().st_size,
                "placeholder_count": count_placeholders(text),
            }
        )
    return tuple(items)


def _resolve_staged_status_path(repo_root: Path, raw_path: str) -> str:
    staged_paths = expand_repo_paths(
        repo_root,
        [raw_path],
        allowed_roots=STAGED_STATUS_ROOTS,
        allowed_suffixes=STAGED_STATUS_SUFFIXES,
    )
    if len(staged_paths) != 1:
        raise ValueError("publish-status requires exactly one staged markdown file")
    return repo_relative(repo_root, staged_paths[0])


def _resolve_sync_wrapper(repo_root: Path) -> Path:
    repo_local_wrapper = repo_root / SYNC_WRAPPER
    if repo_local_wrapper.is_file():
        return repo_local_wrapper
    return Path(__file__).resolve().parents[2] / SYNC_WRAPPER


def run_context_management(
    *,
    repo_root: str | Path = ".",
    mode: str,
    paths: Sequence[str] | None = None,
    changed_paths: Sequence[str] | None = None,
    limit: int = DEFAULT_LIMIT,
    staged_status_path: str | None = None,
    approval: str = APPROVAL_NONE,
) -> SurfaceResult:
    path_rules = _path_rules()
    normalized_repo_root = Path(repo_root).resolve()
    if not looks_like_repo_root(normalized_repo_root):
        return repo_root_failure(surface=SURFACE, mode=mode, approval=approval, path_rules=path_rules)
    if limit < 0:
        return invalid_input_result(
            surface=SURFACE,
            mode=mode,
            approval=approval,
            message="limit must be zero or greater",
            path_rules=path_rules,
        )
    try:
        items = _collect_items(normalized_repo_root, list(paths or ()), limit=limit)
    except ValueError as exc:
        return invalid_input_result(
            surface=SURFACE,
            mode=mode,
            approval=approval,
            message=str(exc),
            path_rules=path_rules,
        )
    if mode == "inventory":
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_PASS,
            reason_code=REASON_CODE_OK,
            message="context page inventory computed",
            approval=approval,
            path_rules=path_rules,
            items=items,
            summary={"selected_count": len(items), "lock_required_modes": list(LOCK_REQUIRED_MODES)},
        )
    if mode == "plan-fill":
        changed = {path.strip() for path in (changed_paths or ()) if path.strip()}
        planned = tuple(
            item
            for item in items
            if item["placeholder_count"] > 0 and (not changed or item["path"] in changed)
        )
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_PASS,
            reason_code=REASON_CODE_OK,
            message="context fill plan computed",
            approval=approval,
            path_rules=path_rules,
            items=planned,
            summary={
                "selected_count": len(items),
                "planned_count": len(planned),
                "changed_path_filter": sorted(changed),
                "lock_required": False,
            },
        )
    if approval != APPROVAL_APPROVED:
        return approval_required_result(
            surface=SURFACE,
            mode=mode,
            path_rules=path_rules,
            lock_required=True,
        )
    if not staged_status_path:
        return invalid_input_result(
            surface=SURFACE,
            mode=mode,
            approval=approval,
            message="publish-status requires --staged-status-path",
            path_rules=path_rules,
        )
    try:
        staged_status_rel = _resolve_staged_status_path(normalized_repo_root, staged_status_path)
    except ValueError as exc:
        return invalid_input_result(
            surface=SURFACE,
            mode=mode,
            approval=approval,
            message=str(exc),
            path_rules=path_rules,
        )
    command = [
        sys.executable,
        str(_resolve_sync_wrapper(normalized_repo_root)),
        "--write-status-from",
        staged_status_rel,
    ]
    try:
        subprocess.run(command, cwd=normalized_repo_root, check=True)
    except subprocess.CalledProcessError as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_FAIL,
            reason_code="delegated_write_failed",
            message=f"delegated governed write failed with exit code {exc.returncode}",
            approval=approval,
            lock_path=LOCK_PATH,
            lock_required=True,
            path_rules=path_rules,
            items=items,
        )
    return SurfaceResult(
        surface=SURFACE,
        mode=mode,
        status=STATUS_PASS,
        reason_code=REASON_CODE_OK,
        message="delegated status publication completed",
        approval=approval,
        lock_path=LOCK_PATH,
        lock_required=True,
        path_rules=path_rules,
        items=items,
        summary={"delegated_writer": SYNC_WRAPPER},
    )


def run_cli(argv: Sequence[str] | None = None, *, output_stream: TextIO = sys.stdout) -> int:
    return run_surface_cli(
        argv=argv,
        parser_factory=_build_parser,
        path_rules_factory=_path_rules,
        surface=SURFACE,
        runner=run_context_management,
        args_to_kwargs=lambda a: {
            "repo_root": a.repo_root,
            "mode": a.mode,
            "paths": a.path,
            "changed_paths": a.changed_path,
            "limit": a.limit,
            "staged_status_path": a.staged_status_path,
            "approval": a.approval,
        },
        output_stream=output_stream,
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
