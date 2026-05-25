"""Evaluate runtime-budget artifacts for CI workflow stages."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

from scripts.validation import _runtime_budget


def evaluate_runtime_budget(
    *,
    metrics_path: Path,
    budget_config_path: Path,
    report_path: Path,
    summary_file_path: Path | None,
    github_output_path: Path | None,
    output_key: str,
) -> dict[str, Any]:
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    if not isinstance(metrics, Mapping):
        raise ValueError("metrics payload must be a mapping")

    workflow_id = metrics.get("workflow_id")
    if not isinstance(workflow_id, str) or not workflow_id.strip():
        raise ValueError("metrics.workflow_id must be a non-empty string")

    stage_durations_raw = metrics.get("stage_durations_seconds")
    if not isinstance(stage_durations_raw, Mapping):
        raise ValueError("metrics.stage_durations_seconds must be a mapping")

    stage_durations_seconds: dict[str, int] = {}
    for stage_id, raw_duration in stage_durations_raw.items():
        stage_name = str(stage_id)
        if not stage_name:
            raise ValueError("stage_durations_seconds keys must be non-empty")
        if isinstance(raw_duration, bool) or isinstance(raw_duration, float):
            raise ValueError(
                "metrics.stage_durations_seconds values must be integer durations (bool/float rejected)"
            )
        stage_durations_seconds[stage_name] = int(raw_duration)

    config = _runtime_budget.load_runtime_budgets(budget_config_path)
    evaluation = _runtime_budget.evaluate_workflow_budgets(
        config=config,
        workflow_id=workflow_id,
        stage_durations_seconds=stage_durations_seconds,
    )
    artifact = _runtime_budget.build_artifact_payload(
        evaluation=evaluation,
        config=config,
        budget_config_path=str(budget_config_path),
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if summary_file_path is not None:
        summary_file_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_file_path.open("a", encoding="utf-8") as summary_handle:
            summary_handle.write(_runtime_budget.build_summary_markdown(artifact) + "\n")

    if github_output_path is not None:
        github_output_path.parent.mkdir(parents=True, exist_ok=True)
        with github_output_path.open("a", encoding="utf-8") as output_handle:
            output_handle.write(f"{output_key}={artifact['overall_status']}\n")

    return artifact


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metrics",
        required=True,
        help="Path to runtime metrics JSON containing workflow_id and stage_durations_seconds.",
    )
    parser.add_argument(
        "--report",
        required=True,
        help="Path where the runtime-budget report JSON should be written.",
    )
    parser.add_argument(
        "--budget-config",
        default="schema/runtime-budgets.json",
        help="Runtime budget contract JSON path.",
    )
    parser.add_argument(
        "--summary-file",
        default=os.environ.get("GITHUB_STEP_SUMMARY", "").strip() or None,
        help="Optional summary markdown output path (defaults to GITHUB_STEP_SUMMARY when set).",
    )
    parser.add_argument(
        "--github-output-file",
        default=os.environ.get("GITHUB_OUTPUT", "").strip() or None,
        help="Optional GitHub output file path (defaults to GITHUB_OUTPUT when set).",
    )
    parser.add_argument(
        "--output-key",
        default="overall_status",
        help="Output key written to the GitHub output file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    evaluate_runtime_budget(
        metrics_path=Path(args.metrics),
        budget_config_path=Path(args.budget_config),
        report_path=Path(args.report),
        summary_file_path=Path(args.summary_file) if args.summary_file else None,
        github_output_path=Path(args.github_output_file) if args.github_output_file else None,
        output_key=str(args.output_key),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
