"""Deterministic runtime budget evaluation helpers for CI workflows."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"
_STATUS_ORDER = (STATUS_OK, STATUS_WARN, STATUS_FAIL)
_STATUS_RANK = {status: index for index, status in enumerate(_STATUS_ORDER)}


@dataclass(frozen=True, slots=True)
class StageBudget:
    warn_seconds: int
    fail_seconds: int


@dataclass(frozen=True, slots=True)
class StageEvaluation:
    stage_id: str
    duration_seconds: int
    warn_seconds: int
    fail_seconds: int
    status: str


@dataclass(frozen=True, slots=True)
class WorkflowEvaluation:
    workflow_id: str
    overall_status: str
    stage_results: tuple[StageEvaluation, ...]


@dataclass(frozen=True, slots=True)
class RuntimeBudgetConfig:
    schema_version: int
    severity_model: dict[str, str]
    workflows: dict[str, dict[str, StageBudget]]


def load_runtime_budgets(path: str | Path) -> RuntimeBudgetConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return parse_runtime_budgets(payload)


def parse_runtime_budgets(payload: Mapping[str, Any]) -> RuntimeBudgetConfig:
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a mapping")
    schema_version = _parse_positive_int(payload.get("schema_version"), field="schema_version", allow_zero=False)
    severity_model_raw = payload.get("severity_model")
    if not isinstance(severity_model_raw, Mapping):
        raise ValueError("severity_model must be a mapping")
    severity_model = {
        status: _parse_non_empty_string(severity_model_raw.get(status), field=f"severity_model.{status}")
        for status in _STATUS_ORDER
    }

    workflows_raw = payload.get("workflows")
    if not isinstance(workflows_raw, Mapping) or not workflows_raw:
        raise ValueError("workflows must be a non-empty mapping")

    workflows: dict[str, dict[str, StageBudget]] = {}
    for workflow_id in sorted(workflows_raw):
        normalized_workflow_id = _parse_non_empty_string(workflow_id, field="workflow_id")
        workflow_entry = workflows_raw[workflow_id]
        if not isinstance(workflow_entry, Mapping):
            raise ValueError(f"workflow '{normalized_workflow_id}' must be a mapping")
        stages_raw = workflow_entry.get("stages")
        if not isinstance(stages_raw, Mapping) or not stages_raw:
            raise ValueError(f"workflow '{normalized_workflow_id}' must declare a non-empty stages mapping")
        stage_budgets: dict[str, StageBudget] = {}
        for stage_id in sorted(stages_raw):
            normalized_stage_id = _parse_non_empty_string(stage_id, field=f"workflows.{normalized_workflow_id}.stage_id")
            stage_entry = stages_raw[stage_id]
            if not isinstance(stage_entry, Mapping):
                raise ValueError(f"stage '{normalized_stage_id}' in workflow '{normalized_workflow_id}' must be a mapping")
            warn_seconds = _parse_positive_int(
                stage_entry.get("warn_seconds"),
                field=f"workflows.{normalized_workflow_id}.stages.{normalized_stage_id}.warn_seconds",
                allow_zero=False,
            )
            fail_seconds = _parse_positive_int(
                stage_entry.get("fail_seconds"),
                field=f"workflows.{normalized_workflow_id}.stages.{normalized_stage_id}.fail_seconds",
                allow_zero=False,
            )
            if warn_seconds >= fail_seconds:
                raise ValueError(
                    f"stage '{normalized_stage_id}' in workflow '{normalized_workflow_id}' must satisfy warn_seconds < fail_seconds"
                )
            stage_budgets[normalized_stage_id] = StageBudget(warn_seconds=warn_seconds, fail_seconds=fail_seconds)
        workflows[normalized_workflow_id] = stage_budgets

    return RuntimeBudgetConfig(
        schema_version=schema_version,
        severity_model=severity_model,
        workflows=workflows,
    )


def classify_stage_result(*, duration_seconds: int, warn_seconds: int, fail_seconds: int) -> str:
    normalized_duration = _parse_positive_int(duration_seconds, field="duration_seconds", allow_zero=True)
    normalized_warn = _parse_positive_int(warn_seconds, field="warn_seconds", allow_zero=False)
    normalized_fail = _parse_positive_int(fail_seconds, field="fail_seconds", allow_zero=False)
    if normalized_warn >= normalized_fail:
        raise ValueError("warn_seconds must be less than fail_seconds")
    if normalized_duration > normalized_fail:
        return STATUS_FAIL
    if normalized_duration > normalized_warn:
        return STATUS_WARN
    return STATUS_OK


def aggregate_overall_status(statuses: Sequence[str]) -> str:
    if not statuses:
        raise ValueError("statuses must be non-empty")
    unknown_statuses = sorted({status for status in statuses if status not in _STATUS_RANK})
    if unknown_statuses:
        raise ValueError(f"unsupported status values: {', '.join(unknown_statuses)}")
    return max(statuses, key=lambda status: _STATUS_RANK[status])


def evaluate_workflow_budgets(
    *,
    config: RuntimeBudgetConfig,
    workflow_id: str,
    stage_durations_seconds: Mapping[str, int],
) -> WorkflowEvaluation:
    normalized_workflow_id = _parse_non_empty_string(workflow_id, field="workflow_id")
    if normalized_workflow_id not in config.workflows:
        raise ValueError(f"workflow '{normalized_workflow_id}' is not declared in runtime budget config")

    workflow_stage_budgets = config.workflows[normalized_workflow_id]
    expected_stage_ids = set(workflow_stage_budgets)
    observed_stage_ids = set(stage_durations_seconds)
    missing_stage_ids = sorted(expected_stage_ids - observed_stage_ids)
    unexpected_stage_ids = sorted(observed_stage_ids - expected_stage_ids)
    if missing_stage_ids:
        raise ValueError(
            f"workflow '{normalized_workflow_id}' is missing stage durations for: {', '.join(missing_stage_ids)}"
        )
    if unexpected_stage_ids:
        raise ValueError(
            f"workflow '{normalized_workflow_id}' reported unexpected stages: {', '.join(unexpected_stage_ids)}"
        )

    stage_results: list[StageEvaluation] = []
    for stage_id in sorted(workflow_stage_budgets):
        budget = workflow_stage_budgets[stage_id]
        duration_seconds = _parse_positive_int(
            stage_durations_seconds[stage_id],
            field=f"stage_durations_seconds.{stage_id}",
            allow_zero=True,
        )
        status = classify_stage_result(
            duration_seconds=duration_seconds,
            warn_seconds=budget.warn_seconds,
            fail_seconds=budget.fail_seconds,
        )
        stage_results.append(
            StageEvaluation(
                stage_id=stage_id,
                duration_seconds=duration_seconds,
                warn_seconds=budget.warn_seconds,
                fail_seconds=budget.fail_seconds,
                status=status,
            )
        )

    overall_status = aggregate_overall_status([result.status for result in stage_results])
    return WorkflowEvaluation(
        workflow_id=normalized_workflow_id,
        overall_status=overall_status,
        stage_results=tuple(stage_results),
    )


def build_artifact_payload(
    *,
    evaluation: WorkflowEvaluation,
    config: RuntimeBudgetConfig,
    budget_config_path: str,
) -> dict[str, object]:
    ok_count = sum(1 for stage in evaluation.stage_results if stage.status == STATUS_OK)
    warn_count = sum(1 for stage in evaluation.stage_results if stage.status == STATUS_WARN)
    fail_count = sum(1 for stage in evaluation.stage_results if stage.status == STATUS_FAIL)
    max_duration_seconds = max((stage.duration_seconds for stage in evaluation.stage_results), default=0)

    stages = [
        {
            "stage_id": stage.stage_id,
            "duration_seconds": stage.duration_seconds,
            "warn_seconds": stage.warn_seconds,
            "fail_seconds": stage.fail_seconds,
            "status": stage.status,
            "warn_overage_seconds": max(0, stage.duration_seconds - stage.warn_seconds),
            "fail_overage_seconds": max(0, stage.duration_seconds - stage.fail_seconds),
        }
        for stage in evaluation.stage_results
    ]
    return {
        "schema_version": config.schema_version,
        "budget_config_path": budget_config_path,
        "workflow_id": evaluation.workflow_id,
        "overall_status": evaluation.overall_status,
        "severity_model": dict(config.severity_model),
        "summary": {
            "stage_count": len(evaluation.stage_results),
            "ok_count": ok_count,
            "warn_count": warn_count,
            "fail_count": fail_count,
            "max_duration_seconds": max_duration_seconds,
        },
        "stages": stages,
    }


def build_summary_markdown(artifact_payload: Mapping[str, object]) -> str:
    workflow_id = _parse_non_empty_string(artifact_payload.get("workflow_id"), field="artifact_payload.workflow_id")
    overall_status = _parse_non_empty_string(
        artifact_payload.get("overall_status"),
        field="artifact_payload.overall_status",
    )
    budget_config_path = _parse_non_empty_string(
        artifact_payload.get("budget_config_path"),
        field="artifact_payload.budget_config_path",
    )
    if overall_status not in _STATUS_RANK:
        raise ValueError(f"unsupported overall_status: {overall_status}")

    stages_raw = artifact_payload.get("stages")
    if not isinstance(stages_raw, Sequence):
        raise ValueError("artifact_payload.stages must be a sequence")

    status_marker = {
        STATUS_OK: "✅",
        STATUS_WARN: "⚠️",
        STATUS_FAIL: "❌",
    }[overall_status]
    lines = [
        f"### Runtime budget report — `{workflow_id}`",
        "",
        f"- Overall status: **{overall_status.upper()}** {status_marker}",
        f"- Budget config: `{budget_config_path}`",
        "",
        "| Stage | Duration (s) | Warn (s) | Fail (s) | Status |",
        "|---|---:|---:|---:|---|",
    ]
    for stage_raw in stages_raw:
        if not isinstance(stage_raw, Mapping):
            raise ValueError("artifact_payload.stages entries must be mappings")
        stage_id = _parse_non_empty_string(stage_raw.get("stage_id"), field="stage.stage_id")
        duration_seconds = _parse_positive_int(stage_raw.get("duration_seconds"), field=f"stage.{stage_id}.duration_seconds", allow_zero=True)
        warn_seconds = _parse_positive_int(stage_raw.get("warn_seconds"), field=f"stage.{stage_id}.warn_seconds", allow_zero=False)
        fail_seconds = _parse_positive_int(stage_raw.get("fail_seconds"), field=f"stage.{stage_id}.fail_seconds", allow_zero=False)
        stage_status = _parse_non_empty_string(stage_raw.get("status"), field=f"stage.{stage_id}.status")
        if stage_status not in _STATUS_RANK:
            raise ValueError(f"unsupported stage status for '{stage_id}': {stage_status}")
        lines.append(
            f"| `{stage_id}` | {duration_seconds} | {warn_seconds} | {fail_seconds} | **{stage_status.upper()}** |"
        )

    if overall_status == STATUS_WARN:
        lines.append("")
        lines.append("_Remediation: investigate WARN stages and reduce runtime before they cross fail thresholds._")
    elif overall_status == STATUS_FAIL:
        lines.append("")
        lines.append("_Remediation: fail-closed threshold breached. Triage the listed FAIL stage(s) before rerunning._")

    return "\n".join(lines)


def _parse_non_empty_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must be a non-empty string")
    return normalized


def _parse_positive_int(value: Any, *, field: str, allow_zero: bool) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if allow_zero and value < 0:
        raise ValueError(f"{field} must be greater than or equal to zero")
    if not allow_zero and value <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return value


__all__ = [
    "STATUS_OK",
    "STATUS_WARN",
    "STATUS_FAIL",
    "StageBudget",
    "StageEvaluation",
    "WorkflowEvaluation",
    "RuntimeBudgetConfig",
    "load_runtime_budgets",
    "parse_runtime_budgets",
    "classify_stage_result",
    "aggregate_overall_status",
    "evaluate_workflow_budgets",
    "build_artifact_payload",
    "build_summary_markdown",
]
