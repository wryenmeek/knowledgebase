"""Copilot-agent-runtime doc generation: inventory/plan source inputs, apply agent-generated docs."""

from __future__ import annotations

import argparse
import json
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
    STATUS_FAIL,
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
    validate_staged_manifest,
)
from scripts.kb.write_utils import LockUnavailableError, exclusive_write_lock, rollback_file_state, write_text_capturing_previous_safe

SURFACE = "scripts/maintenance/generate_docs.py"
SUPPORTED_MODES: tuple[str, ...] = ("inventory", "plan", "apply")
LOCK_REQUIRED_MODES: tuple[str, ...] = ("apply",)

# READ_ROOTS: source inputs the agent reads to generate documentation.
ALLOWED_INPUT_ROOTS: tuple[str, ...] = (".github/skills", "docs", "schema", "scripts")
ALLOWED_INPUT_SUFFIXES: tuple[str, ...] = (".md", ".py")

# WRITE_ROOTS: generated docs are written to docs/ only.
WRITE_ROOTS: tuple[str, ...] = ("docs",)
# DENIED_WRITE_ROOTS: staging area is inside docs/ but must not be written as output.
DENIED_WRITE_ROOTS: tuple[str, ...] = ("docs/staged",)
ALLOWED_OUTPUT_SUFFIXES: tuple[str, ...] = (".md",)

# Staging area where the Copilot agent deposits generated-docs manifests.
STAGED_DOCS_ROOTS: tuple[str, ...] = ("docs/staged",)


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description=(
            "Inventory or plan maintenance doc generation inputs, or apply "
            "a Copilot-agent-produced docs manifest."
        )
    )
    add_common_surface_args(parser, modes=SUPPORTED_MODES, default_mode="inventory")
    parser.add_argument(
        "--staged-docs-path",
        default=None,
        help="Repo-relative path to a staged docs manifest JSON produced by the Copilot agent. Required for apply mode.",
    )
    return parser


def _path_rules() -> dict[str, object]:
    rules = base_path_rules(
        allowed_roots=ALLOWED_INPUT_ROOTS,
        allowed_suffixes=ALLOWED_INPUT_SUFFIXES,
    )
    rules["lock_path"] = LOCK_PATH
    rules["write_roots"] = list(WRITE_ROOTS)
    rules["denied_write_roots"] = list(DENIED_WRITE_ROOTS)
    rules["staged_docs_roots"] = list(STAGED_DOCS_ROOTS)
    rules["direct_writes_declared"] = True
    return rules


