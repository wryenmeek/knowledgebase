"""Workflow integration checks for runtime budget enforcement."""

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_BUDGET_SCHEMA_PATH = REPO_ROOT / "schema" / "runtime-budgets.json"

WORKFLOW_EXPECTATIONS: dict[str, dict[str, object]] = {
    ".github/workflows/ci-2-analyst-diagnostics.yml": {
        "workflow_ids": {
            "ci-2-analyst-diagnostics": (
                "validate_wiki_governance",
                "check_doc_freshness",
                "content_quality_summary",
                "lint_wiki_strict",
                "pytest_suite",
            ),
        },
        "metrics_paths": ("diagnostics/runtime-metrics.json",),
        "report_paths": ("diagnostics/runtime-budget-report.json",),
    },
    ".github/workflows/ci-3-pr-producer.yml": {
        "workflow_ids": {
            "ci-3-pr-producer": (
                "ingest_write_path",
                "update_index_write",
                "lint_wiki_strict",
                "persist_query_gate",
            ),
        },
        "metrics_paths": ("ci3-metrics/runtime-metrics.json",),
        "report_paths": ("ci3-metrics/runtime-budget-report.json",),
    },
    ".github/workflows/ci-5-github-monitor.yml": {
        "workflow_ids": {
            "ci-5-check-drift": ("check_drift",),
            "ci-5-fetch-and-update": ("fetch_content",),
            "ci-5-classify-drift": (
                "classify_drift",
                "create_issues",
                "close_resolved_issues",
            ),
            "ci-5-synthesize": ("synthesize_diff",),
        },
        "metrics_paths": (
            "runtime-metrics/check-drift-runtime-metrics.json",
            "runtime-metrics/fetch-runtime-metrics.json",
            "runtime-metrics/classify-runtime-metrics.json",
            "runtime-metrics/synthesize-runtime-metrics.json",
        ),
        "report_paths": (
            "runtime-metrics/check-drift-runtime-budget-report.json",
            "runtime-metrics/fetch-runtime-budget-report.json",
            "runtime-metrics/classify-runtime-budget-report.json",
            "runtime-metrics/synthesize-runtime-budget-report.json",
        ),
    },
    ".github/workflows/ci-6-google-drive-monitor.yml": {
        "workflow_ids": {
            "ci-6-check-drift": ("check_drift",),
            "ci-6-fetch-and-update": ("fetch_content",),
            "ci-6-classify-drift": (
                "classify_drift",
                "create_issues",
            ),
            "ci-6-synthesize": ("synthesize_diff",),
            "ci-6-advance-cursor": ("advance_cursor",),
        },
        "metrics_paths": (
            "runtime-metrics/check-drift-runtime-metrics.json",
            "runtime-metrics/fetch-runtime-metrics.json",
            "runtime-metrics/classify-runtime-metrics.json",
            "runtime-metrics/synthesize-runtime-metrics.json",
            "runtime-metrics/advance-cursor-runtime-metrics.json",
        ),
        "report_paths": (
            "runtime-metrics/check-drift-runtime-budget-report.json",
            "runtime-metrics/fetch-runtime-budget-report.json",
            "runtime-metrics/classify-runtime-budget-report.json",
            "runtime-metrics/synthesize-runtime-budget-report.json",
            "runtime-metrics/advance-cursor-runtime-budget-report.json",
        ),
    },
}


class RuntimeBudgetWorkflowIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime_budget_schema = json.loads(RUNTIME_BUDGET_SCHEMA_PATH.read_text(encoding="utf-8"))

    def _extract_stage_ids_for_workflow(self, *, workflow_text: str, workflow_id: str) -> tuple[str, ...]:
        literal_block_match = re.search(
            rf'"workflow_id"\s*:\s*"{re.escape(workflow_id)}"\s*,\s*"stage_durations_seconds"\s*:\s*\{{(?P<body>.*?)\n\s*\}}',
            workflow_text,
            flags=re.DOTALL,
        )
        if literal_block_match:
            stage_block = literal_block_match.group("body")
            return tuple(sorted(set(re.findall(r'"([^"]+)"\s*:', stage_block))))

        dynamic_block_match = re.search(
            rf'"workflow_id"\s*:\s*"{re.escape(workflow_id)}"\s*,\s*"stage_durations_seconds"\s*:\s*stage_durations',
            workflow_text,
            flags=re.DOTALL,
        )
        if dynamic_block_match:
            workflow_id_parts = workflow_id.split("-", maxsplit=2)
            if len(workflow_id_parts) != 3:
                return tuple()
            job_id = workflow_id_parts[2]
            job_block_match = re.search(
                rf"^  {re.escape(job_id)}:\n(?P<body>.*?)(?=^  [a-z0-9-]+:\n|\Z)",
                workflow_text,
                flags=re.DOTALL | re.MULTILINE,
            )
            if not job_block_match:
                return tuple()
            job_block = job_block_match.group("body")
            stage_ids = re.findall(
                r'echo "([a-z0-9_]+)=\$\{[a-z0-9_]+\}" >> runtime-metrics/classify-stage-durations\.env',
                job_block,
            )
            return tuple(sorted(set(stage_ids)))

        return tuple()

    def test_dynamic_stage_extraction_scopes_to_matching_job_block(self) -> None:
        synthetic_workflow = """
  classify-drift:
    steps:
      - run: |
          echo "classify_drift=${classify_duration}" >> runtime-metrics/classify-stage-durations.env
          echo "create_issues=${create_issues_duration}" >> runtime-metrics/classify-stage-durations.env
          metrics = {
              "workflow_id": "ci-6-classify-drift",
              "stage_durations_seconds": stage_durations,
          }
  unrelated-job:
    steps:
      - run: |
          echo "should_not_match=${x}" >> runtime-metrics/classify-stage-durations.env
"""
        emitted_stage_ids = self._extract_stage_ids_for_workflow(
            workflow_text=synthetic_workflow,
            workflow_id="ci-6-classify-drift",
        )
        self.assertEqual(emitted_stage_ids, ("classify_drift", "create_issues"))

    def test_workflows_reference_runtime_budget_contract_and_summary_outputs(self) -> None:
        required_snippets = (
            "schema/runtime-budgets.json",
            "python3 -m scripts.validation.evaluate_runtime_budget",
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

    def test_schema_workflow_scope_matches_runtime_budget_integrations(self) -> None:
        expected_workflow_ids = {
            workflow_id
            for expectation in WORKFLOW_EXPECTATIONS.values()
            for workflow_id in expectation["workflow_ids"]
        }
        self.assertEqual(
            set(self.runtime_budget_schema["workflows"]),
            expected_workflow_ids,
            "schema/runtime-budgets.json must declare exactly the workflow IDs that execute runtime-budget evaluation",
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

    def test_workflow_stage_ids_match_runtime_budget_schema_and_workflow_literals(self) -> None:
        for workflow_path, expectation in WORKFLOW_EXPECTATIONS.items():
            with self.subTest(workflow=workflow_path):
                text = Path(workflow_path).read_text(encoding="utf-8")
                for workflow_id, expected_stage_ids in expectation["workflow_ids"].items():
                    with self.subTest(workflow_id=workflow_id):
                        schema_stage_ids = tuple(sorted(self.runtime_budget_schema["workflows"][workflow_id]["stages"]))
                        expected_stage_ids_sorted = tuple(sorted(expected_stage_ids))
                        emitted_stage_ids = self._extract_stage_ids_for_workflow(
                            workflow_text=text,
                            workflow_id=workflow_id,
                        )
                        self.assertEqual(
                            schema_stage_ids,
                            expected_stage_ids_sorted,
                            f"schema/runtime-budgets.json stage IDs drifted for {workflow_id}",
                        )
                        self.assertEqual(
                            emitted_stage_ids,
                            expected_stage_ids_sorted,
                            f"{workflow_path} stage IDs must match schema/runtime-budgets.json exactly for {workflow_id}",
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
                for metrics_path in expectation["metrics_paths"]:
                    self.assertIn(
                        metrics_path,
                        text,
                        f"{workflow_path} missing runtime metrics path: {metrics_path}",
                    )
                for report_path in expectation["report_paths"]:
                    self.assertIn(
                        report_path,
                        text,
                        f"{workflow_path} missing runtime budget report path: {report_path}",
                    )


if __name__ == "__main__":
    unittest.main()
