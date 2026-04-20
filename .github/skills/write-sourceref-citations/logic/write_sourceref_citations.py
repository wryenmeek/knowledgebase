"""Deterministic canonical SourceRef citation builder."""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from enum import StrEnum
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Sequence

if __package__ in (None, ""):  # supports both 'python -m' and direct invocation without package install
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.kb import sourceref

REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_OWNER = "local"
_RAW_PATH_PREFIXES: tuple[str, ...] = ("raw/inbox/", "raw/processed/", "raw/assets/")


class CitationReasonCode(StrEnum):
    INVALID_PATH = "invalid_path"
    PATH_NOT_ALLOWLISTED = "path_not_allowlisted"
    GIT_REF_UNRESOLVED = "git_ref_unresolved"
    ARTIFACT_MISSING = "artifact_missing"
    VALIDATION_FAILED = "validation_failed"


class SourceRefCitationError(ValueError):
    def __init__(self, reason_code: CitationReasonCode | str, message: str) -> None:
        self.reason_code = str(reason_code)
        super().__init__(f"{self.reason_code}: {message}")


@dataclass(frozen=True, slots=True)
class CitationResult:
    source_ref: str
    source_path: str
    resolved_git_sha: str
    sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source_ref": self.source_ref,
            "source_path": self.source_path,
            "resolved_git_sha": self.resolved_git_sha,
            "sha256": self.sha256,
        }


def build_sourceref_citation(
    *,
    source_path: str | Path,
    anchor: str,
    git_ref: str,
    repo_root: str | Path = REPO_ROOT,
    repo_owner: str = REPO_OWNER,
    repo_name: str | None = None,
) -> CitationResult:
    normalized_path = _normalize_source_path(source_path)
    if not any(normalized_path.startswith(prefix) for prefix in _RAW_PATH_PREFIXES):
        raise SourceRefCitationError(
            CitationReasonCode.PATH_NOT_ALLOWLISTED,
            "SourceRef citation paths must stay under raw/inbox/**, raw/processed/**, or raw/assets/**",
        )

    normalized_repo_root = Path(repo_root).resolve()
    resolved_repo_name = repo_name or _default_repo_name(normalized_repo_root)
    resolved_git_sha = _resolve_git_ref(normalized_repo_root, git_ref)
    artifact_bytes = _read_revision_bytes(
        normalized_repo_root,
        resolved_git_sha=resolved_git_sha,
        source_path=normalized_path,
    )
    checksum = hashlib.sha256(artifact_bytes).hexdigest()
    source_ref_value = (
        f"repo://{repo_owner}/{resolved_repo_name}/{normalized_path}"
        f"@{resolved_git_sha}#{anchor}?sha256={checksum}"
    )

    try:
        sourceref.validate_sourceref(
            source_ref_value,
            authoritative=True,
            repo_root=normalized_repo_root,
            expected_owner=repo_owner,
            expected_repo=resolved_repo_name,
        )
    except sourceref.SourceRefValidationError as exc:
        raise SourceRefCitationError(CitationReasonCode.VALIDATION_FAILED, str(exc)) from exc

    return CitationResult(
        source_ref=source_ref_value,
        source_path=normalized_path,
        resolved_git_sha=resolved_git_sha,
        sha256=checksum,
    )


def _normalize_source_path(value: str | Path) -> str:
    raw_value = value.as_posix() if isinstance(value, Path) else str(value)
    if not raw_value or raw_value.startswith("/") or "\\" in raw_value:
        raise SourceRefCitationError(
            CitationReasonCode.INVALID_PATH,
            "source path must be a repository-relative POSIX path",
        )
    if "//" in raw_value:
        raise SourceRefCitationError(
            CitationReasonCode.INVALID_PATH,
            "source path must not contain empty path segments",
        )
    raw_parts = raw_value.split("/")
    if any(part in {"", "."} for part in raw_parts):
        raise SourceRefCitationError(
            CitationReasonCode.INVALID_PATH,
            "source path must not contain non-canonical path segments",
        )
    if any(part == ".." for part in raw_parts):
        raise SourceRefCitationError(
            CitationReasonCode.INVALID_PATH,
            "source path must not contain traversal segments",
        )
    return PurePosixPath(raw_value).as_posix()


def _default_repo_name(repo_root: Path) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "-", repo_root.name) or "repo"


def _resolve_git_ref(repo_root: Path, git_ref: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", f"{git_ref}^{{commit}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise SourceRefCitationError(
            CitationReasonCode.GIT_REF_UNRESOLVED,
            "git ref must resolve to a real commit revision",
        )
    resolved = completed.stdout.strip()
    if not resolved:
        raise SourceRefCitationError(
            CitationReasonCode.GIT_REF_UNRESOLVED,
            "git ref resolved to an empty revision",
        )
    return resolved


def _read_revision_bytes(repo_root: Path, *, resolved_git_sha: str, source_path: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{resolved_git_sha}:{source_path}"],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise SourceRefCitationError(
            CitationReasonCode.ARTIFACT_MISSING,
            "artifact must exist at the referenced git revision",
        )
    return completed.stdout


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a canonical authoritative SourceRef citation.")
    parser.add_argument("--path", required=True)
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--git-ref", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = build_sourceref_citation(
            source_path=args.path,
            anchor=args.anchor,
            git_ref=args.git_ref,
        )
    except SourceRefCitationError as exc:
        print(json.dumps({"reason_code": exc.reason_code, "message": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
