"""Tests for deterministic runtime budget evaluation helpers."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.validation import _runtime_budget


REPO_ROOT = Path(__file__).resolve().parents[2]


class RuntimeBudgetClassificationTests(unittest.TestCase):
    def test_classify_stage_result_respects_target_and_fail_thresholds(self) -> None:
        self.assertEqual(
            _runtime_budget.classify_stage_result(duration_seconds=10, target_seconds=10, fail_seconds=20),
            _runtime_budget.STATUS_OK,
        )
        self.assertEqual(
            _runtime_budget.classify_stage_result(duration_seconds=11, target_seconds=10, fail_seconds=20),
            _runtime_budget.STATUS_WARN,
        )
        self.assertEqual(
            _runtime_budget.classify_stage_result(duration_seconds=19, target_seconds=10, fail_seconds=20),
            _runtime_budget.STATUS_WARN,
        )
        self.assertEqual(
            _runtime_budget.classify_stage_result(duration_seconds=20, target_seconds=10, fail_seconds=20),
            _runtime_budget.STATUS_FAIL,
        )
        self.assertEqual(
            _runtime_budget.classify_stage_result(duration_seconds=21, target_seconds=10, fail_seconds=20),
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
            _runtime_budget.classify_stage_result(duration_seconds=0, target_seconds=10, fail_seconds=20),
            _runtime_budget.STATUS_OK,
        )
        with self.assertRaises(ValueError):
            _runtime_budget.classify_stage_result(duration_seconds=10, target_seconds=20, fail_seconds=20)
        with self.assertRaises(ValueError):
            _runtime_budget.classify_stage_result(duration_seconds=-1, target_seconds=10, fail_seconds=20)
        with self.assertRaises(ValueError):
            _runtime_budget.classify_stage_result(duration_seconds=True, target_seconds=10, fail_seconds=20)
        with self.assertRaises(ValueError):
            _runtime_budget.classify_stage_result(duration_seconds=1, target_seconds=10, fail_seconds=False)

    def test_parse_runtime_budgets_rejects_non_mapping_payload(self) -> None:
        with self.assertRaises(ValueError):
            _runtime_budget.parse_runtime_budgets([])


class RuntimeBudgetWorkflowEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = _runtime_budget.parse_runtime_budgets(
            {
                "schema_version": 2,
                "severity_model": {
                    "ok": "duration <= target",
                    "warn": "target < duration < fail",
                    "fail": "duration >= fail",
                },
                "workflows": {
                    "ci-example": {
                        "stages": {
                            "stage_a": {"target_seconds": 10, "warn_pct": 25, "fail_pct": 100},
                            "stage_b": {"target_seconds": 5, "warn_pct": 20, "fail_pct": 200},
                        }
                    }
                },
            }
        )

    def test_evaluate_workflow_budgets_builds_stage_results_and_overall_status(self) -> None:
        evaluation = _runtime_budget.evaluate_workflow_budgets(
            config=self.config,
            workflow_id="ci-example",
            stage_durations_seconds={"stage_a": 10, "stage_b": 15},
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
        stage_b = next(stage for stage in evaluation.stage_results if stage.stage_id == "stage_b")
        self.assertEqual(stage_b.fail_seconds, 15)

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

    def test_fail_threshold_uses_ceiling_rounding_boundary(self) -> None:
        config = _runtime_budget.parse_runtime_budgets(
            {
                "schema_version": 2,
                "severity_model": {
                    "ok": "duration <= target",
                    "warn": "target < duration < fail",
                    "fail": "duration >= fail",
                },
                "workflows": {
                    "ci-example": {
                        "stages": {
                            "stage_a": {"target_seconds": 3, "warn_pct": 10, "fail_pct": 34},
                        }
                    }
                },
            }
        )
        warn_evaluation = _runtime_budget.evaluate_workflow_budgets(
            config=config,
            workflow_id="ci-example",
            stage_durations_seconds={"stage_a": 4},
        )
        fail_evaluation = _runtime_budget.evaluate_workflow_budgets(
            config=config,
            workflow_id="ci-example",
            stage_durations_seconds={"stage_a": 5},
        )
        self.assertEqual(warn_evaluation.stage_results[0].fail_seconds, 5)
        self.assertEqual(warn_evaluation.stage_results[0].status, _runtime_budget.STATUS_WARN)
        self.assertEqual(fail_evaluation.stage_results[0].status, _runtime_budget.STATUS_FAIL)

    def test_warn_pct_is_metadata_and_does_not_change_status_boundaries(self) -> None:
        config = _runtime_budget.parse_runtime_budgets(
            {
                "schema_version": 2,
                "severity_model": {
                    "ok": "duration <= target",
                    "warn": "target < duration < fail",
                    "fail": "duration >= fail",
                },
                "workflows": {
                    "ci-example": {
                        "stages": {
                            "stage_low_warn_pct": {"target_seconds": 10, "warn_pct": 0, "fail_pct": 100},
                            "stage_high_warn_pct": {"target_seconds": 10, "warn_pct": 90, "fail_pct": 100},
                        }
                    }
                },
            }
        )
        for duration, expected_status in (
            (10, _runtime_budget.STATUS_OK),
            (11, _runtime_budget.STATUS_WARN),
            (20, _runtime_budget.STATUS_FAIL),
        ):
            with self.subTest(duration=duration, expected_status=expected_status):
                evaluation = _runtime_budget.evaluate_workflow_budgets(
                    config=config,
                    workflow_id="ci-example",
                    stage_durations_seconds={"stage_low_warn_pct": duration, "stage_high_warn_pct": duration},
                )
                self.assertEqual(
                    [stage.status for stage in evaluation.stage_results],
                    [expected_status, expected_status],
                )


class RuntimeBudgetArtifactSchemaTests(unittest.TestCase):
    def test_runtime_budget_artifact_payload_shape(self) -> None:
        config = _runtime_budget.parse_runtime_budgets(
            {
                "schema_version": 2,
                "severity_model": {
                    "ok": "duration <= target",
                    "warn": "target < duration < fail",
                    "fail": "duration >= fail",
                },
                "workflows": {
                    "ci-example": {
                        "stages": {
                            "stage_a": {"target_seconds": 10, "warn_pct": 25, "fail_pct": 100},
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
        self.assertEqual(artifact["schema_version"], 2)
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
                "target_seconds",
                "warn_pct",
                "fail_pct",
                "fail_seconds",
                "status",
                "target_overage_seconds",
                "target_overage_pct",
                "fail_overage_seconds",
            },
        )
        self.assertEqual(stage["stage_id"], "stage_a")
        self.assertEqual(stage["duration_seconds"], 12)
        self.assertEqual(stage["target_seconds"], 10)
        self.assertEqual(stage["warn_pct"], 25)
        self.assertEqual(stage["fail_pct"], 100)
        self.assertEqual(stage["fail_seconds"], 20)
        self.assertEqual(stage["status"], _runtime_budget.STATUS_WARN)
        self.assertEqual(stage["target_overage_seconds"], 2)
        self.assertEqual(stage["target_overage_pct"], 20.0)
        self.assertEqual(stage["fail_overage_seconds"], 0)

    def test_runtime_budget_artifact_summary_math_for_mixed_statuses(self) -> None:
        config = _runtime_budget.parse_runtime_budgets(
            {
                "schema_version": 2,
                "severity_model": {
                    "ok": "duration <= target",
                    "warn": "target < duration < fail",
                    "fail": "duration >= fail",
                },
                "workflows": {
                    "ci-example": {
                        "stages": {
                            "stage_ok": {"target_seconds": 10, "warn_pct": 25, "fail_pct": 100},
                            "stage_warn": {"target_seconds": 10, "warn_pct": 25, "fail_pct": 100},
                            "stage_fail": {"target_seconds": 10, "warn_pct": 25, "fail_pct": 100},
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
                "stage_fail": 20,
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
        self.assertEqual(artifact["summary"]["max_duration_seconds"], 20)
        stage_by_id = {stage["stage_id"]: stage for stage in artifact["stages"]}
        self.assertEqual(stage_by_id["stage_ok"]["target_overage_seconds"], 0)
        self.assertEqual(stage_by_id["stage_ok"]["fail_overage_seconds"], 0)
        self.assertEqual(stage_by_id["stage_warn"]["target_overage_seconds"], 5)
        self.assertEqual(stage_by_id["stage_warn"]["fail_overage_seconds"], 0)
        self.assertEqual(stage_by_id["stage_fail"]["target_overage_seconds"], 10)
        self.assertEqual(stage_by_id["stage_fail"]["fail_overage_seconds"], 0)

    def test_runtime_budget_artifact_preserves_declared_warn_pct_metadata(self) -> None:
        config = _runtime_budget.parse_runtime_budgets(
            {
                "schema_version": 2,
                "severity_model": {
                    "ok": "duration <= target",
                    "warn": "target < duration < fail",
                    "fail": "duration >= fail",
                },
                "workflows": {
                    "ci-example": {
                        "stages": {
                            "stage_low_warn_pct": {"target_seconds": 10, "warn_pct": 0, "fail_pct": 100},
                            "stage_high_warn_pct": {"target_seconds": 10, "warn_pct": 90, "fail_pct": 100},
                        }
                    }
                },
            }
        )
        evaluation = _runtime_budget.evaluate_workflow_budgets(
            config=config,
            workflow_id="ci-example",
            stage_durations_seconds={"stage_low_warn_pct": 11, "stage_high_warn_pct": 11},
        )
        artifact = _runtime_budget.build_artifact_payload(
            evaluation=evaluation,
            config=config,
            budget_config_path="schema/runtime-budgets.json",
        )
        stage_by_id = {stage["stage_id"]: stage for stage in artifact["stages"]}
        self.assertEqual(stage_by_id["stage_low_warn_pct"]["warn_pct"], 0)
        self.assertEqual(stage_by_id["stage_high_warn_pct"]["warn_pct"], 90)
        self.assertEqual(stage_by_id["stage_low_warn_pct"]["status"], _runtime_budget.STATUS_WARN)
        self.assertEqual(stage_by_id["stage_high_warn_pct"]["status"], _runtime_budget.STATUS_WARN)

    def test_summary_markdown_includes_status_and_remediation_for_failures(self) -> None:
        config = _runtime_budget.load_runtime_budgets(REPO_ROOT / "schema" / "runtime-budgets.json")
        workflow_id = "ci-2-analyst-diagnostics"
        evaluation = _runtime_budget.evaluate_workflow_budgets(
            config=config,
            workflow_id=workflow_id,
            stage_durations_seconds={
                "validate_wiki_governance": 999_999,
                "check_doc_freshness": 1,
                "content_quality_summary": 1,
                "lint_wiki_strict": 1,
                "pytest_suite": 1,
            },
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
        self.assertIn("`validate_wiki_governance`", markdown)
        self.assertIn("| Stage | Duration (s) | Target (s) | Warn (%) |", markdown)

    def test_runtime_budget_schema_file_is_valid_json_and_parseable(self) -> None:
        payload = json.loads((REPO_ROOT / "schema" / "runtime-budgets.json").read_text(encoding="utf-8"))
        config = _runtime_budget.parse_runtime_budgets(payload)
        self.assertGreaterEqual(config.schema_version, 1)
        self.assertGreater(len(config.workflows), 0)

    def test_runtime_budget_schema_stage_entries_require_target_warn_fail_fields(self) -> None:
        payload = json.loads((REPO_ROOT / "schema" / "runtime-budgets.json").read_text(encoding="utf-8"))
        for workflow_id, workflow_entry in payload["workflows"].items():
            for stage_id, stage_entry in workflow_entry["stages"].items():
                self.assertEqual(
                    set(stage_entry),
                    {"target_seconds", "warn_pct", "fail_pct"},
                    f"{workflow_id}/{stage_id} must only define target_seconds, warn_pct, fail_pct",
                )

    def test_parse_runtime_budgets_rejects_missing_or_invalid_threshold_fields(self) -> None:
        payload_missing = {
            "schema_version": 2,
            "severity_model": {
                "ok": "duration <= target",
                "warn": "target < duration < fail",
                "fail": "duration >= fail",
            },
            "workflows": {
                "ci-example": {
                    "stages": {
                        "stage_a": {"target_seconds": 10, "warn_pct": 25},
                    }
                }
            },
        }
        with self.assertRaises(ValueError):
            _runtime_budget.parse_runtime_budgets(payload_missing)

        payload_invalid = {
            "schema_version": 2,
            "severity_model": {
                "ok": "duration <= target",
                "warn": "target < duration < fail",
                "fail": "duration >= fail",
            },
            "workflows": {
                "ci-example": {
                    "stages": {
                        "stage_a": {"target_seconds": 10, "warn_pct": 25, "fail_pct": 25},
                    }
                }
            },
        }
        with self.assertRaises(ValueError):
            _runtime_budget.parse_runtime_budgets(payload_invalid)

    def test_parse_runtime_budgets_rejects_invalid_threshold_types_and_ranges(self) -> None:
        base_payload = {
            "schema_version": 2,
            "severity_model": {
                "ok": "duration <= target",
                "warn": "target < duration < fail",
                "fail": "duration >= fail",
            },
            "workflows": {
                "ci-example": {
                    "stages": {
                        "stage_a": {"target_seconds": 10, "warn_pct": 25, "fail_pct": 100},
                    }
                }
            },
        }
        invalid_stage_entries = (
            {"target_seconds": 0, "warn_pct": 25, "fail_pct": 100},
            {"target_seconds": 10, "warn_pct": -1, "fail_pct": 100},
            {"target_seconds": 10, "warn_pct": 25, "fail_pct": 0},
            {"target_seconds": 10, "warn_pct": 25, "fail_pct": "100"},
            {"target_seconds": "10", "warn_pct": 25, "fail_pct": 100},
            {"target_seconds": 10, "warn_pct": True, "fail_pct": 100},
        )
        for stage_entry in invalid_stage_entries:
            with self.subTest(stage_entry=stage_entry):
                payload = json.loads(json.dumps(base_payload))
                payload["workflows"]["ci-example"]["stages"]["stage_a"] = stage_entry
                with self.assertRaises(ValueError):
                    _runtime_budget.parse_runtime_budgets(payload)


if __name__ == "__main__":
    unittest.main()
