"""Shared validation helpers for the drive_monitor script family.

These helpers operate on untrusted data from registry JSON files and
Drive API responses.  All functions fail closed: they raise ``ValueError``
on any suspicious input rather than silently passing.
"""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path, PurePosixPath

from scripts.drive_monitor._types import (
    _DRIVE_FILE_ID_RE,
    _ALIAS_RE,
    MIME_EXTENSION_MAP,
)

_LEADING_DOTS_RE: re.Pattern[str] = re.compile(r"^\.+")
_UNSAFE_CHARS_RE: re.Pattern[str] = re.compile(r"[^\w\-. ]+")
_MAX_BASENAME_LEN: int = 200

_FORBIDDEN_COMPONENTS: frozenset[str] = frozenset({".."})
_MAX_PATH_DEPTH: int = 20


def validate_alias(alias: str) -> str:
    """Validate a registry alias slug.

    Aliases must be lowercase, alphanumeric, hyphen-separated slugs.  Raises
    ``ValueError`` on any violation.

    Example valid aliases: ``cms-guidelines``, ``policy-docs``, ``myalias``
    Example invalid: ``CMS_Guidelines``, ``../evil``, ``my/alias``
    """
    if not isinstance(alias, str) or not alias:
        raise ValueError(f"Alias must be a non-empty string, got {alias!r}")
    if not _ALIAS_RE.match(alias):
        raise ValueError(
            f"Alias must be lowercase alphanumeric/hyphen-separated (no leading/"
            f"trailing hyphens, no underscores, no uppercase), got {alias!r}"
        )
    return alias


def validate_file_id(file_id: str) -> str:
    """Validate an untrusted Google Drive file/folder ID.

    Drive file IDs contain alphanumeric characters, underscores, and hyphens.
    Raises ``ValueError`` on any violation.
    """
    if not isinstance(file_id, str) or not file_id:
        raise ValueError(f"Drive file_id must be a non-empty string, got {file_id!r}")
    if not _DRIVE_FILE_ID_RE.match(file_id):
        raise ValueError(
            f"Drive file_id contains unsafe characters: {file_id!r}"
        )
    return file_id


def validate_display_name(name: str) -> str:
    """Validate an untrusted Drive file display name for use in asset paths.

    Strips or rejects characters that could cause path traversal.  Raises
    ``ValueError`` if the name contains null bytes, path separators, or
    traversal sequences.
    """
    if not isinstance(name, str) or not name:
        raise ValueError(f"Display name must be a non-empty string, got {name!r}")
    if any(ord(c) < 0x20 for c in name):
        raise ValueError(f"Display name contains control characters: {name!r}")
    # Reject any name that looks like a path (contains / or \)
    if "/" in name or "\\" in name:
        raise ValueError(
            f"Display name must not contain path separators: {name!r}"
        )
    if name in ("..", "."):
        raise ValueError(f"Display name must not be a path traversal component: {name!r}")
    return name


def build_drive_asset_path(
    repo_root: Path,
    alias: str,
    file_id: str,
    version_segment: str,
    filename: str,
) -> Path:
    """Construct and bounds-check a ``raw/assets/gdrive/`` path for a vendored asset.

    Parameters
    ----------
    repo_root:
        Absolute path to the knowledgebase repository root.
    alias:
        Registry alias slug (must pass ``validate_alias()``).
    file_id:
        Drive file ID (must pass ``validate_file_id()``).
    version_segment:
        Drive version integer string (native) or MD5 checksum hex (non-native).
        Used as the directory segment to make paths unique across content versions.
    filename:
        Safe filename with extension (must pass ``validate_display_name()``).

    Returns
    -------
    Path
        Resolved absolute path under ``raw/assets/gdrive/``.  Raises
        ``ValueError`` if any argument fails validation or the resolved path
        escapes the ``raw/assets/gdrive/`` prefix.
    """
    validate_alias(alias)
    validate_file_id(file_id)
    validate_display_name(filename)

    if not isinstance(version_segment, str) or not version_segment:
        raise ValueError(
            f"version_segment must be a non-empty string, got {version_segment!r}"
        )
    # Must be alphanumeric-only (either an integer string or an MD5 hex).
    if not re.match(r"^[0-9a-f]+$", version_segment):
        raise ValueError(
            f"version_segment must be an integer string or a lowercase hex string, "
            f"got {version_segment!r}"
        )

    gdrive_root = (repo_root / "raw" / "assets" / "gdrive").resolve()
    target = (
        repo_root / "raw" / "assets" / "gdrive" / alias / file_id / version_segment / filename
    ).resolve()

    if not target.is_relative_to(gdrive_root):
        raise ValueError(
            f"Drive asset path {target} escapes raw/assets/gdrive/ boundary "
            f"(alias={alias!r}, file_id={file_id!r}, version={version_segment!r}, "
            f"filename={filename!r})"
        )

    return target


def safe_filename(display_name: str, mime_type: str) -> str:
    """Build a safe filename for an asset from the display name and MIME type.

    Replaces unsafe characters with underscores, strips leading dots (to
    prevent hidden files), limits length to 200 chars, and appends the
    canonical extension for the MIME type.  Returns ``"untitled"`` (plus
    extension) when the sanitised base is empty.
    """
    base = _UNSAFE_CHARS_RE.sub("_", display_name).strip().rstrip(".")
    base = _LEADING_DOTS_RE.sub("", base)
    if not base:
        base = "untitled"
    base = base[:_MAX_BASENAME_LEN]
    ext = MIME_EXTENSION_MAP.get(mime_type, "")
    if ext and not base.lower().endswith(ext):
        return base + ext
    return base


def build_wiki_page_path(repo_root: Path, wiki_page: str) -> Path:
    """Construct and bounds-check a wiki page path.

    Raises ``ValueError`` if the resolved path escapes ``wiki/``.
    """
    if not isinstance(wiki_page, str) or not wiki_page:
        raise ValueError(f"wiki_page must be a non-empty string, got {wiki_page!r}")
    wiki_root = (repo_root / "wiki").resolve()
    target = (repo_root / wiki_page).resolve()
    if not target.is_relative_to(wiki_root):
        raise ValueError(
            f"wiki_page path {wiki_page!r} escapes wiki/ boundary"
        )
    return target
