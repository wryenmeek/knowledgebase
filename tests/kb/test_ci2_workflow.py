"""Workflow contract checks for CI-2 read-only analyst diagnostics."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


WORKFLOW_PATH = Path(".github/workflows/ci-2-analyst-diagnostics.yml")


def _parse_top_level_mapping_block(text: str, key: str) -> dict[str, str]:
    lines = text.splitlines()
    target = f"{key}:"

    for index, line in enumerate(lines):
        if line.strip() != target or line.startswith(" "):
            continue

        mapping: dict[str, str] = {}
        for candidate in lines[index + 1 :]:
            stripped = candidate.strip()
            if not stripped:
                continue
            if not candidate.startswith("  ") or candidate.startswith("    "):
                break
            if stripped.startswith("#") or ":" not in stripped:
                continue
            map_key, map_value = stripped.split(":", 1)
            mapping[map_key.strip()] = map_value.strip()

        return mapping

    raise AssertionError(f"Top-level '{key}' block is missing from {WORKFLOW_PATH}")


class Ci2WorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}")
        self.workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_ci2_metadata_and_triggers_are_explicit(self) -> None:
        self.assertIn("name: CI-2 Analyst Read-Only Diagnostics", self.workflow_text)
        self.assertIn("CI_ID: CI-2", self.workflow_text)
        self.assertIn("TOKEN_PROFILE: tp-analyst-readonly", self.workflow_text)
        self.assertIn("push:", self.workflow_text)
        self.assertIn("pull_request:", self.workflow_text)
        self.assertIn("workflow_dispatch:", self.workflow_text)

    def test_permissions_match_tp_analyst_readonly(self) -> None:
        self.assertEqual(
            _parse_top_level_mapping_block(self.workflow_text, "permissions"),
            {
                "actions": "read",
                "checks": "read",
                "contents": "read",
            },
        )
        self.assertIsNone(
            re.search(
                r"(?im)^\s*(actions|checks|contents|pull-requests|issues|packages|id-token)\s*:\s*write\s*$",
                self.workflow_text,
            ),
            "Workflow must not request write token scopes",
        )

    def test_workflow_yaml_syntax_validation_is_explicit(self) -> None:
        required_controls = (
            "Validate workflow YAML syntax",
            'require "psych"',
            'Dir.glob(".github/workflows/*.yml").sort.each do |workflow_path|',
            "Psych.parse_file(workflow_path)",
            "rescue Psych::SyntaxError => err",
            'warn "::error file=#{workflow_path}::#{err.message}"',
        )
        for control in required_controls:
            self.assertIn(control, self.workflow_text)

    def test_workflow_is_diagnostics_only_with_explicit_failures(self) -> None:
        self.assertIn("python3 scripts/kb/lint_wiki.py --wiki-root wiki --strict", self.workflow_text)
        self.assertIn("python3 -m unittest discover -s tests -p 'test_*.py'", self.workflow_text)
        self.assertIn(
            "uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
            self.workflow_text,
        )
        self.assertIn("if: always()", self.workflow_text)
        self.assertIn("if: steps.diagnostics.outputs.exit_code != '0'", self.workflow_text)
        self.assertIn("exit 1", self.workflow_text)

        forbidden_write_or_release_commands = (
            "git push",
            "git commit",
            "gh pr",
            "scripts/kb/update_index.py --write",
            "scripts/kb/persist_query.py",
        )
        for forbidden in forbidden_write_or_release_commands:
            self.assertNotIn(forbidden, self.workflow_text)

    def test_diagnostics_step_propagates_lint_and_test_failures(self) -> None:
        self.assertIsNotNone(
            re.search(
                r"python3 scripts/kb/lint_wiki\.py --wiki-root wiki --strict.*?lint_exit=\"\$\{PIPESTATUS\[0\]\}\"",
                self.workflow_text,
                flags=re.DOTALL,
            ),
            "Lint command status must be captured for final diagnostics exit_code",
        )
        self.assertIsNotNone(
            re.search(
                r"python3 -m unittest discover -s tests -p 'test_\*\.py'.*?tests_exit=\"\$\{PIPESTATUS\[0\]\}\"",
                self.workflow_text,
                flags=re.DOTALL,
            ),
            "Test command status must be captured for final diagnostics exit_code",
        )
        self.assertIn(
            'if [ "${lint_exit}" -ne 0 ] || [ "${tests_exit}" -ne 0 ]; then',
            self.workflow_text,
        )
        self.assertIn('echo "exit_code=${diagnostics_exit}" >> "${GITHUB_OUTPUT}"', self.workflow_text)


if __name__ == "__main__":
    unittest.main()
