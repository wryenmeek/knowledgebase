"""Per-workflow contract tests for `.github/workflows/jules-account-probe.yml`.

This file pins the invariants that the cross-functional review (2026-06-21)
required before the schedule + tracking-issue notification path was considered
safe to merge (Issue #349):

1. Both `workflow_dispatch` AND `schedule` triggers are present.
2. Schedule cron is exactly `0 0,9,18 * * *` (3 slots/day: 00:00/09:00/18:00 UTC).
3. Workflow-level `permissions:` contains only `contents: read`.
   `issues: write` must NOT appear at the workflow level (widest scope).
4. The `notify` job declares `issues: write` in its own `permissions:` block
   (narrowest scope that GitHub Actions supports for issue comment writes).
5. `JULES_API_KEY` is step-scoped — NOT declared in `jobs.probe.env` or
   workflow-level `env`.

Follows the per-workflow contract test pattern established by
`tests/kb/test_jules_archive_stale_workflow.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "jules-account-probe.yml"
EXPECTED_CRON = "0 0,9,18 * * *"


@pytest.fixture(scope="module")
def workflow() -> dict:
    """Parse the workflow YAML once per test session."""
    assert WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}"
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def workflow_text() -> str:
    """Raw workflow text for substring assertions that need the source form."""
    return WORKFLOW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def probe_job(workflow: dict) -> dict:
    jobs = workflow.get("jobs", {})
    assert "probe" in jobs, "expected a `probe` job in jules-account-probe.yml"
    return jobs["probe"]


@pytest.fixture(scope="module")
def notify_job(workflow: dict) -> dict:
    jobs = workflow.get("jobs", {})
    assert "notify" in jobs, (
        "expected a `notify` job in jules-account-probe.yml for tracking-issue updates"
    )
    return jobs["notify"]


# ---------------------------------------------------------------------------
# Trigger tests
# ---------------------------------------------------------------------------

def test_workflow_dispatch_trigger_present(workflow: dict) -> None:
    on_block = workflow.get(True, workflow.get("on", {}))
    assert "workflow_dispatch" in on_block, (
        "jules-account-probe.yml must have a `workflow_dispatch` trigger"
    )


def test_schedule_trigger_present(workflow: dict) -> None:
    on_block = workflow.get(True, workflow.get("on", {}))
    assert "schedule" in on_block, (
        "jules-account-probe.yml must have a `schedule` trigger (cron `0 0,9,18 * * *`)"
    )


def test_schedule_cron_is_exactly_three_daily_slots(workflow: dict) -> None:
    on_block = workflow.get(True, workflow.get("on", {}))
    schedule = on_block.get("schedule", [])
    crons = [str(item["cron"]) for item in schedule if isinstance(item, dict) and "cron" in item]
    assert EXPECTED_CRON in crons, (
        f"jules-account-probe.yml must have cron schedule `{EXPECTED_CRON}` "
        f"(3 slots/day: 00:00/09:00/18:00 UTC). Found: {crons}"
    )


# ---------------------------------------------------------------------------
# Permission tests
# ---------------------------------------------------------------------------

def test_workflow_level_permissions_are_contents_read_only(workflow: dict) -> None:
    """Workflow-level permissions must be {contents: read} only.

    `issues: write` must NOT appear at the workflow level — it is scoped
    to the `notify` job to minimize the blast radius if the token is
    compromised.
    """
    perms = workflow.get("permissions", {})
    assert isinstance(perms, dict), (
        f"workflow-level permissions must be a mapping. Got: {type(perms).__name__}"
    )
    assert perms.get("contents") == "read", (
        f"workflow-level `permissions.contents` must be `read`. Got: {perms.get('contents')!r}"
    )
    assert "issues" not in perms, (
        "workflow-level `permissions.issues` must NOT be declared. "
        "`issues: write` belongs in the `notify` job's permissions block only."
    )


def test_notify_job_has_issues_write(notify_job: dict) -> None:
    """`notify` job must declare `issues: write` in its own permissions block."""
    perms = notify_job.get("permissions", {})
    assert isinstance(perms, dict), (
        f"`notify` job permissions must be a mapping. Got: {type(perms).__name__}"
    )
    assert perms.get("issues") == "write", (
        f"`notify` job must declare `permissions.issues: write`. "
        f"Got: {perms.get('issues')!r}"
    )


def test_probe_job_does_not_have_issues_write(probe_job: dict) -> None:
    """`probe` job must NOT declare `issues: write` — probe is read-only."""
    perms = probe_job.get("permissions", {})
    if not isinstance(perms, dict):
        return  # No job-level permissions at all → fine
    assert "issues" not in perms, (
        "`probe` job must NOT declare `permissions.issues` — "
        "only the `notify` job needs issue-write access."
    )


# ---------------------------------------------------------------------------
# JULES_API_KEY scope test
# ---------------------------------------------------------------------------

def test_jules_api_key_is_step_scoped_not_job_scoped(probe_job: dict) -> None:
    """`JULES_API_KEY` must be bound at the step level, not the job level.

    Per AGENTS.md: job-level secrets leak to all steps including
    `actions/checkout` and third-party actions.
    """
    job_env = probe_job.get("env", {}) or {}
    assert "JULES_API_KEY" not in job_env, (
        "JULES_API_KEY must NOT be declared at the job level (`jobs.probe.env`). "
        "Bind it at the step level (`steps[].env.JULES_API_KEY`) so it does not "
        "leak to checkout and other steps."
    )
    steps = probe_job.get("steps", [])
    step_env_declarations = [
        bool((step.get("env") or {}).get("JULES_API_KEY"))
        for step in steps
    ]
    assert any(step_env_declarations), (
        "Expected at least one step in the `probe` job to declare JULES_API_KEY "
        "in its `env` block."
    )


# ---------------------------------------------------------------------------
# Notify job structure tests
# ---------------------------------------------------------------------------

def test_notify_job_runs_if_always(notify_job: dict) -> None:
    """`notify` job must have `if: always()` so it runs even when probe fails."""
    job_if = str(notify_job.get("if", "")).strip()
    assert "always()" in job_if, (
        f"`notify` job must have `if: always()` to run even when probe fails. "
        f"Got: {job_if!r}"
    )


def test_notify_job_depends_on_probe(notify_job: dict) -> None:
    """`notify` job must declare `needs: probe`."""
    needs = notify_job.get("needs", [])
    if isinstance(needs, str):
        needs = [needs]
    assert "probe" in needs, (
        "`notify` job must declare `needs: probe` so it runs after the probe job."
    )


def test_notify_job_uses_probe_result_from_needs(workflow_text: str) -> None:
    """The notification step must read `needs.probe.result` (not a hard-coded value)."""
    assert "needs.probe.result" in workflow_text, (
        "The `notify` job must reference `needs.probe.result` to determine "
        "whether the probe succeeded or failed."
    )


# ---------------------------------------------------------------------------
# Tracking-issue lookup tests
# ---------------------------------------------------------------------------

def test_notify_step_looks_up_by_probe_tracking_label(workflow_text: str) -> None:
    """The notification step must look up the tracking issue by `probe-tracking` label."""
    assert "probe-tracking" in workflow_text, (
        "The `notify` job must look up the tracking issue using the "
        "`probe-tracking` label."
    )


def test_notify_step_fails_closed_on_missing_issue(workflow_text: str) -> None:
    """The notification step must fail closed (exit 1) when no tracking issue is found."""
    assert "exit 1" in workflow_text, (
        "The `notify` step must call `exit 1` when the tracking issue is missing."
    )


def test_failure_comment_uses_prefix(workflow_text: str) -> None:
    """Failure comments must use the `❌ Probe failed` prefix for recovery detection."""
    assert "❌ Probe failed" in workflow_text, (
        "The failure comment in the `notify` step must start with `❌ Probe failed` "
        "so the recovery-detection algorithm can identify failure comments."
    )


def test_recovery_comment_uses_prefix(workflow_text: str) -> None:
    """Recovery comments must use the `✅ Recovered` prefix."""
    assert "✅ Recovered" in workflow_text, (
        "The recovery comment in the `notify` step must start with `✅ Recovered`."
    )
