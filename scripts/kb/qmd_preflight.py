"""Deterministic preflight checks for qmd runtime and index/resource readiness."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import sys
from typing import Callable, Sequence, TextIO


STATUS_PASS = "pass"
STATUS_FAIL = "fail"

REASON_CODE_OK = "ok"
REASON_CODE_INVALID_INPUT = "invalid_input"
REASON_CODE_PREREQ_MISSING_QMD_RUNTIME = "prereq_missing:qmd_runtime"
REASON_CODE_PREREQ_MISSING_QMD_INDEX_RESOURCE = "prereq_missing:qmd_index_resource"

DEFAULT_REQUIRED_RESOURCES: tuple[str, ...] = (".qmd/index",)


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    """Result of one deterministic preflight check."""

    check_id: str
    status: str
    reason_code: str
    message: str
    target: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "check_id": self.check_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "target": self.target,
        }


@dataclass(frozen=True, slots=True)
class PreflightReport:
    """Deterministic preflight summary payload."""

    status: str
    reason_code: str
    message: str
    checks: tuple[PreflightCheck, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "checks": [check.to_dict() for check in self.checks],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


def run_preflight(
    *,
    repo_root: str | Path = ".",
    qmd_binary: str = "qmd",
    required_resources: Sequence[str] | None = None,
    which_fn: Callable[[str], str | None] = shutil.which,
    path_exists_fn: Callable[[Path], bool] | None = None,
) -> PreflightReport:
    """Run deterministic qmd prerequisite checks without side effects."""
    exists = path_exists_fn or (lambda path: path.exists())
    normalized_repo_root = Path(repo_root).resolve()
    normalized_resources = _normalize_required_resources(required_resources)
    checks: list[PreflightCheck] = []

    if not qmd_binary.strip():
        checks.append(
            PreflightCheck(
                check_id="runtime:qmd",
                status=STATUS_FAIL,
                reason_code=REASON_CODE_INVALID_INPUT,
                message="qmd binary must be a non-empty string",
                target=qmd_binary,
            )
        )
        return _report_from_checks(checks)

    runtime_path = which_fn(qmd_binary)
    if runtime_path:
        checks.append(
            PreflightCheck(
                check_id=f"runtime:{qmd_binary}",
                status=STATUS_PASS,
                reason_code=REASON_CODE_OK,
                message=f"required runtime/tool available: {qmd_binary}",
                target=runtime_path,
            )
        )
    else:
        checks.append(
            PreflightCheck(
                check_id=f"runtime:{qmd_binary}",
                status=STATUS_FAIL,
                reason_code=REASON_CODE_PREREQ_MISSING_QMD_RUNTIME,
                message=f"required runtime/tool unavailable: {qmd_binary}",
                target=qmd_binary,
            )
        )

    for resource in normalized_resources:
        check_id = f"resource:{resource}"
        resolved_resource = _resolve_resource_path(normalized_repo_root, resource)
        if resolved_resource is None:
            checks.append(
                PreflightCheck(
                    check_id=check_id,
                    status=STATUS_FAIL,
                    reason_code=REASON_CODE_INVALID_INPUT,
                    message=f"required index/resource escapes repository: {resource}",
                    target=resource,
                )
            )
            continue

        if exists(resolved_resource):
            checks.append(
                PreflightCheck(
                    check_id=check_id,
                    status=STATUS_PASS,
                    reason_code=REASON_CODE_OK,
                    message=f"required index/resource available: {resource}",
                    target=resolved_resource.as_posix(),
                )
            )
        else:
            checks.append(
                PreflightCheck(
                    check_id=check_id,
                    status=STATUS_FAIL,
                    reason_code=REASON_CODE_PREREQ_MISSING_QMD_INDEX_RESOURCE,
                    message=f"required index/resource unavailable: {resource}",
                    target=resolved_resource.as_posix(),
                )
            )

    return _report_from_checks(checks)


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    output_stream: TextIO = sys.stdout,
    which_fn: Callable[[str], str | None] = shutil.which,
    path_exists_fn: Callable[[Path], bool] | None = None,
) -> int:
    """CLI wrapper for qmd preflight checks."""
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    report = run_preflight(
        repo_root=args.repo_root,
        qmd_binary=args.qmd_binary,
        required_resources=args.required_resources,
        which_fn=which_fn,
        path_exists_fn=path_exists_fn,
    )
    output_stream.write(report.to_json())
    output_stream.write("\n")
    return 0 if report.status == STATUS_PASS else 1


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv=argv)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic qmd runtime and index/resource preflight checks.",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root used to resolve required resource paths (default: .).",
    )
    parser.add_argument(
        "--qmd-binary",
        default="qmd",
        help="qmd binary name to resolve on PATH (default: qmd).",
    )
    parser.add_argument(
        "--required-resource",
        dest="required_resources",
        action="append",
        help=(
            "Repository-relative required index/resource path. "
            "Repeat for multiple resources. Defaults to .qmd/index."
        ),
    )
    return parser


def _normalize_required_resources(required_resources: Sequence[str] | None) -> tuple[str, ...]:
    values = required_resources if required_resources is not None else DEFAULT_REQUIRED_RESOURCES
    normalized: list[str] = []
    seen: set[str] = set()

    for value in values:
        resource = Path(value).as_posix()
        if not resource:
            continue
        if resource in seen:
            continue
        seen.add(resource)
        normalized.append(resource)

    if normalized:
        return tuple(normalized)
    return DEFAULT_REQUIRED_RESOURCES


def _resolve_resource_path(repo_root: Path, resource: str) -> Path | None:
    candidate = Path(resource)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    resolved_candidate = candidate.resolve()
    try:
        resolved_candidate.relative_to(repo_root)
    except ValueError:
        return None
    return resolved_candidate


def _report_from_checks(checks: list[PreflightCheck]) -> PreflightReport:
    first_failure = next((check for check in checks if check.status == STATUS_FAIL), None)
    if first_failure is None:
        return PreflightReport(
            status=STATUS_PASS,
            reason_code=REASON_CODE_OK,
            message="all qmd preflight checks passed",
            checks=tuple(checks),
        )
    return PreflightReport(
        status=STATUS_FAIL,
        reason_code=first_failure.reason_code,
        message=first_failure.message,
        checks=tuple(checks),
    )


__all__ = [
    "STATUS_FAIL",
    "STATUS_PASS",
    "REASON_CODE_INVALID_INPUT",
    "REASON_CODE_OK",
    "REASON_CODE_PREREQ_MISSING_QMD_INDEX_RESOURCE",
    "REASON_CODE_PREREQ_MISSING_QMD_RUNTIME",
    "DEFAULT_REQUIRED_RESOURCES",
    "PreflightCheck",
    "PreflightReport",
    "run_preflight",
    "run_cli",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
