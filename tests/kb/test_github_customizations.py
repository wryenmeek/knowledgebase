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

    def test_nonexistent_script_paths_return_errors(self) -> None:
        import tempfile, json
        cases = (
            ("bash scripts/hooks/no_such_script_xyz.sh", "missing script"),
            ("python3 scripts/hooks/no_such_hook_xyz.py", "missing Python script"),
        )
        for command, expected in cases:
            with self.subTest(command=command):
                data = {
                    "hooks": {
                        "SessionStart": [{"command": command}],
                        "PreToolUse": [{"command": "echo pre"}],
                        "PostToolUse": [{"command": "echo post"}],
                        "Stop": [{"command": "echo stop"}],
                    }
                }
                with tempfile.TemporaryDirectory() as tmp:
                    p = self._write_hooks(Path(tmp), json.dumps(data))
                    errors = validate_hooks_json(p, REPO_ROOT)
                    self.assertTrue(
                        any(expected in e for e in errors),
                        f"Expected {expected} error, got: {errors}",
                    )

    def test_registered_python_path_must_match_actual_filename_after_rename(self) -> None:
        import tempfile, json
        data = {
            "hooks": {
                "SessionStart": [{"command": "bash .github/hooks/session-start.sh"}],
                "PreToolUse": [{"command": "echo pre"}],
                "PostToolUse": [
                    {
                        "command": "python3 scripts/hooks/locality_postuse_advisor.py",
                    }
                ],
                "Stop": [{"command": "bash .github/hooks/simplify-ignore.sh"}],
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_hooks(Path(tmp), json.dumps(data))
            errors = validate_hooks_json(p, REPO_ROOT)
            self.assertTrue(
                any("locality_postuse_advisor.py" in e for e in errors),
                f"Expected stale renamed Python hook path error, got: {errors}",
            )


class HooksJsonStructureTests(unittest.TestCase):
    """hooks.json is structurally valid and all referenced scripts exist."""

    def test_hooks_json_is_valid(self) -> None:
        errors = validate_hooks_json(HOOKS_JSON, REPO_ROOT)
        for err in errors:
            with self.subTest(error=err):
                self.fail(f"hooks.json validation error: {err}")

    def test_posttooluse_edit_matcher_is_anchored(self) -> None:
        import json, re
        hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
        matchers = [
            entry["matcher"]
            for entry in hooks["PostToolUse"]
            if entry.get("command") == "python3 scripts/hooks/locality_postuse_advisory.py"
        ]

        self.assertEqual(len(matchers), 1)
        matcher = re.compile(matchers[0])
        self.assertIsNotNone(matcher.fullmatch("edit"))
        self.assertIsNotNone(matcher.fullmatch("Edit"))
        self.assertIsNone(matcher.search("prefix_edit_suffix"))
        self.assertIsNone(matcher.search("EditExtra"))


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


class ValidateHooksJsonEdgeCaseTests(unittest.TestCase):
    """Edge-case coverage for validate_hooks_json branches."""

    def _write_hooks(self, tmp: Path, content: str) -> Path:
        p = tmp / "hooks.json"
        p.write_text(content, encoding="utf-8")
        return p

    def test_missing_hooks_key_returns_error(self) -> None:
        import tempfile, json
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_hooks(Path(tmp), json.dumps({"notHooks": {}}))
            errors = validate_hooks_json(p, REPO_ROOT)
            self.assertTrue(any("missing top-level 'hooks'" in e for e in errors), errors)

    def test_hooks_value_not_a_dict_returns_error(self) -> None:
        import tempfile, json
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_hooks(Path(tmp), json.dumps({"hooks": "notadict"}))
            errors = validate_hooks_json(p, REPO_ROOT)
            self.assertTrue(any("mapping" in e for e in errors), errors)

    def test_event_value_not_a_list_returns_error(self) -> None:
        import tempfile, json
        data = {
            "hooks": {
                "SessionStart": "shouldbelist",
                "PreToolUse": [{"command": "echo pre"}],
                "PostToolUse": [{"command": "echo post"}],
                "Stop": [{"command": "echo stop"}],
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_hooks(Path(tmp), json.dumps(data))
            errors = validate_hooks_json(p, REPO_ROOT)
            self.assertTrue(any("must be a list" in e for e in errors), errors)

    def test_hook_entry_not_a_dict_returns_error(self) -> None:
        import tempfile, json
        data = {
            "hooks": {
                "SessionStart": ["notadict"],
                "PreToolUse": [{"command": "echo pre"}],
                "PostToolUse": [{"command": "echo post"}],
                "Stop": [{"command": "echo stop"}],
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_hooks(Path(tmp), json.dumps(data))
            errors = validate_hooks_json(p, REPO_ROOT)
            self.assertTrue(any("must be a dict" in e for e in errors), errors)

    def test_cannot_read_file_returns_error(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "missing.json"
            errors = validate_hooks_json(p, REPO_ROOT)
            self.assertTrue(any("Cannot read" in e for e in errors), errors)


class ExtractAgentSkillRefsFallbackTests(unittest.TestCase):
    """Tests for extract_agent_skill_refs fallback path (no Required skills section)."""

    def test_agent_with_no_required_section_falls_back_to_full_text(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            agents_root = Path(tmp)
            # Agent file with a skill ref but no "Required skills" heading
            (agents_root / "fake-agent.md").write_text(
                "# Fake Agent\n\n"
                "Use `.github/skills/incremental-implementation/SKILL.md` for builds.\n",
                encoding="utf-8",
            )
            result = extract_agent_skill_refs(agents_root)
            self.assertIn("fake-agent", result)
            self.assertIn("incremental-implementation", result["fake-agent"])

    def test_agent_with_no_skill_refs_anywhere_returns_empty_list(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            agents_root = Path(tmp)
            (agents_root / "bare-agent.md").write_text(
                "# Bare Agent\n\nNo skills referenced here.\n",
                encoding="utf-8",
            )
            result = extract_agent_skill_refs(agents_root)
            self.assertIn("bare-agent", result)
            self.assertEqual(result["bare-agent"], [])


class ExtractCopilotInstructionRefsTests(unittest.TestCase):
    """Tests for script path extraction from copilot instructions."""

    def test_extracts_python3_script_paths(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            instructions = Path(tmp) / "copilot-instructions.md"
            instructions.write_text(
                "Run `python3 scripts/kb/ingest.py` to ingest.\n"
                "Or `python3 scripts/kb/lint_wiki.py --strict`.\n",
                encoding="utf-8",
            )
            result = extract_copilot_instruction_refs(instructions)
            self.assertIn("scripts/kb/ingest.py", result["scripts"])
            self.assertIn("scripts/kb/lint_wiki.py", result["scripts"])

    def test_extracts_skill_paths(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            instructions = Path(tmp) / "copilot-instructions.md"
            instructions.write_text(
                "Use `.github/skills/incremental-implementation/SKILL.md` skill.\n",
                encoding="utf-8",
            )
            result = extract_copilot_instruction_refs(instructions)
            self.assertIn("incremental-implementation", result["skills"])


class ExtractPromptLinksEdgeCaseTests(unittest.TestCase):
    """Tests for extract_prompt_links edge cases."""

    def test_external_links_skipped(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            prompts_dir = Path(tmp)
            repo_root = Path(tmp)
            (prompts_dir / "test.prompt.md").write_text(
                "See [external](https://example.com/page) for details.\n",
                encoding="utf-8",
            )
            result = extract_prompt_links(prompts_dir, repo_root)
            # External links should not appear in results
            self.assertIn("test.prompt.md", result)
            self.assertEqual(result["test.prompt.md"], [])

    def test_anchor_only_links_skipped(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            prompts_dir = Path(tmp)
            repo_root = Path(tmp)
            (prompts_dir / "test2.prompt.md").write_text(
                "See [section](#my-section) for details.\n",
                encoding="utf-8",
            )
            result = extract_prompt_links(prompts_dir, repo_root)
            self.assertIn("test2.prompt.md", result)
            # Anchor-only links have no path; should be skipped
            self.assertEqual(result["test2.prompt.md"], [])

    def test_local_file_link_resolution(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            prompts_dir = repo_root / ".github" / "prompts"
            prompts_dir.mkdir(parents=True)
            real_file = repo_root / "docs" / "architecture.md"
            real_file.parent.mkdir(parents=True)
            real_file.write_text("content", encoding="utf-8")
            (prompts_dir / "local.prompt.md").write_text(
                "[architecture](docs/architecture.md)\n",
                encoding="utf-8",
            )
            result = extract_prompt_links(prompts_dir, repo_root)
            self.assertIn("local.prompt.md", result)
            links = result["local.prompt.md"]
            self.assertTrue(any(target == "docs/architecture.md" and ok for target, ok in links))

    def test_mailto_links_skipped(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            prompts_dir = Path(tmp)
            repo_root = Path(tmp)
            (prompts_dir / "email.prompt.md").write_text(
                "Contact [us](mailto:admin@example.com).\n",
                encoding="utf-8",
            )
            result = extract_prompt_links(prompts_dir, repo_root)
            self.assertIn("email.prompt.md", result)
            self.assertEqual(result["email.prompt.md"], [])


class SectionBodyAndResolveLinkTests(unittest.TestCase):
    """Tests for _section_body and _resolve_link private helpers."""

    def _section_body(self, text: str, heading: str) -> str:
        from scripts.kb.github_customizations_graph import _section_body
        return _section_body(text, heading)

    def _resolve_link(self, source: Path, target: str, repo_root: Path) -> Path:
        from scripts.kb.github_customizations_graph import _resolve_link
        return _resolve_link(source, target, repo_root)

    def test_section_body_heading_not_found_returns_empty(self) -> None:
        result = self._section_body("# Title\n\nSome content.\n", "## Missing heading")
        self.assertEqual(result, "")

    def test_section_body_extracts_until_next_heading(self) -> None:
        text = "# Title\n\n## First\nFirst body.\n\n## Second\nSecond body.\n"
        result = self._section_body(text, "## First")
        self.assertIn("First body", result)
        self.assertNotIn("Second body", result)

    def test_section_body_no_next_heading_returns_rest(self) -> None:
        text = "# Title\n\n## Only\nRest of content here.\n"
        result = self._section_body(text, "## Only")
        self.assertIn("Rest of content here", result)

    def test_resolve_link_absolute_target_clamped_to_repo_root(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            source = repo_root / ".github" / "prompts" / "test.prompt.md"
            result = self._resolve_link(source, "/etc/passwd", repo_root)
            # Should resolve to repo_root / "etc" / "passwd", not actual /etc/passwd
            self.assertTrue(str(result).startswith(str(repo_root.resolve())))

    def test_resolve_link_agents_md_resolves_from_repo_root(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            source = repo_root / ".github" / "prompts" / "test.prompt.md"
            result = self._resolve_link(source, "AGENTS.md", repo_root)
            self.assertEqual(result, (repo_root / "AGENTS.md").resolve())

    def test_resolve_link_readme_resolves_from_repo_root(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            source = repo_root / ".github" / "prompts" / "test.prompt.md"
            result = self._resolve_link(source, "README.md", repo_root)
            self.assertEqual(result, (repo_root / "README.md").resolve())

    def test_resolve_link_docs_prefix_resolves_from_repo_root(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            source = repo_root / ".github" / "prompts" / "test.prompt.md"
            result = self._resolve_link(source, "docs/architecture.md", repo_root)
            self.assertEqual(result, (repo_root / "docs" / "architecture.md").resolve())

    def test_resolve_link_relative_resolves_from_source_parent(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            source = repo_root / "sub" / "dir" / "file.md"
            result = self._resolve_link(source, "sibling.md", repo_root)
            self.assertEqual(result, (repo_root / "sub" / "dir" / "sibling.md").resolve())


if __name__ == "__main__":
    unittest.main()
