"""Shared validation helpers for the github_monitor script family.

These helpers operate on untrusted data from registry JSON files and
GitHub API responses.  All functions fail closed: they raise ``ValueError``
on any suspicious input rather than silently passing.
"""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path, PurePosixPath

from scripts.github_monitor._types import _SAFE_SEGMENT_RE


_FORBIDDEN_COMPONENTS: frozenset[str] = frozenset({".."})
# Note: "~" is intentionally absent here; it is caught by the ``startswith("~")``
# check in ``_check_path_components`` which also covers ``~user`` forms.
_MAX_PATH_DEPTH: int = 20  # Practical guard against unreasonably deep paths

# Full 40-char lowercase hex string (git commit / blob SHA).
_COMMIT_SHA_RE: re.Pattern[str] = re.compile(r"^[0-9a-f]{40}$")


def validate_external_path(path: str) -> str:
    """Validate and normalize an external (untrusted) file path.

    Accepts a forward-slash-separated relative path string (e.g. from a
    registry JSON ``path`` field or a GitHub API response) and returns the
    normalized string if valid.

    Raises ``ValueError`` if the path:

    - Is empty or not a string.
    - Is absolute (starts with ``/``).
    - Contains ``..`` or ``~`` in any component.
    - Contains URL-encoded traversal sequences (``%2e%2e``, ``%7e``, etc.).
    - Contains null bytes or control characters.
    - Has more than ``_MAX_PATH_DEPTH`` components (defense-in-depth guard).

    Usage::

        validated = validate_external_path(entry["path"])
        # ... then build a local path:
        local_path = repo_root / "raw" / "assets" / owner / repo / sha / validated

    Always call ``check_no_symlink_path()`` from ``scripts.kb.write_utils`` on
    the *resolved local path* after construction, even when this function passes.
    """
    if not isinstance(path, str) or not path:
        raise ValueError(f"External path must be a non-empty string, got {path!r}")

    # Reject null bytes and control characters (defense against certain injection attacks).
    if any(ord(c) < 0x20 for c in path):
        raise ValueError(f"External path contains control characters: {path!r}")

    # Iteratively URL-decode and check each layer.  Stops when decoding is stable.
    # This catches both single-encoded (%2e%2e) and double-encoded (%252e%252e)
    # traversal sequences, and ensures control characters injected via URL encoding
    # are caught before reaching the filesystem.
    s = path
    while True:
        decoded = urllib.parse.unquote(s)
        if decoded == s:
            break
        if any(ord(c) < 0x20 for c in decoded):
            raise ValueError(
                f"External path contains control characters after URL-decoding: {path!r}"
            )
        _check_path_components(decoded, original=path)
        s = decoded

    _check_path_components(path, original=path)

    return path


def _check_path_components(path: str, *, original: str) -> None:
    """Check individual path components for traversal patterns.

    Raises ``ValueError`` if any component is forbidden.
    """
    # Reject absolute paths.
    if path.startswith("/") or path.startswith("\\"):
        raise ValueError(
            f"External path must be relative (no leading slash): {original!r}"
        )

    # Normalize separators and split into components.
    parts = PurePosixPath(path).parts

    if len(parts) > _MAX_PATH_DEPTH:
        raise ValueError(
            f"External path has {len(parts)} components (max {_MAX_PATH_DEPTH}): {original!r}"
        )

    for part in parts:
        if part in _FORBIDDEN_COMPONENTS:
            raise ValueError(
                f"External path contains forbidden component {part!r}: {original!r}"
            )
        if part.startswith("~"):
            raise ValueError(
                f"External path component starts with '~': {original!r}"
            )


def build_asset_path(
    repo_root: Path,
    owner: str,
    repo: str,
    commit_sha: str,
    file_path: str,
) -> Path:
    """Construct and bounds-check a ``raw/assets/`` path for a vendored asset.

    Parameters
    ----------
    repo_root:
        Absolute path to the knowledgebase repository root.
    owner:
        GitHub organization or user name from the registry.  Must contain only
        alphanumerics, hyphens, underscores, or dots (no slashes).
    repo:
        GitHub repository name from the registry.  Same character constraints.
    commit_sha:
        Full 40-hex commit SHA from the registry.  Must be exactly 40 lowercase
        hex characters.
    file_path:
        Repo-relative file path from the external repo; must have passed
        ``validate_external_path()`` already.

    Returns
    -------
    Path
        Resolved absolute path under ``raw/assets/``.  Raises ``ValueError``
        if any argument fails validation or the resolved path escapes the
        ``raw/assets/`` prefix.
    """
    for name, value in (("owner", owner), ("repo", repo)):
        if not value or not _SAFE_SEGMENT_RE.match(value):
            raise ValueError(
                f"build_asset_path: {name!r} must be a non-empty alphanumeric/"
                f"hyphen/underscore/dot string, got {value!r}"
            )

    if not _COMMIT_SHA_RE.match(commit_sha):
        raise ValueError(
            f"build_asset_path: commit_sha must be a 40-char lowercase hex string, "
            f"got {commit_sha!r}"
        )

    assets_root = (repo_root / "raw" / "assets").resolve()
    target = (repo_root / "raw" / "assets" / owner / repo / commit_sha / file_path).resolve()

    if not target.is_relative_to(assets_root):
        raise ValueError(
            f"Asset path {target} escapes raw/assets/ boundary (owner={owner!r}, "
            f"repo={repo!r}, sha={commit_sha!r}, path={file_path!r})"
        )

    return target
