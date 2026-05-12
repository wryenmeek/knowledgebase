"""Contract checks for thin optional heavy-surface skills."""

from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_EXPECTATIONS = {
    "refresh-context-pages": {
        "script": "scripts/context/manage_context_pages.py",
        "commands": ("--mode inventory", "--mode plan-fill"),
    },
    "fill-context-pages": {
        "script": "scripts/context/fill_context_pages.py",
        "commands": ("--mode preview", "--mode apply"),
    },
    "generate-maintenance-docs": {
        "script": "scripts/maintenance/generate_docs.py",
        "commands": ("--mode inventory", "--mode apply"),
    },
    "convert-sources-to-md": {
        "script": "scripts/ingest/convert_sources_to_md.py",
        "commands": ("--mode inspect", "--mode preview"),
    },
    "snapshot-knowledgebase": {
        "script": "scripts/validation/snapshot_knowledgebase.py",
        "commands": ("--mode capture", "--mode compare"),
    },
    "report-content-quality": {
        "script": "scripts/reporting/content_quality_report.py",
        "commands": ("--mode summary", "--mode persist"),
    },
    "prioritize-quality-follow-up": {
        "script": "scripts/reporting/quality_runtime.py",
        "commands": ("--mode recommend", "--mode report"),
    },
}


class OptionalSurfaceSkillTests(unittest.TestCase):
    def test_skills_are_thin_and_point_to_repo_scripts(self) -> None:
        for skill_name, expectation in SKILL_EXPECTATIONS.items():
            skill_root = REPO_ROOT / ".github" / "skills" / skill_name
            text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill_name):
                self.assertIn("## Overview", text)
                self.assertIn("## When to Use", text)
                self.assertIn("## Contract", text)
                self.assertIn("## Assertions", text)
                self.assertIn("## Commands", text)
                self.assertIn("## References", text)
                self.assertIn(expectation["script"], text)
                self.assertFalse((skill_root / "logic").exists())
                for command_snippet in expectation["commands"]:
                    self.assertIn(command_snippet, text)
                self.assertIn("typed", text.lower())


if __name__ == "__main__":
    unittest.main()
