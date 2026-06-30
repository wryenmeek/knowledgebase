"""Workflow contract checks for CI-2 read-only analyst diagnostics."""

from __future__ import annotations

from pathlib import Path
import re

from tests.kb._workflow_yaml import (
    extract_named_step_block,
    parse_job_mapping_block,
    parse_top_level_mapping_block,
)


WORKFLOW_PATH = Path(".github/workflows/ci-2-analyst-diagnostics.yml")


def _parse_top_level_mapping_block(text: str, key: str) -> dict[str, str]:
    return parse_top_level_mapping_block(text, key, workflow_path=WORKFLOW_PATH)


class TestCi2WorkflowContractTests:
    def setup_method(self) -> None:
        assert WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}"
        self.workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_ci2_metadata_and_triggers_are_explicit(self) -> None:
        assert "name: CI-2 Analyst Read-Only Diagnostics" in self.workflow_text
        assert "CI_ID: CI-2" in self.workflow_text
        assert "TOKEN_PROFILE: tp-analyst-readonly" in self.workflow_text
        assert 'CLOSURE_EVIDENCE_POLICY_START: "2026-06-29T00:00:00Z"' in self.workflow_text
        assert "push:" in self.workflow_text
        assert "pull_request:" in self.workflow_text
        assert "workflow_dispatch:" in self.workflow_text

    def test_permissions_match_tp_analyst_readonly(self) -> None:
        assert _parse_top_level_mapping_block(self.workflow_text, "permissions") == {
                "actions": "read",
                "checks": "read",
                "contents": "read",
            }
        assert re.search(r"(?im)^\s*(actions|checks|contents|pull-requests|issues|packages|id-token)\s*:\s*write\s*$", self.workflow_text) is None, "Workflow must not request write token scopes"
        # issues: read is scoped to the analyst-diagnostics job, not workflow level
        job_perms = parse_job_mapping_block(
            self.workflow_text, "analyst-diagnostics", "permissions", WORKFLOW_PATH
        )
        assert job_perms == {
                "actions": "read",
                "checks": "read",
                "contents": "read",
                "issues": "read",
            }, "analyst-diagnostics job must declare issues: read at job level"

    def test_workflow_yaml_syntax_validated_by_python_test_suite(self) -> None:
        # YAML syntax validation moved to WorkflowYamlSyntaxTests in the Python
        # test suite (issue #16: eliminate duplicate YAML parse in CI-2).
        # The Ruby Psych step was removed; CI-2 no longer parses workflow YAML directly.
        assert 'require "psych"' not in self.workflow_text
        assert "Psych.parse_file" not in self.workflow_text

    def test_workflow_is_diagnostics_only_with_explicit_failures(self) -> None:
        assert "Install pinned qmd runtime" in self.workflow_text
        assert "Set up Node.js" in self.workflow_text
        assert "uses: actions/setup-node@a0853c24544627f65ddf259abe73b1d18a591444" in self.workflow_text
        assert 'QMD_NPM_PACKAGE="@tobilu/qmd"' in self.workflow_text
        assert 'QMD_VERSION="2.5.1"' in self.workflow_text
        assert 'QMD_EXPECTED_INTEGRITY="sha512-Ep9ccOj1bNRinfTIszp5UZP8xfi5AJNtmzwWDD4ZVm2YdWVS+rFobWJQovj0HD2uIAFrryvbSpZYeGa3flEO7g=="' in self.workflow_text
        assert 'npm view "${QMD_NPM_PACKAGE}@${QMD_VERSION}" dist.integrity --registry=https://registry.npmjs.org' in self.workflow_text
        assert 'if [ "${QMD_DIST_INTEGRITY}" != "${QMD_EXPECTED_INTEGRITY}" ]; then' in self.workflow_text
        assert "::error::qmd dist.integrity mismatch" in self.workflow_text
        assert "exit 1" in self.workflow_text
        assert 'npm install --global "${QMD_NPM_PACKAGE}@${QMD_VERSION}" --registry=https://registry.npmjs.org' in self.workflow_text
        assert "qmd init" in self.workflow_text
        assert "cp .qmd/index.sqlite .qmd/index/index.sqlite" in self.workflow_text
        assert "cp .qmd/index.yml .qmd/index/index.yml" in self.workflow_text
        assert "python3 scripts/kb/qmd_preflight.py --repo-root ." in self.workflow_text
        assert ".ci-bin" not in self.workflow_text
        assert "cat > .ci-bin/qmd" not in self.workflow_text
        assert "python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py" in self.workflow_text
        assert "python3 scripts/kb/lint_wiki.py --wiki-root wiki --strict" in self.workflow_text
        assert "python3 -m pytest tests/ -q" in self.workflow_text
        assert "python3 scripts/validation/check_doc_freshness.py --scope wiki --path wiki/concepts --path wiki/entities --path wiki/analyses" in self.workflow_text
        assert "python3 -m scripts.validation.check_issue_closure_evidence" in self.workflow_text
        assert re.search(r"python3 -m scripts\.validation\.check_issue_closure_evidence.*?--lookback-days 3650.*?--issue-limit 500.*?--closed-after", self.workflow_text, flags=re.DOTALL) is not None, "Closure evidence command must include lookback, issue-limit, and closed-after flags"
        assert "--cov=scripts.validation._runtime_budget" in self.workflow_text
        assert "Secret scan (gitleaks)" in self.workflow_text
        assert "Dependency vulnerability audit (pip-audit)" in self.workflow_text
        assert "uses: actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f" in self.workflow_text
        assert "if: always()" in self.workflow_text
        assert "always() && (steps.diagnostics.outcome != 'success' || steps.closure-evidence.outcome != 'success' || steps.diagnostics.outputs.exit_code != '0' || steps.closure-evidence.outputs.closure_evidence_exit != '0' || steps.runtime-budget.outputs.overall_status == 'fail')" in self.workflow_text
        assert "Evaluate CI-2 runtime budgets" in self.workflow_text
        assert "schema/runtime-budgets.json" in self.workflow_text
        assert "diagnostics/runtime-budget-report.json" in self.workflow_text
        assert "exit 1" in self.workflow_text

        forbidden_write_or_release_commands = (
            "git push",
            "git commit",
            "gh pr",
            "scripts/kb/update_index.py --write",
            "scripts/kb/persist_query.py",
        )
        for forbidden in forbidden_write_or_release_commands:
            assert forbidden not in self.workflow_text

    def test_diagnostics_step_propagates_lint_and_test_failures(self) -> None:
        diagnostics_step = extract_named_step_block(
            self.workflow_text,
            "Run analyst diagnostics (lint + unit tests)",
            workflow_path=WORKFLOW_PATH,
        )
        assert "set -uo pipefail" in diagnostics_step
        assert "set +e" in diagnostics_step, "Diagnostics step must disable inherited bash -e so it can emit all outputs deterministically"

        closure_step = extract_named_step_block(
            self.workflow_text,
            "Check issue closure evidence",
            workflow_path=WORKFLOW_PATH,
        )
        assert "set -uo pipefail" in closure_step
        assert "set +e" in closure_step, "Closure-evidence step must disable inherited bash -e so closure_evidence_exit is always emitted"

        assert re.search(r"python3 \.github/skills/validate-wiki-governance/logic/validate_wiki_governance\.py.*?wrapper_exit=\"\$\{PIPESTATUS\[0\]\}\"", self.workflow_text, flags=re.DOTALL) is not None, "Wrapper command status must be captured for final diagnostics exit_code"
        assert re.search(r"python3 scripts/validation/check_doc_freshness\.py.*?freshness_exit=\"\$\{PIPESTATUS\[0\]\}\"", self.workflow_text, flags=re.DOTALL) is not None, "Freshness command status must be captured for final diagnostics exit_code"
        assert re.search(r"python3 scripts/reporting/content_quality_report\.py.*?quality_exit=\"\$\{PIPESTATUS\[0\]\}\"", self.workflow_text, flags=re.DOTALL) is not None, "Quality report command status must be captured for final diagnostics exit_code"
        # closure_evidence runs in its own dedicated step (issue #154: GH_TOKEN scoped to that step only)
        assert re.search(r"python3 -m scripts\.validation\.check_issue_closure_evidence.*?closure_evidence_exit=\"\$\{PIPESTATUS\[0\]\}\"", self.workflow_text, flags=re.DOTALL) is not None, "Closure evidence command status must be captured in the dedicated closure-evidence step"
        assert "steps.closure-evidence.outputs.closure_evidence_exit" in self.workflow_text, "Closure evidence exit must be propagated via steps.closure-evidence.outputs"
        assert re.search(r"python3 scripts/kb/lint_wiki\.py --wiki-root wiki --strict.*?lint_exit=\"\$\{PIPESTATUS\[0\]\}\"", self.workflow_text, flags=re.DOTALL) is not None, "Lint command status must be captured for final diagnostics exit_code"
        assert re.search(r"python3 -m pytest tests/ -q.*?tests_exit=\"\$\{PIPESTATUS\[0\]\}\"", self.workflow_text, flags=re.DOTALL) is not None, "Test command status must be captured for final diagnostics exit_code"
        assert 'if [ "${wrapper_exit}" -ne 0 ] || [ "${freshness_exit}" -ne 0 ] || [ "${quality_exit}" -ne 0 ] || [ "${lint_exit}" -ne 0 ] || [ "${tests_exit}" -ne 0 ]; then' in self.workflow_text
        assert "CLOSURE_EVIDENCE_EXIT" in self.workflow_text
        assert 'echo "exit_code=${diagnostics_exit}" >> "${GITHUB_OUTPUT}"' in self.workflow_text

    def test_closure_evidence_token_is_step_scoped(self) -> None:
        closure_step = extract_named_step_block(
            self.workflow_text,
            "Check issue closure evidence",
            workflow_path=WORKFLOW_PATH,
        )
        assert "GH_TOKEN: ${{ github.token }}" in closure_step, "Closure-evidence step must bind GH_TOKEN locally"

        diagnostics_step = extract_named_step_block(
            self.workflow_text,
            "Run analyst diagnostics (lint + unit tests)",
            workflow_path=WORKFLOW_PATH,
        )
        assert "GH_TOKEN:" not in diagnostics_step, "Diagnostics step must not bind GH_TOKEN across all commands"
        assert self.workflow_text.count("GH_TOKEN:") == 1, "CI-2 workflow must bind GH_TOKEN exactly once in the closure-evidence step"



