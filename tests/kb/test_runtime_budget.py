"""Tests for deterministic runtime budget evaluation helpers."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.validation import _runtime_budget


REPO_ROOT = Path(__file__).resolve().parents[2]


class RuntimeBudgetClassificationTests(unittest.TestCase):
    def test_classify_stage_result_respects_warn_and_fail_thresholds(self) -> None:
        self.assertEqual(
            _runtime_budget.classify_stage_result(duration_seconds=10, warn_seconds=10, fail_seconds=20),
            _runtime_budget.STATUS_OK,
        )
        self.assertEqual(
            _runtime_budget.classify_stage_result(duration_seconds=11, warn_seconds=10, fail_seconds=20),
            _runtime_budget.STATUS_WARN,
        )
        self.assertEqual(
            _runtime_budget.classify_stage_result(duration_seconds=20, warn_seconds=10, fail_seconds=20),
            _runtime_budget.STATUS_WARN,
        )
        self.assertEqual(
            _runtime_budget.classify_stage_result(duration_seconds=21, warn_seconds=10, fail_seconds=20),
            _runtime_budget.STATUS_FAIL,
        )

    def test_aggregate_overall_status_returns_highest_severity(self) -> None:
        self.assertEqual(
            _runtime_budget.aggregate_overall_status([_runtime_budget.STATUS_OK, _runtime_budget.STATUS_OK]),
            _runtime_budget.STATUS_OK,
        )
        self.assertEqual(
            _runtime_budget.aggregate_overall_status([_runtime_budget.STATUS_OK, _runtime_budget.STATUS_WARN]),
            _runtime_budget.STATUS_WARN,
        )
        self.assertEqual(
            _runtime_budget.aggregate_overall_status([_runtime_budget.STATUS_WARN, _runtime_budget.STATUS_FAIL]),
            _runtime_budget.STATUS_FAIL,
        )

    def test_classify_stage_result_rejects_invalid_inputs_and_thresholds(self) -> None:
        self.assertEqual(
            _runtime_budget.classify_stage_result(duration_seconds=0, warn_seconds=10, fail_seconds=20),
            _runtime_budget.STATUS_OK,
        )
        with self.assertRaises(ValueError):
            _runtime_budget.classify_stage_result(duration_seconds=10, warn_seconds=20, fail_seconds=20)
        with self.assertRaises(ValueError):
            _runtime_budget.classify_stage_result(duration_seconds=-1, warn_seconds=10, fail_seconds=20)
        with self.assertRaises(ValueError):
            _runtime_budget.classify_stage_result(duration_seconds=True, warn_seconds=10, fail_seconds=20)
        with self.assertRaises(ValueError):
            _runtime_budget.classify_stage_result(duration_seconds=1, warn_seconds=10, fail_seconds=False)

    def test_parse_runtime_budgets_rejects_non_mapping_payload(self) -> None:
        with self.assertRaises(ValueError):
            _runtime_budget.parse_runtime_budgets([])


class RuntimeBudgetWorkflowEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = _runtime_budget.parse_runtime_budgets(
            {
                "schema_version": 1,
                "severity_model": {
                    "ok": "duration <= warn",
                    "warn": "warn < duration <= fail",
                    "fail": "duration > fail",
                },
                "workflows": {
                    "ci-example": {
                        "stages": {
                            "stage_a": {"warn_seconds": 10, "fail_seconds": 20},
                            "stage_b": {"warn_seconds": 5, "fail_seconds": 15},
                        }
                    }
                },
            }
        )

    def test_evaluate_workflow_budgets_builds_stage_results_and_overall_status(self) -> None:
        evaluation = _runtime_budget.evaluate_workflow_budgets(
            config=self.config,
            workflow_id="ci-example",
            stage_durations_seconds={"stage_a": 10, "stage_b": 16},
        )
        self.assertEqual(evaluation.workflow_id, "ci-example")
        self.assertEqual(evaluation.overall_status, _runtime_budget.STATUS_FAIL)
        self.assertEqual(
            [stage.stage_id for stage in evaluation.stage_results],
            ["stage_a", "stage_b"],
        )
        self.assertEqual(
            [stage.status for stage in evaluation.stage_results],
            [_runtime_budget.STATUS_OK, _runtime_budget.STATUS_FAIL],
        )

    def test_evaluate_workflow_budgets_fails_closed_when_stage_durations_missing(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            _runtime_budget.evaluate_workflow_budgets(
                config=self.config,
                workflow_id="ci-example",
                stage_durations_seconds={"stage_a": 4},
            )
        self.assertIn("missing stage durations", str(ctx.exception))

    def test_evaluate_workflow_budgets_fails_closed_when_unexpected_stage_reported(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            _runtime_budget.evaluate_workflow_budgets(
                config=self.config,
                workflow_id="ci-example",
                stage_durations_seconds={"stage_a": 4, "stage_b": 5, "stage_c": 6},
            )
        self.assertIn("unexpected stages", str(ctx.exception))


class RuntimeBudgetArtifactSchemaTests(unittest.TestCase):
    def test_runtime_budget_artifact_payload_shape(self) -> None:
        config = _runtime_budget.parse_runtime_budgets(
            {
                "schema_version": 1,
                "severity_model": {
                    "ok": "duration <= warn",
                    "warn": "warn < duration <= fail",
                    "fail": "duration > fail",
                },
                "workflows": {
                    "ci-example": {
                        "stages": {
                            "stage_a": {"warn_seconds": 10, "fail_seconds": 20},
                        }
                    }
                },
            }
        )
        evaluation = _runtime_budget.evaluate_workflow_budgets(
            config=config,
            workflow_id="ci-example",
            stage_durations_seconds={"stage_a": 12},
        )
        artifact = _runtime_budget.build_artifact_payload(
            evaluation=evaluation,
            config=config,
            budget_config_path="schema/runtime-budgets.json",
        )
        self.assertEqual(
            set(artifact),
            {
                "schema_version",
                "budget_config_path",
                "workflow_id",
                "overall_status",
                "severity_model",
                "summary",
                "stages",
            },
        )
        self.assertEqual(artifact["schema_version"], 1)
        self.assertEqual(artifact["budget_config_path"], "schema/runtime-budgets.json")
        self.assertEqual(artifact["workflow_id"], "ci-example")
        self.assertEqual(artifact["overall_status"], _runtime_budget.STATUS_WARN)
        self.assertEqual(artifact["summary"]["stage_count"], 1)
        self.assertEqual(artifact["summary"]["warn_count"], 1)
        self.assertEqual(artifact["summary"]["fail_count"], 0)
        self.assertEqual(artifact["summary"]["ok_count"], 0)
        self.assertEqual(artifact["summary"]["max_duration_seconds"], 12)
        self.assertEqual(len(artifact["stages"]), 1)
        stage = artifact["stages"][0]
        self.assertEqual(
            set(stage),
            {
                "stage_id",
                "duration_seconds",
                "warn_seconds",
                "fail_seconds",
                "status",
                "warn_overage_seconds",
                "fail_overage_seconds",
            },
        )
        self.assertEqual(stage["stage_id"], "stage_a")
        self.assertEqual(stage["duration_seconds"], 12)
        self.assertEqual(stage["warn_seconds"], 10)
        self.assertEqual(stage["fail_seconds"], 20)
        self.assertEqual(stage["status"], _runtime_budget.STATUS_WARN)
        self.assertEqual(stage["warn_overage_seconds"], 2)
        self.assertEqual(stage["fail_overage_seconds"], 0)

    def test_runtime_budget_artifact_summary_math_for_mixed_statuses(self) -> None:
        config = _runtime_budget.parse_runtime_budgets(
            {
                "schema_version": 1,
                "severity_model": {
                    "ok": "duration <= warn",
                    "warn": "warn < duration <= fail",
                    "fail": "duration > fail",
                },
                "workflows": {
                    "ci-example": {
                        "stages": {
                            "stage_ok": {"warn_seconds": 10, "fail_seconds": 20},
                            "stage_warn": {"warn_seconds": 10, "fail_seconds": 20},
                            "stage_fail": {"warn_seconds": 10, "fail_seconds": 20},
                        }
                    }
                },
            }
        )
        evaluation = _runtime_budget.evaluate_workflow_budgets(
            config=config,
            workflow_id="ci-example",
            stage_durations_seconds={
                "stage_ok": 10,
                "stage_warn": 15,
                "stage_fail": 25,
            },
        )
        artifact = _runtime_budget.build_artifact_payload(
            evaluation=evaluation,
            config=config,
            budget_config_path="schema/runtime-budgets.json",
        )
        self.assertEqual(artifact["overall_status"], _runtime_budget.STATUS_FAIL)
        self.assertEqual(artifact["summary"]["stage_count"], 3)
        self.assertEqual(artifact["summary"]["ok_count"], 1)
        self.assertEqual(artifact["summary"]["warn_count"], 1)
        self.assertEqual(artifact["summary"]["fail_count"], 1)
        self.assertEqual(artifact["summary"]["max_duration_seconds"], 25)
        stage_by_id = {stage["stage_id"]: stage for stage in artifact["stages"]}
        self.assertEqual(stage_by_id["stage_ok"]["warn_overage_seconds"], 0)
        self.assertEqual(stage_by_id["stage_ok"]["fail_overage_seconds"], 0)
        self.assertEqual(stage_by_id["stage_warn"]["warn_overage_seconds"], 5)
        self.assertEqual(stage_by_id["stage_warn"]["fail_overage_seconds"], 0)
        self.assertEqual(stage_by_id["stage_fail"]["warn_overage_seconds"], 15)
        self.assertEqual(stage_by_id["stage_fail"]["fail_overage_seconds"], 5)

    def test_summary_markdown_includes_status_and_remediation_for_failures(self) -> None:
        config = _runtime_budget.load_runtime_budgets(REPO_ROOT / "schema" / "runtime-budgets.json")
        workflow_id = "ci-5-check-drift"
        evaluation = _runtime_budget.evaluate_workflow_budgets(
            config=config,
            workflow_id=workflow_id,
            stage_durations_seconds={"check_drift": 999_999},
        )
        artifact = _runtime_budget.build_artifact_payload(
            evaluation=evaluation,
            config=config,
            budget_config_path="schema/runtime-budgets.json",
        )
        markdown = _runtime_budget.build_summary_markdown(artifact)
        self.assertIn("Runtime budget report", markdown)
        self.assertIn("Overall status: **FAIL**", markdown)
        self.assertIn("fail-closed threshold breached", markdown)
        self.assertIn("`check_drift`", markdown)

    def test_runtime_budget_schema_file_is_valid_json_and_parseable(self) -> None:
        payload = json.loads((REPO_ROOT / "schema" / "runtime-budgets.json").read_text(encoding="utf-8"))
        config = _runtime_budget.parse_runtime_budgets(payload)
        self.assertGreaterEqual(config.schema_version, 1)
        self.assertGreater(len(config.workflows), 0)


if __name__ == "__main__":
    unittest.main()
