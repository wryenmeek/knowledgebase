"""Shared path validation primitives for audit-workspace logic."""

from __future__ import annotations

import re


SAFE_REPO_RELATIVE_PATH_PATTERN = (
    r"^(?!.*[\s\x00-\x1F\x7F])(?!/)(?![A-Za-z]:)"
    r"(?![A-Za-z][A-Za-z0-9+.-]*:)(?!.*(?:^|/)\.\.?($|/))"
    r"[A-Za-z0-9._@+-]+(?:/[A-Za-z0-9._@+-]+)*$"
)
SAFE_REPO_RELATIVE_PATH_RE = re.compile(SAFE_REPO_RELATIVE_PATH_PATTERN)


__all__ = [
    "SAFE_REPO_RELATIVE_PATH_PATTERN",
    "SAFE_REPO_RELATIVE_PATH_RE",
]
