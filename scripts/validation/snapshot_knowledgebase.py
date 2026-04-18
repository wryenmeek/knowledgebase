"""Deterministic capture/compare snapshots for repo-local knowledgebase state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence, TextIO

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts._optional_surface_common import (
    APPROVAL_NONE,
    JsonArgumentParser,
    REASON_CODE_MISSING_SNAPSHOT,
    REASON_CODE_OK,
    STATUS_FAIL,
    STATUS_PASS,
    SurfaceResult,
    add_common_surface_args,
    base_path_rules,
    expand_repo_paths,
    invalid_input_result,
    looks_like_repo_root,
    repo_relative,
    repo_root_failure,
    run_surface_cli,
    sha256_file,
)

SURFACE = "scripts/validation/snapshot_knowledgebase.py"
SUPPORTED_MODES: tuple[str, ...] = ("capture", "compare")
ALLOWED_SNAPSHOT_ROOTS: tuple[str, ...] = ("raw/processed", "schema", "wiki")


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description="Capture or compare deterministic knowledgebase snapshots.")
    add_common_surface_args(
        parser,
        modes=SUPPORTED_MODES,
        default_mode="capture",
        include_approval=False,
    )
    parser.add_argument("--snapshot", help="Repo-relative JSON snapshot captured earlier.")
    return parser


def _path_rules() -> dict[str, object]:
    rules = base_path_rules(allowed_roots=ALLOWED_SNAPSHOT_ROOTS, allowed_suffixes=None)
    rules["read_only"] = True
    return rules


def _capture_snapshot(repo_root: Path, paths: Sequence[str]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "path": repo_relative(repo_root, path),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in expand_repo_paths(
            repo_root,
            list(paths),
            allowed_roots=ALLOWED_SNAPSHOT_ROOTS,
            allowed_suffixes=None,
        )
    )


def _resolve_repo_file(repo_root: Path, raw_path: str) -> Path:
    normalized = raw_path.strip()
    if not normalized:
        raise ValueError("snapshot path must be a non-empty repo-relative path")
    candidate = Path(normalized)
    if candidate.is_absolute():
        raise ValueError(f"snapshot path must be repo-relative: {raw_path}")
    resolved = (repo_root / candidate).resolve()
    if not resolved.is_relative_to(repo_root):
        raise ValueError(f"snapshot path escapes repository root: {raw_path}")
    if not resolved.is_file() or resolved.suffix.lower() != ".json":
        raise ValueError("snapshot path must reference an existing JSON file within the repository")
    return resolved


def _load_snapshot_items(snapshot_file: Path) -> list[dict[str, object]]:
    payload = json.loads(snapshot_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("snapshot JSON must be an object with an 'items' list")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("snapshot JSON must contain an 'items' list")
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("snapshot items must be objects")
        if not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
            raise ValueError("snapshot items must include string 'path' and 'sha256' fields")
    return items


def run_snapshot(
    *,
    repo_root: str | Path = ".",
    mode: str,
    paths: Sequence[str] | None = None,
    snapshot_path: str | None = None,
) -> SurfaceResult:
    path_rules = _path_rules()
    normalized_repo_root = Path(repo_root).resolve()
    if not looks_like_repo_root(normalized_repo_root):
        return repo_root_failure(surface=SURFACE, mode=mode, approval=APPROVAL_NONE, path_rules=path_rules)
    try:
        captured = _capture_snapshot(normalized_repo_root, list(paths or ()))
    except ValueError as exc:
        return invalid_input_result(
            surface=SURFACE,
            mode=mode,
            approval=APPROVAL_NONE,
            message=str(exc),
            path_rules=path_rules,
        )
    if mode == "capture":
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_PASS,
            reason_code=REASON_CODE_OK,
            message="knowledgebase snapshot captured",
            path_rules=path_rules,
            items=captured,
            summary={"file_count": len(captured)},
        )
    if snapshot_path is None:
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_MISSING_SNAPSHOT,
            message="compare mode requires --snapshot",
            path_rules=path_rules,
        )
    try:
        snapshot_file = _resolve_repo_file(normalized_repo_root, snapshot_path)
        previous_items = _load_snapshot_items(snapshot_file)
    except (ValueError, json.JSONDecodeError) as exc:
        return invalid_input_result(
            surface=SURFACE,
            mode=mode,
            approval=APPROVAL_NONE,
            message=str(exc),
            path_rules=path_rules,
        )
    previous_map = {item["path"]: item["sha256"] for item in previous_items}
    current_map = {item["path"]: item["sha256"] for item in captured}
    added = sorted(path for path in current_map if path not in previous_map)
    removed = sorted(path for path in previous_map if path not in current_map)
    changed = sorted(path for path in current_map if previous_map.get(path) not in {None, current_map[path]})
    return SurfaceResult(
        surface=SURFACE,
        mode=mode,
        status=STATUS_PASS,
        reason_code=REASON_CODE_OK,
        message="knowledgebase snapshot comparison computed",
        path_rules=path_rules,
        items=captured,
        summary={
            "file_count": len(captured),
            "added": added,
            "removed": removed,
            "changed": changed,
        },
    )


def run_cli(argv: Sequence[str] | None = None, *, output_stream: TextIO = sys.stdout) -> int:
    return run_surface_cli(
        argv=argv,
        parser_factory=_build_parser,
        path_rules_factory=_path_rules,
        surface=SURFACE,
        runner=run_snapshot,
        args_to_kwargs=lambda a: {
            "repo_root": a.repo_root,
            "mode": a.mode,
            "paths": a.path,
            "snapshot_path": a.snapshot,
        },
        output_stream=output_stream,
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
