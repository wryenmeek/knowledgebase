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
        self.assertIn('CLOSURE_EVIDENCE_POLICY_START: "2026-05-25T00:00:00Z"', self.workflow_text)
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
        # issues: read is scoped to the analyst-diagnostics job, not workflow level
        from tests.kb._workflow_yaml import parse_job_mapping_block
        job_perms = parse_job_mapping_block(
            self.workflow_text, "analyst-diagnostics", "permissions", WORKFLOW_PATH
        )
        self.assertEqual(
            job_perms,
            {
                "actions": "read",
                "checks": "read",
                "contents": "read",
                "issues": "read",
            },
            "analyst-diagnostics job must declare issues: read at job level",
        )

    def test_workflow_yaml_syntax_validated_by_python_test_suite(self) -> None:
        # YAML syntax validation moved to WorkflowYamlSyntaxTests in the Python
        # test suite (issue #16: eliminate duplicate YAML parse in CI-2).
        # The Ruby Psych step was removed; CI-2 no longer parses workflow YAML directly.
        self.assertNotIn('require "psych"', self.workflow_text)
        self.assertNotIn("Psych.parse_file", self.workflow_text)

    def test_workflow_is_diagnostics_only_with_explicit_failures(self) -> None:
        self.assertIn("Install pinned qmd runtime", self.workflow_text)
        self.assertIn("Set up Node.js", self.workflow_text)
        self.assertIn("uses: actions/setup-node@a0853c24544627f65ddf259abe73b1d18a591444", self.workflow_text)
        self.assertIn('QMD_NPM_PACKAGE="@tobilu/qmd"', self.workflow_text)
        self.assertIn('QMD_VERSION="2.5.1"', self.workflow_text)
        self.assertIn(
            'QMD_EXPECTED_INTEGRITY="sha512-Ep9ccOj1bNRinfTIszp5UZP8xfi5AJNtmzwWDD4ZVm2YdWVS+rFobWJQovj0HD2uIAFrryvbSpZYeGa3flEO7g=="',
            self.workflow_text,
        )
        self.assertIn(
            'npm view "${QMD_NPM_PACKAGE}@${QMD_VERSION}" dist.integrity --registry=https://registry.npmjs.org',
            self.workflow_text,
        )
        self.assertIn(
            'if [ "${QMD_DIST_INTEGRITY}" != "${QMD_EXPECTED_INTEGRITY}" ]; then',
            self.workflow_text,
        )
        self.assertIn(
            "::error::qmd dist.integrity mismatch",
            self.workflow_text,
        )
        self.assertIn("exit 1", self.workflow_text)
        self.assertIn(
            'npm install --global "${QMD_NPM_PACKAGE}@${QMD_VERSION}" --registry=https://registry.npmjs.org',
            self.workflow_text,
        )
        self.assertIn("qmd init", self.workflow_text)
        self.assertIn("cp .qmd/index.sqlite .qmd/index/index.sqlite", self.workflow_text)
        self.assertIn("cp .qmd/index.yml .qmd/index/index.yml", self.workflow_text)
        self.assertIn("python3 scripts/kb/qmd_preflight.py --repo-root .", self.workflow_text)
        self.assertNotIn(".ci-bin", self.workflow_text)
        self.assertNotIn("cat > .ci-bin/qmd", self.workflow_text)
        self.assertIn(
            "python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py",
            self.workflow_text,
        )
        self.assertIn("python3 scripts/kb/lint_wiki.py --wiki-root wiki --strict", self.workflow_text)
        self.assertIn("python3 -m pytest tests/ -q", self.workflow_text)
        self.assertIn(
            "python3 -m scripts.validation.check_issue_closure_evidence",
            self.workflow_text,
        )
        self.assertIsNotNone(
            re.search(
                r"python3 -m scripts\.validation\.check_issue_closure_evidence.*?--lookback-days 3650.*?--issue-limit 500.*?--closed-after",
                self.workflow_text,
                flags=re.DOTALL,
            ),
            "Closure evidence command must include lookback, issue-limit, and closed-after flags",
        )
        self.assertIn("GH_TOKEN: ${{ github.token }}", self.workflow_text)
        self.assertIn("--cov=scripts.validation._runtime_budget", self.workflow_text)
        self.assertIn("Secret scan (gitleaks)", self.workflow_text)
        self.assertIn("Dependency vulnerability audit (pip-audit)", self.workflow_text)
        self.assertIn(
            "uses: actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f",
            self.workflow_text,
        )
        self.assertIn("if: always()", self.workflow_text)
        self.assertIn(
            "steps.diagnostics.outputs.exit_code != '0' || steps.closure-evidence.outputs.closure_evidence_exit != '0' || steps.runtime-budget.outputs.overall_status == 'fail'",
            self.workflow_text,
        )
        self.assertIn("Evaluate CI-2 runtime budgets", self.workflow_text)
        self.assertIn("schema/runtime-budgets.json", self.workflow_text)
        self.assertIn("diagnostics/runtime-budget-report.json", self.workflow_text)
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
        # closure_evidence runs in its own dedicated step (issue #154: GH_TOKEN scoped to that step only)
        self.assertIsNotNone(
            re.search(
                r"python3 -m scripts\.validation\.check_issue_closure_evidence.*?closure_evidence_exit=\"\$\{PIPESTATUS\[0\]\}\"",
                self.workflow_text,
                flags=re.DOTALL,
            ),
            "Closure evidence command status must be captured in the dedicated closure-evidence step",
        )
        self.assertIn(
            "steps.closure-evidence.outputs.closure_evidence_exit",
            self.workflow_text,
            "Closure evidence exit must be propagated via steps.closure-evidence.outputs",
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
        self.assertIn("CLOSURE_EVIDENCE_EXIT", self.workflow_text)
        self.assertIn('echo "exit_code=${diagnostics_exit}" >> "${GITHUB_OUTPUT}"', self.workflow_text)



class WorkflowYamlSyntaxTests(unittest.TestCase):
    """Validate that all CI workflow YAML files parse cleanly (#16).

    This single Python-level check replaces the Ruby Psych step that previously
    ran in CI-2 as a separate workflow step. One canonical parse path is cheaper
    than two and keeps validation inside the pytest suite.
    """

    def test_all_workflow_yaml_files_parse_without_error(self) -> None:
        import yaml  # pyyaml — available in dev extras

        workflows_dir = Path(".github/workflows")
        self.assertTrue(workflows_dir.is_dir(), f"Missing workflows dir: {workflows_dir}")
        yaml_files = sorted(workflows_dir.glob("*.yml"))
        self.assertGreater(len(yaml_files), 0, "No workflow YAML files found")
        errors: list[str] = []
        for yf in yaml_files:
            try:
                yaml.safe_load(yf.read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                errors.append(f"{yf}: {exc}")
        self.assertEqual(errors, [], "Workflow YAML syntax errors found:\n" + "\n".join(errors))

    def test_ci2_workflow_file_is_included_in_scanned_yaml_files(self) -> None:
        """CI-2's own workflow file must be in the YAML scan list.

        Guards against the file being accidentally deleted or moved, which would
        allow test_all_workflow_yaml_files_parse_without_error to still pass
        trivially while the CI-2 file went unvalidated.
        """
        workflows_dir = Path(".github/workflows")
        yaml_files = [f.name for f in sorted(workflows_dir.glob("*.yml"))]
        self.assertIn(
            "ci-2-analyst-diagnostics.yml",
            yaml_files,
            "ci-2-analyst-diagnostics.yml must be present and scanned by WorkflowYamlSyntaxTests",
        )


if __name__ == "__main__":
    unittest.main()
