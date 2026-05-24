"""Tests for scripts/validation/evaluate_runtime_budget.py."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validation import evaluate_runtime_budget


def _write_runtime_budget_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "severity_model": {"ok": "notice", "warn": "warning", "fail": "error"},
                "workflows": {
                    "ci-test": {
                        "stages": {
                            "stage_a": {
                                "target_seconds": 10,
                                "warn_pct": 25,
                                "fail_pct": 100,
                            }
                        }
                    }
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_metrics(path: Path, duration_seconds: int) -> None:
    path.write_text(
        json.dumps(
            {
                "workflow_id": "ci-test",
                "stage_durations_seconds": {"stage_a": duration_seconds},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_main_writes_report_summary_and_output(tmp_path: Path) -> None:
    config_path = tmp_path / "runtime-budgets.json"
    metrics_path = tmp_path / "runtime-metrics.json"
    report_path = tmp_path / "runtime-budget-report.json"
    summary_path = tmp_path / "summary.md"
    output_path = tmp_path / "github-output.txt"
    _write_runtime_budget_config(config_path)
    _write_metrics(metrics_path, duration_seconds=12)

    exit_code = evaluate_runtime_budget.main(
        [
            "--metrics",
            str(metrics_path),
            "--report",
            str(report_path),
            "--budget-config",
            str(config_path),
            "--summary-file",
            str(summary_path),
            "--github-output-file",
            str(output_path),
        ]
    )

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["workflow_id"] == "ci-test"
    assert report["overall_status"] == "warn"
    assert "overall_status=warn" in output_path.read_text(encoding="utf-8")
    assert "ci-test" in summary_path.read_text(encoding="utf-8")


def test_main_uses_default_env_output_paths(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "runtime-budgets.json"
    metrics_path = tmp_path / "runtime-metrics.json"
    report_path = tmp_path / "runtime-budget-report.json"
    summary_path = tmp_path / "summary.md"
    output_path = tmp_path / "github-output.txt"
    _write_runtime_budget_config(config_path)
    _write_metrics(metrics_path, duration_seconds=9)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))

    exit_code = evaluate_runtime_budget.main(
        [
            "--metrics",
            str(metrics_path),
            "--report",
            str(report_path),
            "--budget-config",
            str(config_path),
        ]
    )

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["overall_status"] == "ok"
    assert "overall_status=ok" in output_path.read_text(encoding="utf-8")
    assert "ci-test" in summary_path.read_text(encoding="utf-8")
