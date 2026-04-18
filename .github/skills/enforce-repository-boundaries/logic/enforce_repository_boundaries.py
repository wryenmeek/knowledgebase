"""Deterministic repository boundary checks for knowledgebase paths."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import StrEnum
import fnmatch
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.kb import contracts, path_utils

REPO_ROOT = Path(__file__).resolve().parents[4]
WRITE_ALLOWLIST_GLOBS: tuple[str, ...] = contracts.WRITE_ALLOWLIST_PATHS
READ_ALLOWLIST_PREFIXES: tuple[str, ...] = (
    ".github/agents/",
    ".github/skills/",
    "raw/assets/",
    "raw/inbox/",
    "raw/processed/",
    "schema/",
    "scripts/kb/",
    "tests/kb/",
    "wiki/",
)
READ_ALLOWLIST_FILES: tuple[str, ...] = (
    "AGENTS.md",
    "docs/architecture.md",
    "docs/decisions/ADR-007-control-plane-layering-and-packaging.md",
    "docs/ideas/wiki-curation-agent-framework.md",
    "docs/mvp-runbook.md",
    "raw/processed/SPEC.md",
)


class AccessMode(StrEnum):
    READ = "read"
    WRITE = "write"


class BoundaryReasonCode(StrEnum):
    OK = "ok"
    INVALID_PATH = "invalid_path"
    PATH_TRAVERSAL = "path_traversal"
    PATH_NOT_ALLOWLISTED = "path_not_allowlisted"


@dataclass(frozen=True, slots=True)
class BoundaryDecision:
    path: str
    mode: str
    allowed: bool
    reason_code: str

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "path": self.path,
            "mode": self.mode,
            "allowed": self.allowed,
            "reason_code": self.reason_code,
        }


def normalize_repo_relative_path(value: str | Path) -> tuple[str, str]:
    normalized, error_kind = path_utils.try_normalize_repo_relative_path(value)
    if error_kind == path_utils.ERROR_KIND_PATH_TRAVERSAL:
        return normalized, BoundaryReasonCode.PATH_TRAVERSAL.value
    if error_kind == path_utils.ERROR_KIND_INVALID_PATH:
        return normalized, BoundaryReasonCode.INVALID_PATH.value
    return normalized, BoundaryReasonCode.OK.value


def enforce_repository_boundary(path: str | Path, *, mode: AccessMode) -> BoundaryDecision:
    normalized, normalization_reason = normalize_repo_relative_path(path)
    if normalization_reason != BoundaryReasonCode.OK.value:
        return BoundaryDecision(
            path=normalized,
            mode=mode.value,
            allowed=False,
            reason_code=normalization_reason,
        )

    allowed = _is_allowlisted(normalized, mode=mode)
    return BoundaryDecision(
        path=normalized,
        mode=mode.value,
        allowed=allowed,
        reason_code=BoundaryReasonCode.OK.value if allowed else BoundaryReasonCode.PATH_NOT_ALLOWLISTED.value,
    )


def _is_allowlisted(path: str, *, mode: AccessMode) -> bool:
    if mode is AccessMode.WRITE:
        return any(fnmatch.fnmatch(path, pattern) for pattern in WRITE_ALLOWLIST_GLOBS)

    if path in READ_ALLOWLIST_FILES:
        return True
    return any(path.startswith(prefix) for prefix in READ_ALLOWLIST_PREFIXES)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check a repository-relative path against fixed knowledgebase boundaries."
    )
    parser.add_argument("--mode", choices=tuple(mode.value for mode in AccessMode), required=True)
    parser.add_argument("--path", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    decision = enforce_repository_boundary(args.path, mode=AccessMode(args.mode))
    print(json.dumps(decision.to_dict(), sort_keys=True))
    return 0 if decision.allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())
