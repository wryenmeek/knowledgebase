"""Shared helpers for canonical repository-relative paths."""

from __future__ import annotations

from os import PathLike
from pathlib import Path, PurePosixPath


class RepoRelativePathError(ValueError):
    """Raised when a path is not a canonical repo-relative POSIX path."""


# Error kinds returned by try_normalize_repo_relative_path.
ERROR_KIND_INVALID_PATH = "invalid_path"
ERROR_KIND_PATH_TRAVERSAL = "path_traversal"


def try_normalize_repo_relative_path(
    path: str | PathLike[str],
) -> tuple[str, str | None]:
    """Normalize a repo-relative POSIX path without raising.

    Returns ``(normalized, error_kind)``. ``error_kind`` is ``None`` on success,
    ``"path_traversal"`` if the path contains ``..`` segments, and
    ``"invalid_path"`` otherwise. On failure ``normalized`` is the raw input.
    """
    raw_path = path.as_posix() if isinstance(path, Path) else str(path)
    if not raw_path or raw_path.startswith("/") or "\\" in raw_path or "//" in raw_path:
        return raw_path, ERROR_KIND_INVALID_PATH

    parts = raw_path.split("/")
    if any(part in {"", "."} for part in parts):
        return raw_path, ERROR_KIND_INVALID_PATH
    if any(part == ".." for part in parts):
        return raw_path, ERROR_KIND_PATH_TRAVERSAL

    return PurePosixPath(raw_path).as_posix(), None


def normalize_repo_relative_path(path: str | PathLike[str]) -> str:
    normalized, error_kind = try_normalize_repo_relative_path(path)
    if error_kind == ERROR_KIND_PATH_TRAVERSAL:
        raise RepoRelativePathError("paths must not contain traversal or non-canonical segments")
    if error_kind == ERROR_KIND_INVALID_PATH:
        if not normalized or normalized.startswith("/") or "\\" in normalized or "//" in normalized:
            raise RepoRelativePathError("paths must be repository-relative POSIX paths")
        raise RepoRelativePathError("paths must not contain traversal or non-canonical segments")
    return normalized


__all__ = [
    "ERROR_KIND_INVALID_PATH",
    "ERROR_KIND_PATH_TRAVERSAL",
    "RepoRelativePathError",
    "normalize_repo_relative_path",
    "try_normalize_repo_relative_path",
]
