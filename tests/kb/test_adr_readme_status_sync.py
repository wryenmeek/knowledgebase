"""Test that docs/decisions/README.md status cells match ADR ## Status section lines.

When an ADR status line is updated (e.g., amended, extended), the README index row
must reflect the same status. Both sides are normalized before comparison:
implementation-detail text after the first ': ' separator in compound status strings
is stripped so README cells can omit verbose detail while still capturing the type.

Normalization examples:
  'Accepted' → 'Accepted'
  'Accepted — amended in-place: uses pre-commit framework' → 'Accepted — amended in-place'
  'Accepted — extended by ADR-015' → 'Accepted — extended by ADR-015'
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DECISIONS_DIR = REPO_ROOT / "docs" / "decisions"
README_PATH = DECISIONS_DIR / "README.md"

# Matches the ## Status heading (exact heading, start of line)
_STATUS_HEADING_RE = re.compile(r"^## Status\s*$", re.MULTILINE)

# Matches ADR rows in the README table:
#   | [ADR-NNN](ADR-NNN-filename.md) | Title | Status |
_README_ROW_RE = re.compile(
    r"^\|\s*\[ADR-\d+\]\(([^)]+)\)\s*\|[^|]+\|\s*([^|]+?)\s*\|",
    re.MULTILINE,
)


def _normalize_status(raw: str) -> str:
    """Strip implementation detail from compound status strings.

    Strips two kinds of implementation detail:
    1. Text after the first ': ' when '—' precedes it
       e.g., 'Accepted — amended in-place: detail' → 'Accepted — amended in-place'
    2. Trailing parenthetical ' (...)' after the main clause
       e.g., 'Accepted — extended by ADR-015 (CI-4 added)' → 'Accepted — extended by ADR-015'
    """
    normalized = raw.strip()
    # Strip ': <detail>' from compound strings containing em-dash
    parts = normalized.split(": ", 1)
    if len(parts) == 2 and "\u2014" in parts[0]:  # em-dash
        normalized = parts[0].strip()
    # Strip trailing parenthetical from compound strings containing em-dash
    paren_match = re.search(r"\s*\([^)]+\)\s*$", normalized)
    if paren_match and "\u2014" in normalized[: paren_match.start()]:
        normalized = normalized[: paren_match.start()].strip()
    return normalized


def _extract_adr_status(adr_path: Path) -> str | None:
    """Return the first non-empty line after the '## Status' heading."""
    text = adr_path.read_text(encoding="utf-8")
    match = _STATUS_HEADING_RE.search(text)
    if match is None:
        return None
    rest = text[match.end():]
    for line in rest.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _parse_readme_status_map() -> dict[str, str]:
    """Parse README.md ADR index table → {adr_filename: raw_status_cell}."""
    if not README_PATH.exists():
        return {}
    text = README_PATH.read_text(encoding="utf-8")
    result: dict[str, str] = {}
    for match in _README_ROW_RE.finditer(text):
        filename = match.group(1).strip()
        status = match.group(2).strip()
        result[filename] = status
    return result


class TestAdrReadmeStatusSync(unittest.TestCase):
    """ADR ## Status lines must match README index status cells (normalized)."""

    def test_adr_status_matches_readme_index(self) -> None:
        if not DECISIONS_DIR.is_dir():
            self.skipTest("docs/decisions/ directory does not exist")
        if not README_PATH.exists():
            self.skipTest("docs/decisions/README.md does not exist")

        readme_map = _parse_readme_status_map()
        if not readme_map:
            self.skipTest("README.md ADR index table is empty or unparseable")

        for adr_file in sorted(DECISIONS_DIR.glob("ADR-*.md")):
            with self.subTest(adr=adr_file.name):
                adr_status = _extract_adr_status(adr_file)
                self.assertIsNotNone(
                    adr_status,
                    f"{adr_file.name}: missing '## Status' section",
                )

                readme_status = readme_map.get(adr_file.name)
                self.assertIsNotNone(
                    readme_status,
                    f"{adr_file.name}: not found in README.md ADR index table",
                )

                normalized_adr = _normalize_status(adr_status)  # type: ignore[arg-type]
                normalized_readme = _normalize_status(readme_status)  # type: ignore[arg-type]

                self.assertEqual(
                    normalized_readme,
                    normalized_adr,
                    f"{adr_file.name}: README status '{readme_status}' does not match "
                    f"ADR status '{adr_status}' (normalized: '{normalized_readme}' "
                    f"vs '{normalized_adr}'). "
                    f"Update docs/decisions/README.md to reflect the current ADR status.",
                )

    def test_readme_has_entry_for_every_adr_file(self) -> None:
        """Ensure every ADR file has a corresponding README index entry."""
        if not DECISIONS_DIR.is_dir():
            self.skipTest("docs/decisions/ directory does not exist")
        if not README_PATH.exists():
            self.skipTest("docs/decisions/README.md does not exist")

        readme_map = _parse_readme_status_map()
        for adr_file in sorted(DECISIONS_DIR.glob("ADR-*.md")):
            with self.subTest(adr=adr_file.name):
                self.assertIn(
                    adr_file.name,
                    readme_map,
                    f"{adr_file.name} is not listed in docs/decisions/README.md index table",
                )


if __name__ == "__main__":
    unittest.main()