class TestWorkflowYamlSyntaxTests:
    """Validate that all CI workflow YAML files parse cleanly (#16).

    This single Python-level check replaces the Ruby Psych step that previously
    ran in CI-2 as a separate workflow step. One canonical parse path is cheaper
    than two and keeps validation inside the pytest suite.
    """

    def test_all_workflow_yaml_files_parse_without_error(self) -> None:
        import yaml  # pyyaml — available in dev extras

        workflows_dir = Path(".github/workflows")
        assert workflows_dir.is_dir(), f"Missing workflows dir: {workflows_dir}"
        yaml_files = sorted(workflows_dir.glob("*.yml"))
        assert len(yaml_files) > 0, "No workflow YAML files found"
        errors: list[str] = []
        for yf in yaml_files:
            try:
                yaml.safe_load(yf.read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                errors.append(f"{yf}: {exc}")
        assert errors == [], "Workflow YAML syntax errors found:\n" + "\n".join(errors)

    def test_ci2_workflow_file_is_included_in_scanned_yaml_files(self) -> None:
        """CI-2's own workflow file must be in the YAML scan list.

        Guards against the file being accidentally deleted or moved, which would
        allow test_all_workflow_yaml_files_parse_without_error to still pass
        trivially while the CI-2 file went unvalidated.
        """
        workflows_dir = Path(".github/workflows")
        yaml_files = [f.name for f in sorted(workflows_dir.glob("*.yml"))]
        assert "ci-2-analyst-diagnostics.yml" in yaml_files, "ci-2-analyst-diagnostics.yml must be present and scanned by WorkflowYamlSyntaxTests"



