"""Workflow contract checks for CI-2 read-only analyst diagnostics."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from tests.kb._workflow_yaml import parse_top_level_mapping_block


WORKFLOW_PATH = Path(".github/workflows/ci-2-analyst-diagnostics.yml")


def _parse_top_level_mapping_block(text: str, key: str) -> dict[str, str]:
    return parse_top_level_mapping_block(text, key, workflow_path=WORKFLOW_PATH)


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
        self.assertIn("Bootstrap repo-local qmd preflight shim", self.workflow_text)
        self.assertIn("mkdir -p .ci-bin .qmd/index", self.workflow_text)
        self.assertIn('printf \'%s\\n\' "${PWD}/.ci-bin" >> "${GITHUB_PATH}"', self.workflow_text)
        self.assertIn(
            "python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py",
            self.workflow_text,
        )
        self.assertIn("python3 scripts/kb/lint_wiki.py --wiki-root wiki --strict", self.workflow_text)
        self.assertIn("python3 -m pytest tests/ -q", self.workflow_text)
        self.assertIn(
            "uses: actions/upload-artifact@4cec3d8aa04e39d1a68397de0c4cd6fb9dce8ec1",
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
                r"python3 \.github/skills/validate-wiki-governance/logic/validate_wiki_governance\.py.*?wrapper_exit=\"\$\{PIPESTATUS\[0\]\}\"",
                self.workflow_text,
                flags=re.DOTALL,
            ),
            "Wrapper command status must be captured for final diagnostics exit_code",
        )
        self.assertIsNotNone(
            re.search(
                r"python3 scripts/validation/check_doc_freshness\.py.*?freshness_exit=\"\$\{PIPESTATUS\[0\]\}\"",
                self.workflow_text,
                flags=re.DOTALL,
            ),
            "Freshness command status must be captured for final diagnostics exit_code",
        )
        self.assertIsNotNone(
            re.search(
                r"python3 scripts/reporting/content_quality_report\.py.*?quality_exit=\"\$\{PIPESTATUS\[0\]\}\"",
                self.workflow_text,
                flags=re.DOTALL,
            ),
            "Quality report command status must be captured for final diagnostics exit_code",
        )
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
                r"python3 -m pytest tests/ -q.*?tests_exit=\"\$\{PIPESTATUS\[0\]\}\"",
                self.workflow_text,
                flags=re.DOTALL,
            ),
            "Test command status must be captured for final diagnostics exit_code",
        )
        self.assertIn(
            'if [ "${wrapper_exit}" -ne 0 ] || [ "${freshness_exit}" -ne 0 ] || [ "${quality_exit}" -ne 0 ] || [ "${lint_exit}" -ne 0 ] || [ "${tests_exit}" -ne 0 ]; then',
            self.workflow_text,
        )
        self.assertIn('echo "exit_code=${diagnostics_exit}" >> "${GITHUB_OUTPUT}"', self.workflow_text)


if __name__ == "__main__":
    unittest.main()
