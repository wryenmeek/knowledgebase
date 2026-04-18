"""Shared helpers for approval-gated optional script surfaces."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable, Sequence, TextIO, TypedDict

STATUS_PASS = "pass"
STATUS_FAIL = "fail"

REASON_CODE_OK = "ok"
REASON_CODE_INVALID_INPUT = "invalid_input"
# Note: scripts/kb/qmd_preflight.py independently defines analogous STATUS_PASS / STATUS_FAIL
# and REASON_CODE_OK / REASON_CODE_INVALID_INPUT constants. This is intentional: qmd_preflight
# is a core scripts/kb/ module deployed in isolation (fixture repos copy only scripts/kb/) and
# cannot import from the broader scripts/ package. Do not "unify" across that boundary.
REASON_CODE_PREREQ_MISSING_REPO_ROOT = "prereq_missing:repo_root"
REASON_CODE_APPROVAL_REQUIRED = "approval_required"
REASON_CODE_WRITE_SURFACE_NOT_DECLARED = "write_surface_not_declared"
REASON_CODE_UNSUPPORTED_SOURCE_TYPE = "unsupported_source_type"
REASON_CODE_MISSING_SNAPSHOT = "missing_snapshot"

APPROVAL_NONE = "none"
APPROVAL_APPROVED = "approved"
LOCK_PATH = "wiki/.kb_write.lock"
PLACEHOLDER_MARKERS: tuple[str, ...] = (
    "{{fill}}",
    "TODO",
    "TBD",
    "[context-needed]",
)


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


class SurfaceItem(TypedDict, total=False):
    """Expected shape of each item in ``SurfaceResult.items``.

    All items carry the four required fields; surface-specific keys are optional.
    Callers may include additional keys — the TypedDict documents the common schema
    without enforcing it at runtime.

    Required fields (always present):
        path:        Repo-relative path of the file being assessed.
        status:      ``STATUS_PASS`` or ``STATUS_FAIL``.
        reason_code: A stable machine-readable code from the surface's reason-code set.
        message:     Human-readable description of the result.
    """

    path: str
    status: str
    reason_code: str
    message: str


@dataclass(frozen=True, slots=True)
class SurfaceResult:
    surface: str
    mode: str
    status: str
    reason_code: str
    message: str
    approval: str = APPROVAL_NONE
    lock_path: str | None = None
    lock_required: bool = False
    path_rules: dict[str, Any] = field(default_factory=dict)
    items: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "surface": self.surface,
            "mode": self.mode,
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "approval": self.approval,
            "lock_path": self.lock_path,
            "lock_required": self.lock_required,
            "path_rules": self.path_rules,
            "items": [dict(item) for item in self.items],
            "summary": dict(self.summary),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


def looks_like_repo_root(repo_root: Path) -> bool:
    return repo_root.is_dir() and (repo_root / "AGENTS.md").is_file()


def base_path_rules(
    *,
    allowed_roots: Sequence[str],
    allowed_suffixes: Sequence[str] | None,
) -> dict[str, Any]:
    return {
        "allowlisted_roots": list(allowed_roots),
        "allowed_suffixes": list(allowed_suffixes or ()),
        "deny_by_default": True,
        "repo_local_only": True,
    }


def repo_root_failure(
    *,
    surface: str,
    mode: str,
    approval: str,
    path_rules: dict[str, Any],
) -> SurfaceResult:
    return SurfaceResult(
        surface=surface,
        mode=mode,
        status=STATUS_FAIL,
        reason_code=REASON_CODE_PREREQ_MISSING_REPO_ROOT,
        message="repository root must exist and contain AGENTS.md",
        approval=approval,
        path_rules=path_rules,
    )


def invalid_input_result(
    *,
    surface: str,
    mode: str,
    approval: str,
    message: str,
    path_rules: dict[str, Any],
) -> SurfaceResult:
    return SurfaceResult(
        surface=surface,
        mode=mode,
        status=STATUS_FAIL,
        reason_code=REASON_CODE_INVALID_INPUT,
        message=message,
        approval=approval,
        path_rules=path_rules,
    )


def approval_required_result(
    *,
    surface: str,
    mode: str,
    path_rules: dict[str, Any],
    lock_required: bool,
) -> SurfaceResult:
    return SurfaceResult(
        surface=surface,
        mode=mode,
        status=STATUS_FAIL,
        reason_code=REASON_CODE_APPROVAL_REQUIRED,
        message="write-capable mode is disabled until explicit later-phase approval is supplied",
        approval=APPROVAL_NONE,
        lock_path=LOCK_PATH if lock_required else None,
        lock_required=lock_required,
        path_rules=path_rules,
    )


def write_surface_not_declared_result(
    *,
    surface: str,
    mode: str,
    approval: str,
    path_rules: dict[str, Any],
    lock_required: bool,
    message: str,
) -> SurfaceResult:
    return SurfaceResult(
        surface=surface,
        mode=mode,
        status=STATUS_FAIL,
        reason_code=REASON_CODE_WRITE_SURFACE_NOT_DECLARED,
        message=message,
        approval=approval,
        lock_path=LOCK_PATH if lock_required else None,
        lock_required=lock_required,
        path_rules=path_rules,
    )


def _ensure_safe_relative_path(
    repo_root: Path,
    raw_path: str,
    *,
    allowed_roots: Sequence[str],
) -> Path:
    normalized = raw_path.strip()
    if not normalized:
        raise ValueError("path values must be non-empty repo-relative paths")
    candidate = Path(normalized)
    if candidate.is_absolute():
        raise ValueError(f"path must be repo-relative: {normalized}")
    current = repo_root
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"path must not use symlinks: {normalized}")
    resolved = (repo_root / candidate).resolve()
    if not resolved.is_relative_to(repo_root):
        raise ValueError(f"path escapes repository root: {normalized}")
    allowed_root_paths = tuple((repo_root / root).resolve() for root in allowed_roots)
    if not any(resolved == root or resolved.is_relative_to(root) for root in allowed_root_paths):
        raise ValueError(f"path is outside the declared scope: {normalized}")
    if not resolved.exists():
        raise ValueError(f"path does not exist: {normalized}")
    return resolved


def expand_repo_paths(
    repo_root: Path,
    raw_paths: Sequence[str],
    *,
    allowed_roots: Sequence[str],
    allowed_suffixes: Sequence[str] | None = None,
    default_roots: Sequence[str] | None = None,
) -> tuple[Path, ...]:
    selected: list[Path] = []
    seen: set[Path] = set()
    requested_paths = list(raw_paths) if raw_paths else list(default_roots or allowed_roots)
    normalized_suffixes = {suffix.lower() for suffix in (allowed_suffixes or ())}
    for raw_path in requested_paths:
        resolved = _ensure_safe_relative_path(repo_root, raw_path, allowed_roots=allowed_roots)
        iterator = sorted(path.resolve() for path in resolved.rglob("*") if path.is_file()) if resolved.is_dir() else [resolved]
        for path in iterator:
            relative = path.relative_to(repo_root)
            current = repo_root
            for part in relative.parts:
                current = current / part
                if current.is_symlink():
                    raise ValueError(f"path must not use symlinks: {relative.as_posix()}")
            if normalized_suffixes and path.suffix.lower() not in normalized_suffixes:
                continue
            if path in seen:
                continue
            seen.add(path)
            selected.append(path)
    if not selected:
        raise ValueError("no files matched the declared path rules")
    return tuple(sorted(selected))


def repo_relative(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_placeholders(text: str) -> int:
    return sum(text.count(marker) for marker in PLACEHOLDER_MARKERS)


def add_common_surface_args(
    parser: argparse.ArgumentParser,
    *,
    modes: Sequence[str],
    default_mode: str,
    include_path: bool = True,
    include_approval: bool = True,
) -> None:
    """Attach the common surface CLI flags shared across optional script surfaces."""

    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--mode", choices=tuple(modes), default=default_mode)
    if include_path:
        parser.add_argument("--path", action="append", default=[])
    if include_approval:
        parser.add_argument(
            "--approval",
            choices=(APPROVAL_NONE, APPROVAL_APPROVED),
            default=APPROVAL_NONE,
        )


def run_surface_cli(
    *,
    argv: Sequence[str] | None,
    parser_factory: Callable[[], argparse.ArgumentParser],
    path_rules_factory: Callable[[], dict[str, Any]],
    surface: str,
    runner: Callable[..., SurfaceResult],
    args_to_kwargs: Callable[[argparse.Namespace], dict[str, Any]],
    output_stream: TextIO = sys.stdout,
) -> int:
    """Shared CLI shell: parse args, invoke runner, emit canonical JSON, return exit code."""

    try:
        args = parser_factory().parse_args(list(argv) if argv is not None else None)
    except ValueError as exc:
        result = invalid_input_result(
            surface=surface,
            mode="unknown",
            approval=APPROVAL_NONE,
            message=str(exc),
            path_rules=path_rules_factory(),
        )
        output_stream.write(result.to_json() + "\n")
        return 1
    result = runner(**args_to_kwargs(args))
    output_stream.write(result.to_json() + "\n")
    return 0 if result.status == STATUS_PASS else 1
