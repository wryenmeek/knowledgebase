"""Read-only scaffold for auditing knowledgebase workspace customizations.

Phase 3 intentionally performs no classification and no mutation. The default
flow preserves the existing structural-lint audit contract, while the `improve`
flow remains a dry-run scaffold. It returns an empty findings list by default
and can route caller-supplied classifier findings into read-only OutOfBand
handoff records. Apply mode validates future write targets and acquires
`.github/.customizations.lock` when the caller supplies approved approval.
"""

from __future__ import annotations

import argparse
import contextlib
from collections.abc import Mapping
from dataclasses import dataclass
import fcntl
import os
from pathlib import Path
from pathlib import PurePosixPath
import sys
from typing import Any, Sequence, TextIO

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from outofband_handoff import OutOfBandRoutingError, route_findings
except ImportError:  # pragma: no cover - exercised when imported as a package
    from .outofband_handoff import OutOfBandRoutingError, route_findings

from scripts._optional_surface_common import (
    APPROVAL_APPROVED,
    APPROVAL_NONE,
    JsonArgumentParser,
    REASON_CODE_INVALID_INPUT,
    REASON_CODE_OK,
    STATUS_FAIL,
    STATUS_PASS,
    SurfaceResult,
    looks_like_repo_root,
    repo_root_failure,
    run_surface_cli,
)
from scripts.kb import contracts, write_utils

SURFACE = ".github/skills/audit-knowledgebase-workspace/logic/audit_workspace.py"
SUPPORTED_MODES: tuple[str, ...] = ("default", "improve", "apply")
APPLY_OPERATION_CREATE = "create"
APPLY_OPERATION_MODIFY = "modify"
APPLY_OPERATIONS: tuple[str, ...] = (APPLY_OPERATION_CREATE, APPLY_OPERATION_MODIFY)
REASON_CODE_PATH_NOT_ALLOWLISTED = "path_not_allowlisted"
APPLY_REASON_OUTSIDE_ALLOWLIST = "outside_allowlist"
APPLY_REASON_CROSS_SKILL_FINDING = "cross_skill_finding"
APPLY_CREATE_ONLY_ROOTS: tuple[str, ...] = (
    ".github/instructions",
    ".github/hooks",
)
APPLY_MODIFY_ONLY_PATHS: tuple[str, ...] = (
    ".github/copilot-instructions.md",
    "AGENTS.md",
)
APPLY_SELF_OWNED_MODIFY_ROOT = ".github/skills/audit-knowledgebase-workspace"
APPLY_CROSS_SKILL_ROOTS: tuple[str, ...] = (
    ".github/agents",
    ".github/prompts",
)
APPLY_SIBLING_LOCK_PATHS: tuple[str, ...] = (
    contracts.WRITE_LOCK_PATH,
    contracts.REJECTION_REGISTRY_LOCK_PATH,
)


@dataclass(frozen=True, slots=True)
class ApplyTargetDecision:
    path: str
    operation: str
    allowed: bool
    reason_code: str
    message: str

    def to_item(self) -> dict[str, object]:
        return {
            "path": self.path,
            "operation": self.operation,
            "status": STATUS_PASS if self.allowed else STATUS_FAIL,
            "reason_code": self.reason_code,
            "message": self.message,
        }


def _path_rules() -> dict[str, object]:
    return {
        "allowed_roots": [
            ".github/copilot-instructions.md",
            ".github/agents",
            ".github/prompts",
            ".github/skills",
            ".github/hooks",
            "AGENTS.md",
            "tests/kb",
        ],
        "direct_writes_declared": False,
        "read_only": True,
        "writable_paths": [],
        "writes_forbidden": True,
    }


def _apply_path_rules() -> dict[str, object]:
    return {
        "allowed_roots": [
            ".github/copilot-instructions.md",
            ".github/instructions",
            ".github/hooks",
            ".github/skills/audit-knowledgebase-workspace",
            "AGENTS.md",
        ],
        "create_only_paths": [
            ".github/instructions/**/*.instructions.md",
            ".github/hooks/**",
        ],
        "modify_only_paths": [
            ".github/copilot-instructions.md",
            "AGENTS.md",
            ".github/skills/audit-knowledgebase-workspace/**",
        ],
        "forbidden_paths": [
            ".github/skills/<other-skill>/**",
            ".github/agents/**",
            ".github/prompts/**",
            "wiki/**",
            "raw/**",
            "schema/**",
            "scripts/**",
            "tests/**",
            "docs/**",
        ],
        "deny_by_default": True,
        "repo_local_only": True,
        "write_path_validation_only": True,
        "lock_required": "when --approval approved",
        "customizations_lock_path": contracts.CUSTOMIZATIONS_LOCK_PATH,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description="Run the read-only audit-knowledgebase-workspace scaffold."
    )
    parser.add_argument(
        "--mode",
        choices=SUPPORTED_MODES,
        default="default",
        help=(
            "default: compatibility scaffold; improve: dry-run scaffold with empty findings "
            "unless caller-supplied findings are routed; "
            "apply: validate caller-provided write targets only."
        ),
    )
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument(
        "--approval",
        choices=(APPROVAL_NONE, APPROVAL_APPROVED),
        default=APPROVAL_NONE,
        help=(
            "'approved' is reserved for apply-mode validation scaffolding; "
            "it acquires the customizations lock but performs no writes."
        ),
    )
    parser.add_argument(
        "--apply-target",
        action="append",
        default=None,
        help="Repo-relative target path to validate in apply mode. May be repeated.",
    )
    parser.add_argument(
        "--apply-operation",
        choices=APPLY_OPERATIONS,
        default=None,
        help="Optional operation override for all --apply-target values; otherwise inferred.",
    )
    return parser