def run_generate_docs(
    *,
    repo_root: str | Path = ".",
    mode: str,
    paths: Sequence[str] | None = None,
    staged_docs_path: str | None = None,
    approval: str = APPROVAL_NONE,
) -> SurfaceResult:
    path_rules = _path_rules()
    normalized_repo_root = Path(repo_root).resolve()
    if not looks_like_repo_root(normalized_repo_root):
        return repo_root_failure(surface=SURFACE, mode=mode, approval=approval, path_rules=path_rules)

    if mode in {"inventory", "plan"}:
        try:
            resolved_paths = expand_repo_paths(
                normalized_repo_root,
                list(paths or ()),
                allowed_roots=ALLOWED_INPUT_ROOTS,
                allowed_suffixes=ALLOWED_INPUT_SUFFIXES,
            )
        except ValueError as exc:
            return invalid_input_result(
                surface=SURFACE, mode=mode, approval=approval,
                message=str(exc), path_rules=path_rules,
            )
        items = tuple(
            {
                "path": repo_relative(normalized_repo_root, path),
                "kind": "script" if path.suffix == ".py" else "document",
                "size_bytes": path.stat().st_size,
            }
            for path in resolved_paths
        )
        message = "maintenance doc inventory computed" if mode == "inventory" else "maintenance doc generation plan computed"
        return SurfaceResult(
            surface=SURFACE, mode=mode, status=STATUS_PASS, reason_code=REASON_CODE_OK,
            message=message, approval=approval, path_rules=path_rules, items=items,
            summary={
                "selected_count": len(items),
                "script_targets": sum(1 for item in items if item["kind"] == "script"),
                "document_targets": sum(1 for item in items if item["kind"] == "document"),
            },
        )

    # apply mode
    if approval != APPROVAL_APPROVED:
        return approval_required_result(
            surface=SURFACE, mode=mode, path_rules=path_rules, lock_required=True,
        )
    if not staged_docs_path:
        return invalid_input_result(
            surface=SURFACE, mode=mode, approval=approval,
            message="apply mode requires --staged-docs-path pointing to an agent-produced docs manifest",
            path_rules=path_rules,
        )
    try:
        staged_resolved = expand_repo_paths(
            normalized_repo_root, [staged_docs_path],
            allowed_roots=STAGED_DOCS_ROOTS,
            allowed_suffixes=(".json",),
        )
    except ValueError as exc:
        return invalid_input_result(
            surface=SURFACE, mode=mode, approval=approval,
            message=f"staged-docs-path invalid: {exc}", path_rules=path_rules,
        )
    staged_path = staged_resolved[0]
    try:
        raw_manifest = json.loads(staged_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return invalid_input_result(
            surface=SURFACE, mode=mode, approval=approval,
            message=f"could not parse staged docs manifest: {exc}", path_rules=path_rules,
        )
    try:
        manifest_items = validate_staged_manifest(
            raw_manifest,
            repo_root=normalized_repo_root,
            write_roots=WRITE_ROOTS,
            denied_roots=DENIED_WRITE_ROOTS,
            allowed_suffixes=list(ALLOWED_OUTPUT_SUFFIXES),
            reject_remaining_placeholders=False,
        )
    except ValueError as exc:
        return invalid_input_result(
            surface=SURFACE, mode=mode, approval=approval,
            message=str(exc), path_rules=path_rules,
        )

    snapshots: list[tuple[Path, str | None]] = []
    written_items = []
    try:
        with exclusive_write_lock(normalized_repo_root):
            for resolved_path, content, _sha in manifest_items:
                changed, previous = write_text_capturing_previous_safe(resolved_path, content)
                snapshots.append((resolved_path, previous))
                written_items.append({
                    "path": repo_relative(normalized_repo_root, resolved_path),
                    "changed": changed,
                })
    except LockUnavailableError as exc:
        return SurfaceResult(
            surface=SURFACE, mode=mode, status=STATUS_FAIL,
            reason_code="lock_unavailable",
            message=str(exc), approval=approval,
            lock_path=LOCK_PATH, lock_required=True,
            path_rules=path_rules, items=(),
        )
    except OSError as exc:
        rollback_file_state(snapshots)
        return SurfaceResult(
            surface=SURFACE, mode=mode, status=STATUS_FAIL,
            reason_code="write_failed",
            message=f"write failed and changes were rolled back: {exc}",
            approval=approval, lock_path=LOCK_PATH, lock_required=True,
            path_rules=path_rules, items=(),
        )

    return SurfaceResult(
        surface=SURFACE, mode=mode, status=STATUS_PASS, reason_code=REASON_CODE_OK,
        message="docs generation applied",
        approval=approval, lock_path=LOCK_PATH, lock_required=True,
        path_rules=path_rules, items=tuple(written_items),
        summary={
            "written_count": sum(1 for i in written_items if i["changed"]),
            "unchanged_count": sum(1 for i in written_items if not i["changed"]),
        },
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
            "staged_docs_path": a.staged_docs_path,
            "approval": a.approval,
        },
        output_stream=output_stream,
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv=argv)


__all__ = [
    "SURFACE",
    "SUPPORTED_MODES",
    "ALLOWED_INPUT_ROOTS",
    "WRITE_ROOTS",
    "DENIED_WRITE_ROOTS",
    "run_generate_docs",
    "run_cli",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())

