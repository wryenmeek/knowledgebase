"""Deterministic SourceRef parser and validator."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import re
import subprocess
from typing import Callable


_OWNER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_REPO_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_GIT_SHA_RE = re.compile(r"[0-9a-f]{7,40}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_ANCHOR_RE = re.compile(r"(?:asset|L\d+(?:-L\d+)?|[A-Za-z0-9][A-Za-z0-9._:-]*)\Z")
_ALLOWED_PREFIXES: tuple[tuple[str, str], ...] = (
    ("raw", "inbox"),
    ("raw", "processed"),
    ("raw", "assets"),
)


class SourceRefReasonCode(StrEnum):
    """Stable reason codes for SourceRef validation failures."""

    INVALID_SCHEME = "invalid_scheme"
    INVALID_STRUCTURE = "invalid_structure"
    INVALID_OWNER = "invalid_owner"
    INVALID_REPO = "invalid_repo"
    INVALID_PATH = "invalid_path"
    PATH_NOT_ALLOWLISTED = "path_not_allowlisted"
    PATH_TRAVERSAL = "path_traversal"
    INVALID_GIT_SHA = "invalid_git_sha"
    MISSING_ANCHOR = "missing_anchor"
    INVALID_ANCHOR = "invalid_anchor"
    MISSING_CHECKSUM = "missing_checksum"
    INVALID_CHECKSUM = "invalid_checksum"
    INVALID_FORMAT = "invalid_format"
    PLACEHOLDER_GIT_SHA = "placeholder_git_sha"
    GIT_REVISION_MISSING = "git_revision_missing"
    GIT_OPERATION_FAILED = "git_operation_failed"
    ARTIFACT_MISSING = "artifact_missing"
    ARTIFACT_NOT_FILE = "artifact_not_file"
    SYMLINKED_ARTIFACT = "symlinked_artifact"
    CHECKSUM_MISMATCH = "checksum_mismatch"


class SourceRefValidationError(ValueError):
    """Raised when a SourceRef fails canonical parsing/validation."""

    def __init__(self, reason_code: SourceRefReasonCode | str, message: str) -> None:
        self.reason_code = str(reason_code)
        super().__init__(f"{self.reason_code}: {message}")


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Canonical SourceRef components."""

    owner: str
    repo: str
    path: str
    git_sha: str
    anchor: str
    sha256: str

    def to_canonical(self) -> str:
        """Render canonical SourceRef string."""
        return (
            f"repo://{self.owner}/{self.repo}/{self.path}@{self.git_sha}"
            f"#{self.anchor}?sha256={self.sha256}"
        )


def parse_sourceref(value: str) -> SourceRef:
    """Parse and validate a canonical SourceRef string."""
    if not isinstance(value, str) or not value:
        _raise(SourceRefReasonCode.INVALID_STRUCTURE, "SourceRef must be a non-empty string")

    if not value.startswith("repo://"):
        _raise(SourceRefReasonCode.INVALID_SCHEME, "SourceRef must start with repo://")
    remainder = value[len("repo://") :]

    pre_query, has_query, query = remainder.partition("?")
    if not has_query:
        _raise(
            SourceRefReasonCode.MISSING_CHECKSUM,
            "SourceRef must include ?sha256=<64-hex>",
        )
    if not query.startswith("sha256=") or "&" in query:
        _raise(
            SourceRefReasonCode.INVALID_CHECKSUM,
            "SourceRef query must be exactly sha256=<64-hex>",
        )
    checksum = query[len("sha256=") :]
    if not _SHA256_RE.fullmatch(checksum):
        _raise(
            SourceRefReasonCode.INVALID_CHECKSUM,
            "Checksum must be 64 lowercase hexadecimal characters",
        )

    pre_anchor, has_anchor, anchor = pre_query.partition("#")
    if not has_anchor or not anchor:
        _raise(SourceRefReasonCode.MISSING_ANCHOR, "SourceRef must include #<anchor>")
    if not _ANCHOR_RE.fullmatch(anchor):
        _raise(SourceRefReasonCode.INVALID_ANCHOR, "Anchor must use canonical token characters")

    locator, has_sha, git_sha = pre_anchor.rpartition("@")
    if not has_sha or not git_sha:
        _raise(
            SourceRefReasonCode.INVALID_GIT_SHA,
            "SourceRef must include @<git_sha> before anchor",
        )
    if not _GIT_SHA_RE.fullmatch(git_sha):
        _raise(
            SourceRefReasonCode.INVALID_GIT_SHA,
            "Git SHA must be 7-40 lowercase hexadecimal characters",
        )

    owner, repo, source_path = _parse_locator(locator)
    _validate_source_path(source_path)

    return SourceRef(
        owner=owner,
        repo=repo,
        path=source_path,
        git_sha=git_sha,
        anchor=anchor,
        sha256=checksum,
    )