def _path_matches_root(path: str, root: str) -> bool:
    candidate = PurePosixPath(path)
    root_path = PurePosixPath(root)
    return candidate == root_path or candidate.is_relative_to(root_path)


def _normalize_apply_target_path(repo_root: Path, raw_path: str) -> tuple[str, Path] | str:
    normalized = raw_path.strip()
    if not normalized:
        return "path values must be non-empty repo-relative paths"
    candidate = Path(normalized)
    if candidate.is_absolute():
        return f"path must be repo-relative: {normalized}"
    if any(part in ("", ".", "..") for part in candidate.parts):
        return f"path contains a forbidden path segment: {normalized}"

    current = repo_root
    try:
        for part in candidate.parts:
            current = current / part
            if current.exists() or current.is_symlink():
                write_utils.check_no_symlink_path(current)
    except OSError as exc:
        return str(exc)

    resolved = (repo_root / candidate).resolve(strict=False)
    if not resolved.is_relative_to(repo_root):
        return f"path escapes repository root: {normalized}"
    return resolved.relative_to(repo_root).as_posix(), resolved


def _apply_denied(
    *,
    target_path: str,
    operation: str,
    reason_code: str,
    message: str,
) -> ApplyTargetDecision:
    return ApplyTargetDecision(
        path=target_path,
        operation=operation,
        allowed=False,
        reason_code=reason_code,
        message=message,
    )


def validate_apply_target_path(
    repo_root: str | Path,
    target_path: str,
    *,
    operation: str | None = None,
) -> ApplyTargetDecision:
    """Validate one future apply-mode target against the Q12 allowlist.

    This performs no writes and acquires no locks. It is the single
    deny-by-default gate that future apply writers must call before mutation.
    """

    repo_root_path = Path(repo_root).resolve()
    normalized = _normalize_apply_target_path(repo_root_path, target_path)
    inferred_operation = operation or APPLY_OPERATION_CREATE
    if isinstance(normalized, str):
        return _apply_denied(
            target_path=target_path,
            operation=inferred_operation,
            reason_code=APPLY_REASON_OUTSIDE_ALLOWLIST,
            message=normalized,
        )

    canonical_path, resolved_path = normalized
    inferred_operation = operation or (
        APPLY_OPERATION_MODIFY if resolved_path.exists() else APPLY_OPERATION_CREATE
    )
    if inferred_operation not in APPLY_OPERATIONS:
        return _apply_denied(
            target_path=canonical_path,
            operation=inferred_operation,
            reason_code=APPLY_REASON_OUTSIDE_ALLOWLIST,
            message=f"unsupported apply operation: {inferred_operation}",
        )

    if (
        _path_matches_root(canonical_path, ".github/skills")
        and not _path_matches_root(canonical_path, APPLY_SELF_OWNED_MODIFY_ROOT)
    ) or any(_path_matches_root(canonical_path, root) for root in APPLY_CROSS_SKILL_ROOTS):
        return _apply_denied(
            target_path=canonical_path,
            operation=inferred_operation,
            reason_code=APPLY_REASON_CROSS_SKILL_FINDING,
            message="cross-skill or persona/prompt findings must route OutOfBand",
        )

    if inferred_operation == APPLY_OPERATION_CREATE and resolved_path.exists():
        return _apply_denied(
            target_path=canonical_path,
            operation=inferred_operation,
            reason_code=APPLY_REASON_OUTSIDE_ALLOWLIST,
            message="create-only apply target already exists",
        )
    if inferred_operation == APPLY_OPERATION_MODIFY and not resolved_path.exists():
        return _apply_denied(
            target_path=canonical_path,
            operation=inferred_operation,
            reason_code=APPLY_REASON_OUTSIDE_ALLOWLIST,
            message="modify-only apply target does not exist",
        )

    create_root_allowed = any(
        _path_matches_root(canonical_path, root) for root in APPLY_CREATE_ONLY_ROOTS
    )
    create_allowed = (
        inferred_operation == APPLY_OPERATION_CREATE
        and create_root_allowed
        and (
            not _path_matches_root(canonical_path, ".github/instructions")
            or canonical_path.endswith(".instructions.md")
        )
    )
    modify_allowed = (
        inferred_operation == APPLY_OPERATION_MODIFY
        and (
            canonical_path in APPLY_MODIFY_ONLY_PATHS
            or _path_matches_root(canonical_path, APPLY_SELF_OWNED_MODIFY_ROOT)
        )
    )
    if not (create_allowed or modify_allowed):
        return _apply_denied(
            target_path=canonical_path,
            operation=inferred_operation,
            reason_code=APPLY_REASON_OUTSIDE_ALLOWLIST,
            message="apply target is outside the declared write allowlist",
        )

    return ApplyTargetDecision(
        path=canonical_path,
        operation=inferred_operation,
        allowed=True,
        reason_code=REASON_CODE_OK,
        message="apply target is within the declared write allowlist",
    )


