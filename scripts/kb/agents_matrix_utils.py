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

    # ⚡ Bolt: Isolate the table block using str.find() and parse rows directly with re.finditer to avoid O(N) allocation from splitlines() on large Markdown files
    start_idx = text.find("| Surface ")
    if start_idx == -1:
        start_idx = text.find("| Surface |")
        if start_idx == -1:
            return set()

    # Find start of that line
    line_start = text.rfind("\n", 0, start_idx)
    line_start = 0 if line_start == -1 else line_start + 1

    # Tables in markdown end with a blank line or EOF
    end_idx = text.find("\n\n", line_start)
    block = text[line_start:] if end_idx == -1 else text[line_start:end_idx]

    surfaces: set[str] = set()

    # Only iterate through lines in the table block
    for match in re.finditer(r"^([ \t]*\|.*)$", block, re.MULTILINE):
        stripped = match.group(1).strip()

        # Skip separator rows (---|---).
        if re.match(r"^\|[-| :]+\|$", stripped):
            continue

        row_match = _ROW_RE.match(stripped)
        if not row_match:
            continue

        surface = _strip_surface_text(row_match.group(1))
        if surface and surface != "Surface":
            surfaces.add(surface)

    return surfaces