def validate_sourceref(
    value: str,
    *,
    authoritative: bool = False,
    repo_root: str | Path | None = None,
    read_bytes_fn: Callable[[Path], bytes] | None = None,
    expected_owner: str | None = None,
    expected_repo: str | None = None,
) -> SourceRef:
    """Validate and return parsed SourceRef components."""
    if not isinstance(value, str):
        _raise(SourceRefReasonCode.INVALID_STRUCTURE, "SourceRef must be a non-empty string")
    if not value.strip():
        _raise(SourceRefReasonCode.INVALID_FORMAT, "Value cannot be empty.")
    parsed = parse_sourceref(value)
    if authoritative:
        _validate_authoritative_sourceref(
            parsed,
            repo_root=repo_root,
            read_bytes_fn=read_bytes_fn,
            expected_owner=expected_owner,
            expected_repo=expected_repo,
        )
    return parsed


def _parse_locator(locator: str) -> tuple[str, str, str]:
    parts = locator.split("/")
    if len(parts) < 3:
        _raise(
            SourceRefReasonCode.INVALID_STRUCTURE,
            "SourceRef must include owner/repo/path before @<git_sha>",
        )

    owner = parts[0]
    repo = parts[1]
    source_path = "/".join(parts[2:])

    if not _OWNER_RE.fullmatch(owner):
        _raise(SourceRefReasonCode.INVALID_OWNER, "Owner contains invalid characters (use only alphanumeric characters, hyphens, or underscores)")
    if not _REPO_RE.fullmatch(repo):
        _raise(SourceRefReasonCode.INVALID_REPO, "Repository name contains invalid characters (use only alphanumeric characters, hyphens, underscores, or dots)")
    if not source_path:
        _raise(SourceRefReasonCode.INVALID_PATH, "Path must not be empty")

    return owner, repo, source_path


def _validate_source_path(source_path: str) -> None:
    if source_path.startswith("/") or source_path.endswith("/") or "\\" in source_path:
        _raise(
            SourceRefReasonCode.INVALID_PATH,
            "Path must be a repository-relative POSIX path",
        )

    segments = source_path.split("/")
    if any(segment == "" for segment in segments):
        _raise(SourceRefReasonCode.INVALID_PATH, "Path contains empty segments")
    if any(segment in {".", ".."} for segment in segments):
        _raise(
            SourceRefReasonCode.PATH_TRAVERSAL,
            "Path traversal segments are not allowed",
        )
    if len(segments) < 3 or tuple(segments[:2]) not in _ALLOWED_PREFIXES:
        _raise(
            SourceRefReasonCode.PATH_NOT_ALLOWLISTED,
            "Path must resolve under raw/inbox/**, raw/processed/**, or raw/assets/**",
        )


def _validate_authoritative_sourceref(
    source_ref: SourceRef,
    *,
    repo_root: str | Path | None,
    read_bytes_fn: Callable[[Path], bytes] | None,
    expected_owner: str | None,
    expected_repo: str | None,
) -> None:
    if _is_placeholder_git_sha(source_ref.git_sha):
        _raise(
            SourceRefReasonCode.PLACEHOLDER_GIT_SHA,
            "Authoritative SourceRefs must not use placeholder/sentinel git SHAs",
        )

    if repo_root is None:
        _raise(
            SourceRefReasonCode.INVALID_STRUCTURE,
            "repo_root is required for authoritative SourceRef validation",
        )
    if expected_owner is not None and source_ref.owner != expected_owner:
        _raise(
            SourceRefReasonCode.INVALID_REPO,
            "Authoritative SourceRef owner/repo does not match the expected repository identity",
        )
    if expected_repo is not None and source_ref.repo != expected_repo:
        _raise(
            SourceRefReasonCode.INVALID_REPO,
            "Authoritative SourceRef owner/repo does not match the expected repository identity",
        )

    normalized_repo_root = Path(repo_root).resolve()
    artifact_path = normalized_repo_root / source_ref.path
    resolved_artifact_path = artifact_path.resolve(strict=False)
    if not resolved_artifact_path.is_relative_to(normalized_repo_root):
        _raise(
            SourceRefReasonCode.PATH_TRAVERSAL,
            "Authoritative SourceRef path escapes repository boundary",
        )
    resolved_relative = resolved_artifact_path.relative_to(normalized_repo_root).as_posix()
    _validate_source_path(resolved_relative)

    if _path_has_symlink_component(artifact_path, stop_at=normalized_repo_root):
        _raise(
            SourceRefReasonCode.SYMLINKED_ARTIFACT,
            "Authoritative SourceRef artifacts must not resolve through symlinks",
        )

    resolved_git_sha = _resolve_commit_revision(normalized_repo_root, source_ref.git_sha)
    _validate_revision_artifact_path(
        normalized_repo_root,
        resolved_git_sha=resolved_git_sha,
        source_path=source_ref.path,
    )

    artifact_bytes = (
        _read_artifact_bytes_from_revision(
            normalized_repo_root,
            resolved_git_sha=resolved_git_sha,
            source_path=source_ref.path,
        )
    )
    checksum = hashlib.sha256(artifact_bytes).hexdigest()
    if checksum != source_ref.sha256:
        _raise(
            SourceRefReasonCode.CHECKSUM_MISMATCH,
            "Authoritative SourceRef checksum does not match artifact bytes",
        )


