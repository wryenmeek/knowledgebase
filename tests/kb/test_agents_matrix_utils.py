"""Tests for scripts.kb.agents_matrix_utils.

Parser unit tests use inline fixture strings (NOT real AGENTS.md) so the
test suite remains stable as AGENTS.md evolves.  A separate integration test
exercises the real AGENTS.md.
"""

import textwrap
import unittest
from pathlib import Path

from scripts.kb.agents_matrix_utils import _strip_surface_text, parse_matrix_surfaces

# --- Integration test path ---
AGENTS_PATH = Path(__file__).resolve().parents[2] / "AGENTS.md"


class StripSurfaceTextTests(unittest.TestCase):
    """Unit tests for the text-stripping helper."""

    def test_plain_path_unchanged(self) -> None:
        self.assertEqual(_strip_surface_text("scripts/kb/**"), "scripts/kb/**")

    def test_em_dash_suffix_stripped(self) -> None:
        result = _strip_surface_text(
            "scripts/reporting/content_quality_report.py \u2014 persist mode only"
        )
        self.assertEqual(result, "scripts/reporting/content_quality_report.py")

    def test_backtick_wrapped_stripped(self) -> None:
        result = _strip_surface_text("`scripts/hooks/**`")
        self.assertEqual(result, "scripts/hooks/**")

    def test_backtick_and_em_dash_combined(self) -> None:
        result = _strip_surface_text(
            "`scripts/ingest/convert_sources_to_md.py` \u2014 apply mode only"
        )
        self.assertEqual(result, "scripts/ingest/convert_sources_to_md.py")

    def test_leading_trailing_whitespace_stripped(self) -> None:
        result = _strip_surface_text("  scripts/kb/**  ")
        self.assertEqual(result, "scripts/kb/**")

    def test_header_row_returns_header_string(self) -> None:
        """Surface column header should not appear in parsed output."""
        result = _strip_surface_text("Surface")
        self.assertEqual(result, "Surface")


class ParseMatrixSurfacesFixtureTests(unittest.TestCase):
    """Unit tests using inline AGENTS.md fixture content."""

    def _parse(self, markdown: str) -> set[str]:
        import tempfile, os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(markdown)
            name = f.name
        try:
            return parse_matrix_surfaces(name)
        finally:
            os.unlink(name)

    def _make_matrix(self, rows: list[str]) -> str:
        header = "| Surface | Runtime mode | Writable paths | Read-only / prerequisite paths | Lock requirements | Artifact / schema owners | Hard-fail behavior |"
        sep = "|---|---|---|---|---|---|---|"
        return "\n".join(["## Some Section", header, sep] + rows + [""])

    def test_plain_path_row_parsed(self) -> None:
        md = self._make_matrix(["| scripts/kb/** | read-only only | None | ... | None | ... | fail closed |"])
        surfaces = self._parse(md)
        self.assertIn("scripts/kb/**", surfaces)

    def test_em_dash_suffix_stripped_in_parse(self) -> None:
        md = self._make_matrix([
            "| scripts/reporting/content_quality_report.py \u2014 persist mode only | blocking-only | wiki/reports/ | ... | wiki/.kb_write.lock | schema/ | fail closed |"
        ])
        surfaces = self._parse(md)
        self.assertIn("scripts/reporting/content_quality_report.py", surfaces)
        self.assertNotIn(
            "scripts/reporting/content_quality_report.py \u2014 persist mode only", surfaces
        )

    def test_backtick_row_parsed(self) -> None:
        md = self._make_matrix(["| `scripts/hooks/**` | read-only only | None | ... | None | ... | fail closed |"])
        surfaces = self._parse(md)
        self.assertIn("scripts/hooks/**", surfaces)

    def test_skill_logic_row_parsed(self) -> None:
        md = self._make_matrix([
            "| .github/skills/append-log-entry/logic/** | blocking-only | wiki/log.md | ... | wiki/.kb_write.lock | ... | fail closed |"
        ])
        surfaces = self._parse(md)
        self.assertIn(".github/skills/append-log-entry/logic/**", surfaces)

    def test_separator_rows_excluded(self) -> None:
        md = self._make_matrix(["| scripts/kb/** | read-only only | None | ... | None | ... | fail closed |"])
        surfaces = self._parse(md)
        self.assertNotIn("---", surfaces)

    def test_multiple_rows(self) -> None:
        md = self._make_matrix([
            "| scripts/kb/** | read-only only | None | ... | None | ... | fail closed |",
            "| scripts/hooks/** | read-only only | None | ... | None | ... | fail closed |",
        ])
        surfaces = self._parse(md)
        self.assertIn("scripts/kb/**", surfaces)
        self.assertIn("scripts/hooks/**", surfaces)


class ParseMatrixSurfacesIntegrationTests(unittest.TestCase):
    """Integration test: real AGENTS.md must include all expected rows."""

    EXPECTED_SURFACES = {
        ".github/skills/append-log-entry/logic/**",
        ".github/skills/check-link-topology/logic/**",
        "scripts/kb/**",
        "scripts/validation/**",
        "scripts/hooks/**",
    }

    def test_real_agents_md_contains_expected_surfaces(self) -> None:
        surfaces = parse_matrix_surfaces(AGENTS_PATH)
        for expected in self.EXPECTED_SURFACES:
            with self.subTest(surface=expected):
                self.assertIn(
                    expected,
                    surfaces,
                    f"AGENTS.md write-surface matrix is missing row for '{expected}'",
                )


if __name__ == "__main__":
    unittest.main()
