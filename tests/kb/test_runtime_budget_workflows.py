"""Workflow integration checks for runtime budget enforcement."""

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_BUDGET_SCHEMA_PATH = REPO_ROOT / "schema" / "runtime-budgets.json"

WORKFLOW_EXPECTATIONS: dict[str, dict[str, tuple[str, ...]]] = {
    ".github/workflows/ci-2-analyst-diagnostics.yml": {
        "workflow_ids": ("ci-2-analyst-diagnostics",),
        "report_paths": ("diagnostics/runtime-budget-report.json",),
    },
    ".github/workflows/ci-3-pr-producer.yml": {
        "workflow_ids": ("ci-3-pr-producer",),
        "report_paths": ("ci3-metrics/runtime-budget-report.json",),
    },
}


class RuntimeBudgetWorkflowIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime_budget_schema = json.loads(RUNTIME_BUDGET_SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_workflows_reference_runtime_budget_contract_and_summary_outputs(self) -> None:
        required_snippets = (
            "schema/runtime-budgets.json",
            "from scripts.validation import _runtime_budget",
            "GITHUB_STEP_SUMMARY",
        )
        for workflow_path in WORKFLOW_EXPECTATIONS:
            with self.subTest(workflow=workflow_path):
                text = Path(workflow_path).read_text(encoding="utf-8")
                for snippet in required_snippets:
                    self.assertIn(
                        snippet,
                        text,
                        f"{workflow_path} missing runtime budget integration snippet: {snippet}",
                    )

    def test_workflows_emit_expected_runtime_budget_workflow_ids(self) -> None:
        for workflow_path, expectation in WORKFLOW_EXPECTATIONS.items():
            with self.subTest(workflow=workflow_path):
                text = Path(workflow_path).read_text(encoding="utf-8")
                emitted_ids = sorted(set(re.findall(r'"workflow_id":\s*"([^"]+)"', text)))
                expected_ids = sorted(expectation["workflow_ids"])
                self.assertEqual(
                    emitted_ids,
                    expected_ids,
                    f"{workflow_path} runtime-budget workflow_id literals drifted",
                )
                for workflow_id in expected_ids:
                    self.assertIn(
                        workflow_id,
                        self.runtime_budget_schema["workflows"],
                        f"{workflow_path} references workflow_id not declared in schema/runtime-budgets.json: {workflow_id}",
                    )

    def test_workflow_stage_ids_match_runtime_budget_schema(self) -> None:
        for workflow_path, expectation in WORKFLOW_EXPECTATIONS.items():
            with self.subTest(workflow=workflow_path):
                text = Path(workflow_path).read_text(encoding="utf-8")
                stage_block_match = re.search(
                    r'"stage_durations_seconds"\s*:\s*\{(?P<body>.*?)\n\s*\}',
                    text,
                    flags=re.DOTALL,
                )
                self.assertIsNotNone(
                    stage_block_match,
                    f"{workflow_path} missing runtime metrics stage_durations_seconds block",
                )
                stage_block = stage_block_match.group("body")
                for workflow_id in expectation["workflow_ids"]:
                    stage_ids = sorted(self.runtime_budget_schema["workflows"][workflow_id]["stages"])
                    for stage_id in stage_ids:
                        self.assertRegex(
                            stage_block,
                            rf'"{re.escape(stage_id)}"\s*:',
                            f"{workflow_path} missing stage id from runtime budget schema: {workflow_id}.{stage_id}",
                        )

    def test_each_budgeted_job_has_warn_and_fail_gates(self) -> None:
        for workflow_path, expectation in WORKFLOW_EXPECTATIONS.items():
            with self.subTest(workflow=workflow_path):
                text = Path(workflow_path).read_text(encoding="utf-8")
                expected_budget_jobs = len(expectation["workflow_ids"])
                self.assertEqual(
                    text.count("id: runtime-budget"),
                    expected_budget_jobs,
                    f"{workflow_path} must evaluate runtime budgets once per budgeted job",
                )
                self.assertGreaterEqual(
                    text.count("overall_status == 'warn'"),
                    expected_budget_jobs,
                    f"{workflow_path} must include warn gate per budgeted job",
                )
                self.assertGreaterEqual(
                    text.count("overall_status == 'fail'"),
                    expected_budget_jobs,
                    f"{workflow_path} must include fail gate per budgeted job",
                )
                self.assertGreaterEqual(
                    text.count("exit 1"),
                    expected_budget_jobs,
                    f"{workflow_path} must fail closed on severe runtime-budget breach",
                )
                for report_path in expectation["report_paths"]:
                    self.assertIn(
                        report_path,
                        text,
                        f"{workflow_path} missing runtime budget report path: {report_path}",
                    )


if __name__ == "__main__":
    unittest.main()
