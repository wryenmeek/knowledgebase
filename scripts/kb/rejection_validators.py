"""Field validators for the rejection registry contract.

Validates individual fields of rejection records against
``schema/rejection-registry-contract.md`` constraints.

These validators are used by ``log-intake-rejection`` logic before
writing a rejection record to ``raw/rejected/``.
"""

from __future__ import annotations

import re
from typing import Any


_SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SLUG_MAX_LENGTH = 64

REJECTION_CATEGORIES: frozenset[str] = frozenset({
    "provenance_missing",
    "format_unsupported",
    "duplicate",
    "out_of_scope",
    "quality_insufficient",
})


def validate_slug(slug: str) -> list[str]:
    """Validate a rejection record slug.  Returns a list of error messages."""
    errors: list[str] = []
    if not slug:
        errors.append("slug is empty")
        return errors
    if len(slug) > _SLUG_MAX_LENGTH:
        errors.append(f"slug exceeds {_SLUG_MAX_LENGTH} characters: {len(slug)}")
    if "/" in slug or "\\" in slug:
        errors.append("slug contains path separator")
    if ".." in slug:
        errors.append("slug contains parent traversal")
    if "\x00" in slug:
        errors.append("slug contains null byte")
    if not _SLUG_RE.match(slug):
        errors.append(
            f"slug does not match pattern [a-z0-9]([a-z0-9-]*[a-z0-9])?: {slug!r}"
        )
    return errors


def validate_sha256(sha256: str) -> list[str]:
    """Validate a SHA-256 hex digest.  Returns a list of error messages."""
    errors: list[str] = []
    if not sha256:
        errors.append("sha256 is empty")
        return errors
    if not _SHA256_RE.match(sha256):
        errors.append(f"sha256 is not a valid 64-char lowercase hex string: {sha256!r}")
    return errors


def validate_category(category: str) -> list[str]:
    """Validate a rejection category.  Returns a list of error messages."""
    errors: list[str] = []
    if not category:
        errors.append("rejection_category is empty")
        return errors
    if category not in REJECTION_CATEGORIES:
        errors.append(
            f"rejection_category {category!r} not in allowed set: "
            f"{sorted(REJECTION_CATEGORIES)}"
        )
    return errors


def validate_filename(filename: str) -> list[str]:
    """Validate a rejection record filename.  Returns a list of error messages."""
    errors: list[str] = []
    if not filename:
        errors.append("filename is empty")
        return errors
    if not filename.endswith(".rejection.md"):
        errors.append(f"filename must end with .rejection.md: {filename!r}")
        return errors

    stem = filename.removesuffix(".rejection.md")
    if "--" not in stem:
        errors.append(
            f"filename must contain '--' separating slug from sha256 prefix: {filename!r}"
        )
        return errors

    slug, _, sha_prefix = stem.rpartition("--")
    slug_errors = validate_slug(slug)
    if slug_errors:
        errors.extend(slug_errors)

    if len(sha_prefix) != 8:
        errors.append(
            f"sha256 prefix must be exactly 8 characters, got {len(sha_prefix)}: {sha_prefix!r}"
        )
    elif not re.match(r"^[0-9a-f]{8}$", sha_prefix):
        errors.append(f"sha256 prefix must be lowercase hex: {sha_prefix!r}")

    return errors


def validate_frontmatter(fields: dict[str, Any]) -> list[str]:
    """Validate required frontmatter fields.  Returns a list of error messages."""
    errors: list[str] = []
    required = {"slug", "sha256", "rejected_date", "source_path",
                "rejection_reason", "rejection_category", "reviewed_by",
                "reconsidered_date"}
    missing = required - set(fields.keys())
    if missing:
        errors.append(f"missing required frontmatter fields: {sorted(missing)}")

    if "slug" in fields:
        errors.extend(validate_slug(str(fields["slug"])))
    if "sha256" in fields:
        errors.extend(validate_sha256(str(fields["sha256"])))
    if "rejection_category" in fields:
        errors.extend(validate_category(str(fields["rejection_category"])))
    return errors
