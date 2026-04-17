"""Framework skill scaffolding checks."""

from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPO_ROOT / ".github" / "skills"
FRAMEWORK_SKILLS: dict[str, dict[str, object]] = {
    "information-architecture-and-taxonomy": {"logic": False, "classification": "Doc-only contract consumer"},
    "ontology-and-entity-modeling": {"logic": False, "classification": "Doc-only contract consumer"},
    "knowledge-schema-and-metadata-governance": {"logic": False, "classification": "Doc-only contract consumer"},
    "entity-resolution-and-canonicalization": {"logic": False, "classification": "Deferred"},
    "search-and-discovery-optimization": {"logic": False, "classification": "Deferred"},
    "validate-wiki-governance": {"logic": True},
    "sync-knowledgebase-state": {"logic": True},
    "review-wiki-plan": {"logic": False},
}


class FrameworkSkillTests(unittest.TestCase):
    def test_expected_framework_skills_exist(self) -> None:
        for skill_name in FRAMEWORK_SKILLS:
            with self.subTest(skill=skill_name):
                self.assertTrue((SKILLS_ROOT / skill_name / "SKILL.md").is_file())

    def test_skill_frontmatter_matches_directory_and_discovery_requirements(self) -> None:
        for skill_name in FRAMEWORK_SKILLS:
            skill_path = SKILLS_ROOT / skill_name / "SKILL.md"
            frontmatter = self._parse_frontmatter(skill_path.read_text(encoding="utf-8"))
            with self.subTest(skill=skill_name):
                self.assertEqual(frontmatter.get("name"), skill_name)
                self.assertIn("Use when", frontmatter.get("description", ""))

    def test_skill_docs_include_overview_and_when_to_use_sections(self) -> None:
        for skill_name in FRAMEWORK_SKILLS:
            text = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill_name):
                self.assertIn("## Overview", text)
                self.assertIn("## When to Use", text)

    def test_skill_logic_boundary_matches_mvp_scope(self) -> None:
        for skill_name, expectations in FRAMEWORK_SKILLS.items():
            logic_dir = SKILLS_ROOT / skill_name / "logic"
            with self.subTest(skill=skill_name):
                if expectations["logic"]:
                    self.assertTrue(logic_dir.is_dir())
                    self.assertTrue(any(logic_dir.glob("*.py")))
                else:
                    self.assertFalse(logic_dir.exists())

    def test_classified_skills_keep_declared_status_text(self) -> None:
        for skill_name, expectations in FRAMEWORK_SKILLS.items():
            classification = expectations.get("classification")
            if classification is None:
                continue
            text = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill_name):
                self.assertIn(str(classification), text)

    def _parse_frontmatter(self, text: str) -> dict[str, str]:
        lines = text.splitlines()
        if len(lines) < 3 or lines[0].strip() != "---":
            self.fail("Skill file missing YAML frontmatter")
        result: dict[str, str] = {}
        for line in lines[1:]:
            if line.strip() == "---":
                break
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
        return result


if __name__ == "__main__":
    unittest.main()
