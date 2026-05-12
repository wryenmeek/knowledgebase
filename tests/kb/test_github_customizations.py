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

    _AGENT_SKILL_EXEMPT: frozenset[str] = frozenset()
    """Persona names exempt from the has-skill-refs check (for transition period)."""

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
            if persona in self._AGENT_SKILL_EXEMPT:
                continue
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

    def test_copilot_instructions_has_refs(self) -> None:
        total = len(self.refs["skills"]) + len(self.refs["scripts"])
        self.assertGreater(total, 0, "copilot-instructions.md has no extractable skill or script refs")

    def test_copilot_instructions_script_refs_resolve(self) -> None:
        for script_path in self.refs["scripts"]:
            with self.subTest(script=script_path):
                self.assertTrue(
                    (REPO_ROOT / script_path).is_file(),
                    f"copilot-instructions.md references non-existent script: {script_path}",
                )


class ValidateHooksJsonUnitTests(unittest.TestCase):
    """Unit tests for validate_hooks_json using tmp_path-style fixtures."""

    def _write_hooks(self, tmp: Path, content: str) -> Path:
        p = tmp / "hooks.json"
        p.write_text(content, encoding="utf-8")
        return p

    def test_valid_hooks_returns_no_errors(self) -> None:
        import tempfile, json
        data = {
            "hooks": {
                "SessionStart": [{"command": "echo start"}],
                "PreToolUse": [{"command": "echo pre"}],
                "PostToolUse": [{"command": "echo post"}],
                "Stop": [{"command": "echo stop"}],
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_hooks(Path(tmp), json.dumps(data))
            errors = validate_hooks_json(p, REPO_ROOT)
            self.assertEqual(errors, [])

    def test_invalid_json_returns_error(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_hooks(Path(tmp), "{invalid json")
            errors = validate_hooks_json(p, REPO_ROOT)
            self.assertTrue(any("JSON" in e or "parse" in e.lower() for e in errors), errors)

    def test_missing_event_key_returns_error(self) -> None:
        import tempfile, json
        data = {"hooks": {"SessionStart": [{"command": "echo s"}], "Stop": [{"command": "echo x"}]}}
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_hooks(Path(tmp), json.dumps(data))
            errors = validate_hooks_json(p, REPO_ROOT)
            missing = [e for e in errors if "PreToolUse" in e or "PostToolUse" in e]
            self.assertTrue(missing, f"Expected missing-event errors, got: {errors}")

    def test_missing_command_field_returns_error(self) -> None:
        import tempfile, json
        data = {
            "hooks": {
                "SessionStart": [{"notcommand": "echo s"}],
                "PreToolUse": [{"command": "echo pre"}],
                "PostToolUse": [{"command": "echo post"}],
                "Stop": [{"command": "echo stop"}],
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_hooks(Path(tmp), json.dumps(data))
            errors = validate_hooks_json(p, REPO_ROOT)
            self.assertTrue(errors, f"Expected error for missing 'command' key, got none")

    def test_nonexistent_script_path_returns_error(self) -> None:
        import tempfile, json
        data = {
            "hooks": {
                "SessionStart": [{"command": "bash scripts/hooks/no_such_script_xyz.sh"}],
                "PreToolUse": [{"command": "echo pre"}],
                "PostToolUse": [{"command": "echo post"}],
                "Stop": [{"command": "echo stop"}],
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_hooks(Path(tmp), json.dumps(data))
            errors = validate_hooks_json(p, REPO_ROOT)
            self.assertTrue(errors, f"Expected error for missing script, got none")


class HooksJsonStructureTests(unittest.TestCase):
    """hooks.json is structurally valid and all referenced scripts exist."""

    def test_hooks_json_is_valid(self) -> None:
        errors = validate_hooks_json(HOOKS_JSON, REPO_ROOT)
        for err in errors:
            with self.subTest(error=err):
                self.fail(f"hooks.json validation error: {err}")


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
