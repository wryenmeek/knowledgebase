"""Structural contract checks for sweep-stale-bot-branches.yml.

Covers:
- Trigger contract: cron schedule present and workflow_dispatch declared.
- Permissions: contents: read ONLY (no write).
- workflow_dispatch input dry_run must be type: boolean, default: true.
- dry_run=false path must be gated by environment: sweep-real-delete-approval.
- Concurrency group declared.
- No direct ${{ inputs.* }} interpolation in run: blocks (shell injection guard).

Uses pytest (ADR-029 — NOT unittest.TestCase).
Mirrors test_fleet_merge_workflow.py::FleetDispatchInjectionGuard pattern.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


WORKFLOW_PATH = Path(".github/workflows/sweep-stale-bot-branches.yml")

_INLINE_INPUTS_RE = re.compile(r"\$\{\{[-\s]*inputs\.", re.IGNORECASE)


def _collect_run_blocks(workflow: dict) -> list[str]:
    """Return all run: string values from every step in every job."""
    runs: list[str] = []
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            run_val = step.get("run")
            if run_val:
                runs.append(str(run_val))
    return runs


@pytest.fixture(scope="module")
def workflow() -> dict:
    assert WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}"
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def workflow_text() -> str:
    assert WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}"
    return WORKFLOW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def on_block(workflow: dict) -> dict:
    # YAML parses 'on' as the boolean True in some versions
    return workflow.get(True, workflow.get("on", {}))


# ---------------------------------------------------------------------------
# Trigger contract
# ---------------------------------------------------------------------------


def test_has_schedule_trigger(on_block: dict) -> None:
    """Workflow must have a schedule trigger for nightly sweeps."""
    assert "schedule" in on_block, "sweep-stale-bot-branches.yml must have a schedule trigger"


def test_has_workflow_dispatch_trigger(on_block: dict) -> None:
    """Workflow must have a workflow_dispatch trigger for manual invocation."""
    assert "workflow_dispatch" in on_block, (
        "sweep-stale-bot-branches.yml must have a workflow_dispatch trigger"
    )


def test_cron_is_0_2_every_day(on_block: dict) -> None:
    """Cron schedule must be '0 2 * * *' (02:00 UTC daily)."""
    schedule = on_block.get("schedule", [])
    cron_values = [item.get("cron") for item in schedule if isinstance(item, dict)]
    assert "0 2 * * *" in cron_values, (
        f"Expected cron '0 2 * * *' in schedule; got: {cron_values}"
    )


# ---------------------------------------------------------------------------
# Permissions contract
# ---------------------------------------------------------------------------


def test_permissions_contents_read_only(workflow: dict) -> None:
    """permissions must declare contents: read — NO write permission."""
    permissions = workflow.get("permissions", {})
    assert permissions.get("contents") == "read", (
        "sweep-stale-bot-branches.yml permissions.contents must be 'read' (dry-run phase)"
    )
    # Ensure no write-capable permissions are present at workflow level
    write_perms = [k for k, v in permissions.items() if v == "write"]
    assert write_perms == [], (
        f"Workflow-level write permissions found: {write_perms}. "
        "Only 'read' is permitted during the observation window."
    )


# ---------------------------------------------------------------------------
# workflow_dispatch input contract
# ---------------------------------------------------------------------------


def test_dry_run_input_is_boolean_type(on_block: dict) -> None:
    """workflow_dispatch must declare dry_run as type: boolean."""
    wd = on_block.get("workflow_dispatch", {})
    inputs = wd.get("inputs", {}) or {}
    assert "dry_run" in inputs, (
        "workflow_dispatch must declare a 'dry_run' input"
    )
    dry_run_input = inputs["dry_run"]
    assert dry_run_input.get("type") == "boolean", (
        f"dry_run input must be type: boolean; got: {dry_run_input.get('type')!r}"
    )


def test_dry_run_input_defaults_to_true(on_block: dict) -> None:
    """workflow_dispatch dry_run input must default to true."""
    wd = on_block.get("workflow_dispatch", {})
    inputs = wd.get("inputs", {}) or {}
    dry_run_input = inputs.get("dry_run", {})
    assert dry_run_input.get("default") is True, (
        f"dry_run input must default to true; got: {dry_run_input.get('default')!r}"
    )


# ---------------------------------------------------------------------------
# Environment approval gate (dry_run=false bypass guard)
# ---------------------------------------------------------------------------


def test_sweep_job_environment_gates_on_dry_run_false(workflow: dict) -> None:
    """The sweep job must gate dry_run=false on sweep-real-delete-approval environment.

    This is the mechanism that prevents any operator from bypassing dry-run
    until issue #351 creates the sweep-real-delete-approval environment.
    """
    jobs = workflow.get("jobs", {})
    sweep_job = jobs.get("sweep", {})
    environment = sweep_job.get("environment", "")
    # The environment expression may be a string or a YAML scalar.
    env_str = str(environment)
    assert "sweep-real-delete-approval" in env_str, (
        "sweep job must reference 'sweep-real-delete-approval' environment to gate dry_run=false; "
        f"found: {env_str!r}"
    )


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def test_concurrency_group_declared(workflow: dict) -> None:
    """A concurrency group must be declared to prevent parallel sweep runs."""
    concurrency = workflow.get("concurrency", {})
    if not concurrency:
        # Try at job level
        jobs = workflow.get("jobs", {})
        sweep_job = jobs.get("sweep", {})
        concurrency = sweep_job.get("concurrency", {})
    assert concurrency, "A concurrency group must be declared (workflow or job level)"


def test_concurrency_cancel_in_progress_is_false(workflow: dict) -> None:
    """cancel-in-progress must be False — cancelling an in-flight sweep is unsafe."""
    concurrency = workflow.get("concurrency", {})
    if not concurrency:
        jobs = workflow.get("jobs", {})
        sweep_job = jobs.get("sweep", {})
        concurrency = sweep_job.get("concurrency", {})
    assert concurrency.get("cancel-in-progress") is False, (
        "cancel-in-progress must be False to prevent mid-sweep cancellation"
    )


# ---------------------------------------------------------------------------
# Shell injection guards
# ---------------------------------------------------------------------------


def test_no_direct_inputs_interpolation_in_run_blocks(workflow: dict) -> None:
    """${{ inputs.* }} must never appear directly inside a run: block.

    Direct interpolation enables shell injection via a crafted input value.
    The safe pattern is an env: block + shell variable expansion.
    Both the spaced form (${{ inputs.* }}) and the no-space form (${{inputs.*}})
    are checked.
    """
    for block in _collect_run_blocks(workflow):
        assert not _INLINE_INPUTS_RE.search(block), (
            f"inputs.* must not be interpolated directly in a run: block.\n"
            f"Found in block:\n{block}\n"
            "Use an env: block and reference the env var instead."
        )


def test_env_block_routes_dry_run_input(workflow_text: str) -> None:
    """The sweep step must route the dry_run input through an env: block."""
    # The INPUT_DRY_RUN env var must appear in the workflow to confirm
    # the safe env-routing pattern is established.
    assert "INPUT_DRY_RUN" in workflow_text, (
        "Workflow must route inputs.dry_run through an INPUT_DRY_RUN env var "
        "to prevent shell injection (see AGENTS.md argv-discipline rule)"
    )


# ---------------------------------------------------------------------------
# Step summary output (dry-run report)
# ---------------------------------------------------------------------------


def test_sweep_step_exists_in_job(workflow: dict) -> None:
    """The sweep job must have a step that invokes the Python script."""
    jobs = workflow.get("jobs", {})
    sweep_job = jobs.get("sweep", {})
    steps = sweep_job.get("steps", [])
    run_blocks = [str(s.get("run", "")) for s in steps if s.get("run")]
    combined = "\n".join(run_blocks)
    assert "sweep_stale_bot_branches" in combined, (
        "sweep job must invoke scripts/maintenance/sweep_stale_bot_branches.py"
    )
