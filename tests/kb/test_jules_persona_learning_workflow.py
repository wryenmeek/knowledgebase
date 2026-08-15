"""Per-workflow contract tests for `.github/workflows/jules-persona-learning.yml`.

Covers U6 of docs/plans/2026-08-10-001-feat-jules-persona-learning-loop-plan.md
(the Jules persona PR learning loop's workflow wiring). These are static
YAML-only assertions (no execution) that pin the MVP safety invariants:

- Trigger is `workflow_dispatch` only — no `schedule:` anywhere, so
  proposal creation is never automatic (R11/R13).
- Workflow-level permissions are `contents: read` only; write scopes
  (`contents: write`, `pull-requests: write`) exist only on the `propose`
  job, never at workflow level (R11 least privilege).
- The `collect` job has no write permission of any kind (read-only
  collector/report boundary).
- The `propose` job runs only for `mode: propose` and depends on
  `collect` in the same run (same-run artifact binding).
- No `pull_request_target` trigger anywhere in this file.
- `GH_TOKEN` is step-scoped (declared under a step's `env:`), never at
  job or workflow level, in either job.
- Workflow inputs are never interpolated directly inside `run:` blocks
  (shell/expression injection guard) — they are passed through `env:`.
- No merge/close/redispatch step exists anywhere in this workflow.
- Concurrency groups exist at both workflow and `propose`-job level with
  `cancel-in-progress: false`.

Follows the per-workflow contract test pattern established by
`tests/kb/test_jules_archive_stale_workflow.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "jules-persona-learning.yml"
)


@pytest.fixture(scope="module")
def workflow() -> dict:
    """Parse the workflow YAML once per test session."""
    assert WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}"
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def workflow_text() -> str:
    """Raw workflow text for substring/regex assertions that need source form."""
    return WORKFLOW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def on_block(workflow: dict) -> dict:
    """The `on:` trigger block. PyYAML parses the bare `on` key as `True`."""
    return workflow.get(True, workflow.get("on", {}))


@pytest.fixture(scope="module")
def collect_job(workflow: dict) -> dict:
    jobs = workflow.get("jobs", {})
    assert "collect" in jobs, "expected a `collect` job"
    return jobs["collect"]


@pytest.fixture(scope="module")
def propose_job(workflow: dict) -> dict:
    jobs = workflow.get("jobs", {})
    assert "propose" in jobs, "expected a `propose` job"
    return jobs["propose"]


def _all_steps(job: dict) -> list[dict]:
    return list(job.get("steps", []))


def _run_blocks(job: dict) -> list[str]:
    return [str(step["run"]) for step in _all_steps(job) if step.get("run")]


# ── Trigger contract (R11/R13: no scheduled proposal trigger) ───────────────


def test_trigger_is_workflow_dispatch_only(on_block: dict) -> None:
    """The workflow must be triggered only by `workflow_dispatch` — no
    `schedule:`, `push:`, `pull_request:`, or `pull_request_target:`.
    """
    assert set(on_block.keys()) == {"workflow_dispatch"}, (
        f"Expected only `workflow_dispatch` trigger, got: {sorted(on_block.keys())}"
    )


def test_no_schedule_trigger(on_block: dict) -> None:
    """No cron schedule anywhere — collection and proposal are both manual."""
    assert "schedule" not in on_block


def test_no_pull_request_target_trigger(on_block: dict) -> None:
    """Must never use `pull_request_target` (untrusted-PR-code checkout risk)."""
    assert "pull_request_target" not in on_block


def test_mode_input_is_report_by_default(on_block: dict) -> None:
    """`mode` input must default to `report` (read-only), not `propose`."""
    inputs = on_block["workflow_dispatch"]["inputs"]
    assert "mode" in inputs
    assert inputs["mode"].get("default") == "report"
    assert set(inputs["mode"].get("options", [])) == {"report", "propose"}


# ── Permissions contract (R11: exact permissions, least privilege) ─────────


def test_workflow_level_permissions_are_read_only(workflow: dict) -> None:
    """Workflow-level `permissions:` must be `contents: read` only — no
    write scope may be granted at workflow level (only job level).
    """
    perms = workflow.get("permissions", {})
    assert perms == {"contents": "read"}, (
        f"Workflow-level permissions must be exactly {{'contents': 'read'}}, got: {perms}"
    )


def test_collect_job_has_read_only_permissions(collect_job: dict) -> None:
    """The `collect` job must declare `contents: read` only — no write
    scope of any kind (it is the read-only collector/report boundary).
    """
    perms = collect_job.get("permissions", {})
    assert perms == {"contents": "read"}, (
        f"collect job permissions must be exactly {{'contents': 'read'}}, got: {perms}"
    )
    for value in perms.values():
        assert value == "read", f"collect job must not declare any write permission, got: {perms}"


def test_propose_job_has_narrow_write_permissions(propose_job: dict) -> None:
    """The `propose` job may declare `contents: write` and
    `pull-requests: write` — and nothing else (no `issues`, `actions`,
    `packages`, etc.).
    """
    perms = propose_job.get("permissions", {})
    assert perms.get("contents") == "write"
    assert perms.get("pull-requests") == "write"
    allowed_keys = {"contents", "pull-requests"}
    assert set(perms.keys()) <= allowed_keys, (
        f"propose job must declare only {allowed_keys}, got: {set(perms.keys())}"
    )


# ── Job dependency / mode gating ─────────────────────────────────────────────


def test_propose_job_depends_on_collect(propose_job: dict) -> None:
    """The `propose` job must consume the *same-run* `collect` artifact."""
    needs = propose_job.get("needs")
    if isinstance(needs, list):
        assert "collect" in needs
    else:
        assert needs == "collect"


def test_propose_job_gated_on_environment_approval(propose_job: dict) -> None:
    """The `propose` job must require approval on a dedicated GitHub
    Environment — an authorization boundary independent of the
    `mode: propose` dispatch-input gate, consistent with
    `jules-archive-approval` (`jules-archive-stale.yml`) and
    `sweep-real-delete-approval` (`sweep-stale-bot-branches.yml`)
    elsewhere in this repository (finding-#4 remediation).
    """
    environment = propose_job.get("environment")
    assert environment, "propose job must declare an `environment:` approval gate"
    assert "propose" in str(environment), (
        f"propose job's environment gate should be persona-learning-propose-specific, got: {environment!r}"
    )


def test_propose_job_gated_on_propose_mode(propose_job: dict) -> None:
    """The `propose` job must only run when `mode == 'propose'`."""
    condition = str(propose_job.get("if", ""))
    assert "propose" in condition
    assert "mode" in condition


def test_collect_job_has_no_mode_gate(collect_job: dict) -> None:
    """The `collect` job always runs (both `report` and `propose` modes
    need a same-run artifact) — it must not be gated on `mode`.
    """
    assert "if" not in collect_job


# ── Credential scoping (step-scoped, never job/workflow level) ──────────────


def test_gh_token_not_declared_at_job_level(collect_job: dict, propose_job: dict) -> None:
    """`GH_TOKEN` must never appear in a job-level `env:` block."""
    for job_name, job in (("collect", collect_job), ("propose", propose_job)):
        job_env = job.get("env", {})
        assert "GH_TOKEN" not in job_env, f"{job_name} job must not declare GH_TOKEN at job level"


def test_gh_token_is_step_scoped(collect_job: dict, propose_job: dict) -> None:
    """`GH_TOKEN` must be declared in at least one step's `env:` block in
    each job that needs GitHub API access.
    """
    for job_name, job in (("collect", collect_job), ("propose", propose_job)):
        found = any("GH_TOKEN" in step.get("env", {}) for step in _all_steps(job))
        assert found, f"{job_name} job must declare GH_TOKEN in a step-level env: block"


def test_workflow_has_no_top_level_env(workflow: dict) -> None:
    """No workflow-level `env:` block carrying credentials."""
    assert "env" not in workflow, "Workflow-level env: block is not permitted (step-scoped only)"


# ── Shell/expression injection guard ─────────────────────────────────────────


_INPUT_EXPR_RE = re.compile(r"\$\{\{\s*(?:github\.event\.)?inputs\.[A-Za-z_]+\s*\}\}")


def test_inputs_not_interpolated_directly_in_run_blocks(
    collect_job: dict, propose_job: dict
) -> None:
    """`${{ inputs.* }}` / `${{ github.event.inputs.* }}` must never appear
    directly inside a `run:` block — values must be passed through `env:`
    first (repo convention; GH Actions substitutes `${{ }}` expressions
    before the shell runs, so direct interpolation is an injection vector).
    """
    for job_name, job in (("collect", collect_job), ("propose", propose_job)):
        for run_block in _run_blocks(job):
            assert not _INPUT_EXPR_RE.search(run_block), (
                f"{job_name} job has a run: block that interpolates inputs.* directly: "
                f"{run_block!r}"
            )


def test_propose_inputs_passed_via_env_block(propose_job: dict) -> None:
    """Every human-supplied propose input must be threaded through a step
    `env:` block (`PR_LEARNING_*` vars), not inlined into `run:`.
    """
    expected_env_vars = {
        "PR_LEARNING_PERSONA",
        "PR_LEARNING_MECHANISM",
        "PR_LEARNING_AFFECTED_SCOPE",
        "PR_LEARNING_NORMALIZED_RULE",
        "PR_LEARNING_EVIDENCE_PR_NUMBERS",
        "PR_LEARNING_RULE",
        "PR_LEARNING_EVIDENCE",
        "PR_LEARNING_VERIFICATION",
        "PR_LEARNING_SCOPE",
        "PR_LEARNING_RETRACTION_CONDITION",
        "PR_LEARNING_BASE_BRANCH",
        "PR_LEARNING_ARTIFACT_PATH",
    }
    seen_env_vars: set[str] = set()
    for step in _all_steps(propose_job):
        seen_env_vars.update(step.get("env", {}).keys())
    missing = expected_env_vars - seen_env_vars
    assert not missing, f"propose job is missing expected env-scoped inputs: {missing}"


# ── No merge/redispatch surface ──────────────────────────────────────────────


def test_no_merge_or_redispatch_step(collect_job: dict, propose_job: dict) -> None:
    """This workflow must never merge, close, or redispatch its own (or any)
    PR — it only opens one human-reviewed proposal PR via propose-cli.ts.
    Checked against actual `run:` step bodies only (not doc comments).
    """
    for job_name, job in (("collect", collect_job), ("propose", propose_job)):
        for run_block in _run_blocks(job):
            assert "gh pr merge" not in run_block, f"{job_name} job must not run `gh pr merge`"
            assert "gh pr close" not in run_block, f"{job_name} job must not run `gh pr close`"
            assert "--auto" not in run_block, f"{job_name} job must not queue auto-merge"


def test_no_fleet_orchestrator_app_token(workflow_text: str) -> None:
    """This workflow only opens PRs (never merges) so per the
    fleet-orchestrator-token composite action's own documented contract
    ("Workflows that only open PRs (HITL-reviewed) MUST NOT invoke this"),
    it must stay on the default unelevated `github.token`.
    """
    assert "fleet-orchestrator-token" not in workflow_text


# ── Concurrency contract ─────────────────────────────────────────────────────


def test_workflow_level_concurrency_never_cancels(workflow: dict) -> None:
    concurrency = workflow.get("concurrency", {})
    assert concurrency.get("cancel-in-progress") is False


def test_propose_job_has_own_concurrency_group(propose_job: dict) -> None:
    concurrency = propose_job.get("concurrency", {})
    assert concurrency.get("cancel-in-progress") is False
    assert "group" in concurrency


# ── Checkout / no untrusted PR code ──────────────────────────────────────────


def test_checkout_steps_do_not_reference_pr_head(workflow_text: str) -> None:
    """No checkout step may reference a PR head ref/SHA — this workflow is
    `workflow_dispatch`-only, so every checkout must be the default ref.
    """
    assert "github.event.pull_request" not in workflow_text


# ── Distinct branch/marker awareness (documentation contract) ──────────────


def test_workflow_documents_jules_memory_branch_exclusion(workflow_text: str) -> None:
    """The workflow's header comments must reference the jules-memory/*
    branch-prefix exclusion contract shared with fleet-merge.yml /
    fleet-dispatch.yml (R12)."""
    assert "jules-memory" in workflow_text
    assert "fleet-merge.yml" in workflow_text
    assert "fleet-dispatch.yml" in workflow_text
