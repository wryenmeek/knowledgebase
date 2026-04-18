"""Contract checks for the scan-content-freshness skill."""

from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPO_ROOT / ".github" / "skills" / "scan-content-freshness"
SKILL_PATH = SKILL_ROOT / "SKILL.md"


class ScanContentFreshnessSkillTests(unittest.TestCase):
    def test_skill_is_thin_and_routes_to_repo_script_with_typed_args(self) -> None:
        text = SKILL_PATH.read_text(encoding="utf-8")

        self.assertIn("## Overview", text)
        self.assertIn("## When to Use", text)
        self.assertIn("## Contract", text)
        self.assertIn("## Assertions", text)
        self.assertIn("## Commands", text)
        self.assertIn("scripts/validation/check_doc_freshness.py", text)
        self.assertIn("--scope", text)
        self.assertIn("--as-of", text)
        self.assertIn("--max-age-days", text)
        self.assertIn("typed", text.lower())
        self.assertFalse((SKILL_ROOT / "logic").exists())


if __name__ == "__main__":
    unittest.main()