def _apply_result(
    *,
    normalized_repo_root: Path,
    approval: str,
    path_rules: dict[str, object],
    apply_targets: Sequence[str],
    apply_operation: str | None,
    lock_acquired: bool,
) -> SurfaceResult:
    decisions = tuple(
        validate_apply_target_path(
            normalized_repo_root,
            target,
            operation=apply_operation,
        )
        for target in apply_targets
    )
    failed = tuple(decision for decision in decisions if not decision.allowed)
    lock_required = approval == APPROVAL_APPROVED
    return SurfaceResult(
        surface=SURFACE,
        mode="apply",
        status=STATUS_FAIL if failed else STATUS_PASS,
        reason_code=REASON_CODE_PATH_NOT_ALLOWLISTED if failed else REASON_CODE_OK,
        message=(
            "one or more apply targets are outside the declared write allowlist"
            if failed
            else "apply scaffold validated caller-provided target paths; no writes performed"
        ),
        approval=approval,
        lock_path=contracts.CUSTOMIZATIONS_LOCK_PATH if lock_required else None,
        lock_required=lock_required,
        path_rules=path_rules,
        items=tuple(decision.to_item() for decision in decisions),
        summary={
            "write_targets_validated": len(decisions),
            "write_targets_allowed": len(decisions) - len(failed),
            "write_targets_rejected": len(failed),
            "writes_attempted": 0,
            "writes_performed": 0,
            "lock_acquired": lock_acquired,
            "lock_path": contracts.CUSTOMIZATIONS_LOCK_PATH if lock_required else None,
        },
    )


def _active_sibling_lock_path(repo_root: Path) -> str | None:
    for lock_path in APPLY_SIBLING_LOCK_PATHS:
        if write_utils.is_write_lock_held(repo_root, lock_path=lock_path):
            return lock_path
        abs_lock = repo_root / lock_path
        if not (abs_lock.exists() or abs_lock.is_symlink()):
            continue
        try:
            write_utils.check_no_symlink_path(abs_lock)
            resolved_lock = abs_lock.resolve(strict=False)
            if not resolved_lock.is_relative_to(repo_root):
                return lock_path
            flags = os.O_RDWR
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(abs_lock, flags)
        except FileNotFoundError:
            continue
        except OSError:
            return lock_path

        with os.fdopen(fd, "a+", encoding="utf-8") as lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return lock_path
            finally:
                with contextlib.suppress(OSError):
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    return None


def _apply_lock_unavailable_result(
    *,
    approval: str,
    path_rules: dict[str, object],
    message: str,
    sibling_lock_path: str | None = None,
) -> SurfaceResult:
    summary: dict[str, object] = {
        "write_targets_validated": 0,
        "write_targets_allowed": 0,
        "write_targets_rejected": 0,
        "writes_attempted": 0,
        "writes_performed": 0,
        "lock_acquired": False,
        "lock_path": contracts.CUSTOMIZATIONS_LOCK_PATH,
    }
    if sibling_lock_path is not None:
        summary["sibling_lock_held"] = sibling_lock_path

    return SurfaceResult(
        surface=SURFACE,
        mode="apply",
        status=STATUS_FAIL,
        reason_code=contracts.ReasonCode.LOCK_UNAVAILABLE.value,
        message=message,
        approval=approval,
        lock_path=contracts.CUSTOMIZATIONS_LOCK_PATH,
        lock_required=True,
        path_rules=path_rules,
        summary=summary,
    )


