"""Deterministic SourceRef parser and validator."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re


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


def validate_sourceref(value: str) -> SourceRef:
    """Validate and return parsed SourceRef components."""
    if not value.strip():
        _raise(SourceRefReasonCode.INVALID_FORMAT, "Value cannot be empty.")
    return parse_sourceref(value)


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
        _raise(SourceRefReasonCode.INVALID_OWNER, "Owner contains invalid characters")
    if not _REPO_RE.fullmatch(repo):
        _raise(SourceRefReasonCode.INVALID_REPO, "Repository name contains invalid characters")
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


def _raise(reason_code: SourceRefReasonCode, message: str) -> None:
    raise SourceRefValidationError(reason_code, message)


__all__ = [
    "SourceRef",
    "SourceRefReasonCode",
    "SourceRefValidationError",
    "parse_sourceref",
    "validate_sourceref",
]
