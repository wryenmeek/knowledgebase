"""Shared parser for the AGENTS.md write-surface matrix.

Extracts the set of surface path patterns from the write-surface matrix table
in ``AGENTS.md``. Used by both the framework test
(``tests/kb/test_framework_write_surface_matrix.py``) and the
``check_matrix_coverage`` pre-commit hook.

Design notes
------------
- Row text-stripping uses ``.partition(" \u2014 ")`` (em dash) to remove the
  descriptive suffix (e.g. " — persist mode only") from Surface column entries.
  This is more robust than index-based or ``replace()`` approaches because it
  handles the common case (no suffix) cleanly by returning the original string.
- Backtick wrapping is stripped before pattern extraction.
- The parser is unit-tested against inline fixture strings, NOT against the
  real AGENTS.md, so tests remain stable as AGENTS.md evolves.
"""

from __future__ import annotations

import re
from pathlib import Path

# Matches a table row whose first non-whitespace column contains a path pattern.
# The Surface column is column 1 (index 0 after splitting on ``|``).
_ROW_RE = re.compile(r"^\|([^|]+)\|")

__all__ = ["parse_matrix_surfaces"]


def _strip_surface_text(raw: str) -> str:
    """Return the path portion of a Surface column entry.

    Strips:
    - Leading/trailing whitespace
    - Backtick code-span markers
    - Em-dash suffixes like " — persist mode only"
    """
    text = raw.strip()
    # Remove backticks (code-span wrapping).
    text = text.replace("`", "")
    # Strip em-dash suffix.
    core, _sep, _rest = text.partition(" \u2014 ")
    return core.strip()


def parse_matrix_surfaces(agents_md_path: str | Path) -> set[str]:
    """Parse the write-surface matrix from *agents_md_path*.

    Returns a set of normalised surface path patterns (e.g.
    ``"scripts/kb/**"``). Skips header rows and separator rows.
    """
    text = Path(agents_md_path).read_text(encoding="utf-8")

    # OPTIMIZATION: Fast-path literal check to avoid O(N) splitlines allocation
    if "| Surface |" not in text and "| Surface " not in text:
        return set()

    surfaces: set[str] = set()

    # ⚡ Bolt: Isolate the table using find() before running re.finditer to avoid
    # O(N) splitlines allocation and Python loop overhead.
    start_idx = text.find("| Surface ")
    if start_idx == -1:
        start_idx = text.find("| Surface |")

    if start_idx == -1:
        return set()

    # Find the end of the matrix
    end_idx = text.find("\n\n", start_idx)
    if end_idx == -1:
        end_idx = text.find("\r\n\r\n", start_idx)
        if end_idx == -1:
            end_idx = len(text)

    _ROW_MULTILINE_RE = re.compile(r"^\|([^|\n]+)\|", re.MULTILINE)

    for match in _ROW_MULTILINE_RE.finditer(text, start_idx, end_idx):
        raw = match.group(1).strip()

        if (
            raw == "Surface"
            or raw.startswith("---")
            or raw.startswith(":-")
            or raw.startswith("-:")
        ):
            continue

        surface = _strip_surface_text(raw)

        if surface:
            surfaces.add(surface)

    return surfaces