def _is_placeholder_git_sha(git_sha: str) -> bool:
    if git_sha == "0" * len(git_sha) or git_sha == "f" * len(git_sha):
        return True
    sentinel = ("deadbeef" * ((len(git_sha) // 8) + 1))[: len(git_sha)]
    return git_sha == sentinel


def _resolve_commit_revision(repo_root: Path, git_sha: str) -> str:
    completed = _run_git(
        repo_root,
        "rev-parse",
        "--verify",
        f"{git_sha}^{{commit}}",
        reason_code=SourceRefReasonCode.GIT_REVISION_MISSING,
        error_message="Authoritative SourceRef git_sha must resolve to a real commit revision",
        capture_text=True,
    )
    resolved_git_sha = completed.stdout.strip()
    if not resolved_git_sha:
        _raise(
            SourceRefReasonCode.GIT_REVISION_MISSING,
            "Authoritative SourceRef git_sha resolved to an empty revision",
        )
    return resolved_git_sha


def _validate_revision_artifact_path(repo_root: Path, *, resolved_git_sha: str, source_path: str) -> None:
    try:
        artifact_exists = subprocess.run(
            ["git", "-C", str(repo_root), "cat-file", "-e", f"{resolved_git_sha}:{source_path}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        _raise(
            SourceRefReasonCode.GIT_OPERATION_FAILED,
            f"Unable to inspect authoritative SourceRef path at the referenced revision ({exc})",
        )
    if artifact_exists.returncode != 0:
        _raise(
            SourceRefReasonCode.ARTIFACT_MISSING,
            "Authoritative SourceRef path is missing at the referenced git revision",
        )

    tree_entry = _run_git(
        repo_root,
        "ls-tree",
        resolved_git_sha,
        "--",
        source_path,
        reason_code=SourceRefReasonCode.GIT_OPERATION_FAILED,
        error_message="Unable to inspect authoritative SourceRef path at the referenced revision",
        capture_text=True,
    ).stdout.strip()
    if not tree_entry:
        _raise(
            SourceRefReasonCode.ARTIFACT_MISSING,
            "Authoritative SourceRef path is missing at the referenced git revision",
        )
    mode = tree_entry.split(None, 1)[0]
    if mode == "120000":
        _raise(
            SourceRefReasonCode.SYMLINKED_ARTIFACT,
            "Authoritative SourceRef path resolves to a symlink entry at the referenced revision",
        )
    if mode not in {"100644", "100755"}:
        _raise(
            SourceRefReasonCode.ARTIFACT_NOT_FILE,
            "Authoritative SourceRef path must reference a file/blob at the referenced revision",
        )


def _read_artifact_bytes_from_revision(repo_root: Path, *, resolved_git_sha: str, source_path: str) -> bytes:
    completed = _run_git(
        repo_root,
        "show",
        f"{resolved_git_sha}:{source_path}",
        reason_code=SourceRefReasonCode.GIT_OPERATION_FAILED,
        error_message="Unable to read authoritative SourceRef bytes from the referenced revision",
    )
    return completed.stdout


def _run_git(
    repo_root: Path,
    *args: str,
    reason_code: SourceRefReasonCode,
    error_message: str,
    capture_text: bool = False,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=capture_text,
            check=False,
        )
    except OSError as exc:
        _raise(reason_code, f"{error_message} ({exc})")
    if completed.returncode != 0:
        stderr = (
            completed.stderr.strip()
            if isinstance(completed.stderr, str)
            else completed.stderr.decode("utf-8", errors="replace").strip()
        )
        suffix = f" ({stderr})" if stderr else ""
        _raise(reason_code, f"{error_message}{suffix}")
    return completed


def _path_has_symlink_component(path: Path, *, stop_at: Path) -> bool:
    current = path
    stop_at = stop_at.resolve()
    while True:
        if current.is_symlink():
            return True
        if current == stop_at:
            return False
        if not current.is_relative_to(stop_at):
            return False
        current = current.parent


def _raise(reason_code: SourceRefReasonCode, message: str) -> None:
    raise SourceRefValidationError(reason_code, message)


__all__ = [
    "SourceRef",
    "SourceRefReasonCode",
    "SourceRefValidationError",
    "parse_sourceref",
    "validate_sourceref",
]
