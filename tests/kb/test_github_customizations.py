"""Semantic cross-reference tests for .github/ customization files.

Validates that agent personas, copilot-instructions.md, hooks.json, and
prompt files all reference real, on-disk targets. This is the CI gate side of
the semantic graph engine (scripts/kb/github_customizations_graph.py).

Runs as part of the standard `pytest tests/` suite (CI-2).
"""

from __future__ import annotations

from pathlib import Path
import unittest

from scripts.kb.github_customizations_graph import (
    extract_agent_skill_refs,
    extract_copilot_instruction_refs,
    extract_prompt_links,
    validate_hooks_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_ROOT = REPO_ROOT / ".github" / "agents"
SKILLS_ROOT = REPO_ROOT / ".github" / "skills"
HOOKS_JSON = REPO_ROOT / ".github" / "hooks" / "hooks.json"
COPILOT_INSTRUCTIONS = REPO_ROOT / ".github" / "copilot-instructions.md"
PROMPTS_DIR = REPO_ROOT / ".github" / "prompts"


class AgentSkillGraphTests(unittest.TestCase):
    """Every skill path referenced by agent personas exists on disk."""

    def test_agent_skill_refs_resolve(self) -> None:
        agent_refs = extract_agent_skill_refs(AGENTS_ROOT)
        self.assertTrue(agent_refs, "No agent files found")
        for persona, skill_names in agent_refs.items():
            for skill_name in skill_names:
                with self.subTest(persona=persona, skill=skill_name):
                    self.assertTrue(
                        (SKILLS_ROOT / skill_name / "SKILL.md").is_file(),
                        f"Agent '{persona}' references non-existent skill: {skill_name}",
                    )

    def test_all_agent_files_have_skill_refs(self) -> None:
        agent_refs = extract_agent_skill_refs(AGENTS_ROOT)
        for persona, skill_names in agent_refs.items():
            with self.subTest(persona=persona):
                self.assertTrue(
                    skill_names,
                    f"Agent '{persona}' has no extractable skill references",
                )


class CopilotInstructionsRefsTests(unittest.TestCase):
    """Every skill and script referenced in copilot-instructions.md exists."""

    def setUp(self) -> None:
        self.refs = extract_copilot_instruction_refs(COPILOT_INSTRUCTIONS)

    def test_copilot_instructions_skill_refs_resolve(self) -> None:
        for skill_name in self.refs["skills"]:
            with self.subTest(skill=skill_name):
                self.assertTrue(
                    (SKILLS_ROOT / skill_name / "SKILL.md").is_file(),
                    f"copilot-instructions.md references non-existent skill: {skill_name}",
                )

    def test_copilot_instructions_script_refs_resolve(self) -> None:
        for script_path in self.refs["scripts"]:
            with self.subTest(script=script_path):
                self.assertTrue(
                    (REPO_ROOT / script_path).is_file(),
                    f"copilot-instructions.md references non-existent script: {script_path}",
                )


class HooksJsonStructureTests(unittest.TestCase):
    """hooks.json is structurally valid and all referenced scripts exist."""

    def test_hooks_json_is_valid(self) -> None:
        errors = validate_hooks_json(HOOKS_JSON, REPO_ROOT)
        self.assertEqual(
            errors,
            [],
            f"hooks.json validation errors:\n" + "\n".join(errors),
        )


class PromptLinkTests(unittest.TestCase):
    """All local markdown links in .github/prompts/*.prompt.md resolve."""

    def test_prompt_local_links_resolve(self) -> None:
        prompt_links = extract_prompt_links(PROMPTS_DIR, REPO_ROOT)
        self.assertTrue(prompt_links, "No prompt files found")
        for filename, links in prompt_links.items():
            for target, ok in links:
                with self.subTest(file=filename, target=target):
                    self.assertTrue(
                        ok,
                        f"{filename}: broken link → {target}",
                    )


if __name__ == "__main__":
    unittest.main()