def audit(
    *,
    repo_root: str | Path = ".",
    mode: str = "default",
    approval: str = APPROVAL_NONE,
    classifier_findings: Sequence[Mapping[str, Any]] | None = None,
    apply_targets: Sequence[str] = (),
    apply_operation: str | None = None,
) -> SurfaceResult:
    """Return a read-only audit result with zero writes attempted."""

    path_rules = _apply_path_rules() if mode == "apply" else _path_rules()
    if approval not in (APPROVAL_NONE, APPROVAL_APPROVED):
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_INVALID_INPUT,
            message=f"unsupported approval: {approval}",
            approval=APPROVAL_NONE,
            path_rules=path_rules,
        )
    if approval != APPROVAL_NONE and mode != "apply":
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_INVALID_INPUT,
            message="approval is not accepted by this read-only scaffold",
            approval=APPROVAL_NONE,
            path_rules=path_rules,
        )
    if mode not in SUPPORTED_MODES:
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_INVALID_INPUT,
            message=f"unsupported mode: {mode}",
            approval=approval,
            path_rules=path_rules,
        )

    normalized_repo_root = Path(repo_root).resolve()
    if not looks_like_repo_root(normalized_repo_root):
        return repo_root_failure(
            surface=SURFACE,
            mode=mode,
            approval=approval,
            path_rules=path_rules,
        )

    if mode == "apply":
        if approval == APPROVAL_APPROVED:
            sibling_lock_path = _active_sibling_lock_path(normalized_repo_root)
            if sibling_lock_path is not None:
                return _apply_lock_unavailable_result(
                    approval=approval,
                    path_rules=path_rules,
                    message=(
                        "cannot acquire customizations lock while sibling "
                        f"governance lock is held: {sibling_lock_path}"
                    ),
                    sibling_lock_path=sibling_lock_path,
                )
            try:
                with write_utils.exclusive_write_lock(
                    normalized_repo_root,
                    lock_path=contracts.CUSTOMIZATIONS_LOCK_PATH,
                ):
                    return _apply_result(
                        normalized_repo_root=normalized_repo_root,
                        approval=approval,
                        path_rules=path_rules,
                        apply_targets=apply_targets,
                        apply_operation=apply_operation,
                        lock_acquired=True,
                    )
            except write_utils.LockUnavailableError as exc:
                return _apply_lock_unavailable_result(
                    approval=approval,
                    path_rules=path_rules,
                    message=str(exc),
                )

        return _apply_result(
            normalized_repo_root=normalized_repo_root,
            approval=approval,
            path_rules=path_rules,
            apply_targets=apply_targets,
            apply_operation=apply_operation,
            lock_acquired=False,
        )

    if apply_targets:
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_INVALID_INPUT,
            message="--apply-target is only valid with --mode apply",
            approval=approval,
            path_rules=path_rules,
        )

    try:
        routed_findings = route_findings(
            tuple(classifier_findings or ()),
            repo_root=normalized_repo_root,
        )
    except OutOfBandRoutingError as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_INVALID_INPUT,
            message=f"finding routing failed closed: {exc}",
            approval=approval,
            path_rules=path_rules,
        )

    findings = [dict(finding) for finding in routed_findings.eligible_findings]
    out_of_band_handoffs = [
        dict(handoff) for handoff in routed_findings.out_of_band_handoffs
    ]
    message = (
        "default structural lint remains external; compatibility scaffold returned empty findings"
        if mode == "default"
        else "improve dry-run scaffold completed with routed findings"
    )
    return SurfaceResult(
        surface=SURFACE,
        mode=mode,
        status=STATUS_PASS,
        reason_code=REASON_CODE_OK,
        message=message,
        approval=approval,
        path_rules=path_rules,
        items=(),
        summary={
            "findings": findings,
            "finding_count": len(findings),
            "out_of_band_handoffs": out_of_band_handoffs,
            "out_of_band_handoff_count": len(out_of_band_handoffs),
            "writes_attempted": 0,
            "dry_run": True,
            "read_only": True,
            "structural_lint_executed": False,
        },
    )


def run_cli(argv: Sequence[str] | None = None, *, output_stream: TextIO = sys.stdout) -> int:
    return run_surface_cli(
        argv=argv,
        parser_factory=_build_parser,
        path_rules_factory=_path_rules,
        surface=SURFACE,
        runner=audit,
        args_to_kwargs=lambda a: {
            "repo_root": a.repo_root,
            "mode": a.mode,
            "approval": a.approval,
            "apply_targets": tuple(a.apply_target or ()),
            "apply_operation": a.apply_operation,
        },
        output_stream=output_stream,
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv=argv)


__all__ = [
    "SURFACE",
    "SUPPORTED_MODES",
    "ApplyTargetDecision",
    "audit",
    "validate_apply_target_path",
    "run_cli",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
