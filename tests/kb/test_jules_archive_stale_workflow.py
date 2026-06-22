"""Per-workflow contract tests for `.github/workflows/jules-archive-stale.yml`.

This workflow runs destructive `apply=true` operations against the Jules
session API. The cross-functional security review of PRs #312-#317 found
a HIGH-severity bug where the environment-approval gate expression was
type-mismatched (`inputs.apply == 'true'` against `type: boolean` input)
and silently never engaged. A per-workflow contract test would have caught
that pre-merge. This file is the closing of that loop (Issue #320).

The tests pin the following invariants:

1. Environment gate uses boolean-truthy form, never string comparison
   against the boolean `inputs.apply` input.
2. Concurrency group partitions by `inputs.apply` so dry-run + apply
   queues don't cancel each other.
3. `cancel-in-progress: false` to prevent partial-state archive risk.
4. `inputs.apply` stays `type: boolean` — if it ever flips to string,
   the truthy expression silently changes semantics for non-canonical
   values ("True", "TRUE", "1").

Follows the per-workflow contract test pattern established by
`tests/kb/test_ci6_workflow.py` and `tests/kb/test_fleet_plan_workflow.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "jules-archive-stale.yml"


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
def archive_job(workflow: dict) -> dict:
    """The `archive` job — the only mutation surface in this workflow."""
    jobs = workflow.get("jobs", {})
    assert "archive" in jobs, "expected an `archive` job in jules-archive-stale.yml"
    return jobs["archive"]


def test_environment_expression_uses_boolean_truthiness_not_string_comparison(
    archive_job: dict,
    workflow_text: str,
) -> None:
    """The environment-gate expression must NOT compare boolean `inputs.apply`
    against the string `'true'` — under GitHub Actions' expression evaluator
    (`AbstractEqual + CoerceTypes`), string `'true'` numeric-coerces to NaN
    and `boolean true` coerces to `1.0`, so the comparison always returns
    false. That made the `jules-archive-approval` environment-approval gate
    completely inert on every `apply=true` destructive run.

    See post-merge audit 2026-06-20, HIGH severity finding on commit 4e7679b,
    fixed in commit 06f7e06.
    """
    env_expr = str(archive_job.get("environment", ""))

    # Forbidden pattern: comparing the boolean input to the string 'true'.
    assert "inputs.apply == 'true'" not in env_expr, (
        "Forbidden pattern: `inputs.apply == 'true'` compares boolean to string "
        "and always evaluates to false under the GH Actions expression evaluator. "
        "Use boolean-truthy form: `${{ inputs.apply && 'jules-archive-approval' || '' }}`. "
        "See post-merge audit HIGH finding (commit 06f7e06)."
    )

    # Must use one of the correct forms.
    correct_forms = (
        "inputs.apply &&",
        "inputs.apply == true",
        "fromJSON(inputs.apply)",
    )
    assert any(form in env_expr for form in correct_forms), (
        f"Environment expression must use a boolean-truthy form (one of {correct_forms}). "
        f"Got: {env_expr!r}"
    )

    # And the approval environment must be referenced.
    assert "jules-archive-approval" in env_expr, (
        "Environment expression must reference the `jules-archive-approval` gate. "
        f"Got: {env_expr!r}"
    )


def test_environment_expression_destructive_branch_is_jules_archive_approval(
    archive_job: dict,
) -> None:
    """The destructive branch (when `inputs.apply` is truthy) MUST resolve
    to `jules-archive-approval`, not some other environment name. A future
    typo or refactor that swapped the branches (e.g.,
    `inputs.apply && 'unprotected' || 'jules-archive-approval'`) would gate
    the wrong path and shipping that would re-introduce the HIGH bug class.
    """
    env_expr = str(archive_job.get("environment", ""))

    # In the canonical `cond && 'A' || 'B'` ternary, A is the truthy branch.
    # We expect: `${{ inputs.apply && 'jules-archive-approval' || ... }}`.
    # Allow flexibility on the falsy branch (empty string OR another safe value)
    # but the truthy branch must be exactly 'jules-archive-approval'.
    import re
    match = re.search(r"inputs\.apply\s*&&\s*'([^']+)'\s*\|\|\s*'([^']*)'", env_expr)
    assert match is not None, (
        f"Could not parse `inputs.apply && 'TRUTHY' || 'FALSY'` ternary from environment "
        f"expression. Got: {env_expr!r}"
    )
    truthy_branch = match.group(1)
    falsy_branch = match.group(2)

    assert truthy_branch == "jules-archive-approval", (
        f"The truthy (destructive) branch of the environment ternary must be exactly "
        f"`jules-archive-approval`, got {truthy_branch!r}. Swapping the branches would "
        f"gate the wrong path."
    )
    assert falsy_branch == "", (
        f"The falsy (dry-run) branch must be the empty string so dry-runs bypass "
        f"environment approval. Got {falsy_branch!r}."
    )


def test_concurrency_group_partitions_by_apply_input(archive_job: dict) -> None:
    """Concurrency group must include `${{ inputs.apply }}` so dry-run + apply
    queues don't cancel each other. PR #312 intentionally split the queues
    (dry-run can run concurrently with an in-flight apply — operational
    TOCTOU acceptable because dry-run does not mutate).
    """
    concurrency = archive_job.get("concurrency", {})
    group = str(concurrency.get("group", ""))
    assert "${{ inputs.apply }}" in group, (
        f"Concurrency group must include `${{{{ inputs.apply }}}}` to partition "
        f"dry-run and apply queues. Got: {group!r}"
    )


def test_concurrency_cancel_in_progress_is_false(archive_job: dict) -> None:
    """`cancel-in-progress: false` prevents partial-state archive risk. If
    flipped to `true`, an in-flight `apply=true` run could be cancelled mid-
    archive by a subsequent dispatch, leaving the Jules account in an
    inconsistent state (some sessions archived, others not).
    """
    concurrency = archive_job.get("concurrency", {})
    cancel = concurrency.get("cancel-in-progress")
    assert cancel is False, (
        f"`cancel-in-progress` must be False (boolean) to prevent partial-state "
        f"archive risk. Got: {cancel!r}"
    )


def test_apply_input_declared_boolean(workflow: dict) -> None:
    """`inputs.apply` must remain `type: boolean`. If it ever becomes `string`,
    the boolean-truthy environment expression silently changes semantics —
    non-canonical values like `"True"`, `"TRUE"`, `"1"` would all be truthy
    in the expression evaluator's coercion rules, but the bash step's
    `if [ "$INPUT_APPLY" = "true" ]` check is case-sensitive. The mismatch
    between expression-level and shell-level apply-detection would silently
    re-introduce the inert-gate bug class.
    """
    on_block = workflow.get(True, workflow.get("on", {}))
    dispatch = on_block.get("workflow_dispatch", {}) or {}
    inputs = dispatch.get("inputs", {})
    apply_input = inputs.get("apply", {})
    assert apply_input.get("type") == "boolean", (
        f"`workflow_dispatch.inputs.apply.type` must be `boolean`. "
        f"Got: {apply_input.get('type')!r}. If you change this, the environment "
        f"expression's truthy semantics may silently shift."
    )


def test_jules_api_key_is_step_scoped_not_job_scoped(archive_job: dict) -> None:
    """`JULES_API_KEY` must be bound at the step level, not the job level.
    Per AGENTS.md GitHub Actions guidance on step-scoped secret binding —
    job-level secrets leak to all steps including `actions/checkout` and
    third-party actions, widening the attack surface unnecessarily.
    """
    job_env = archive_job.get("env", {}) or {}
    assert "JULES_API_KEY" not in job_env, (
        "JULES_API_KEY must NOT be declared at the job level (`jobs.archive.env`). "
        "Bind it at the step level (`steps[].env.JULES_API_KEY`) so it doesn't leak "
        "to checkout and other steps."
    )
    # And at least one step must declare it (otherwise the dispatch can't work).
    steps = archive_job.get("steps", [])
    step_env_declarations = [
        bool((step.get("env") or {}).get("JULES_API_KEY"))
        for step in steps
    ]
    assert any(step_env_declarations), (
        "Expected at least one step in `archive` job to declare JULES_API_KEY "
        "in its `env` block."
    )


def test_workflow_permissions_are_narrowly_scoped(workflow: dict) -> None:
    """Workflow-level permissions must NOT include `contents: write` or
    `pull-requests: write`. This workflow only needs `contents: read` to
    check out the repo for running fleet scripts. The destructive operation
    is against the Jules API, not the repo itself.
    """
    perms = workflow.get("permissions", {})
    if isinstance(perms, str):
        # If permissions is a single string (e.g., 'read-all'), accept.
        assert perms in {"read-all", "read"}, (
            f"workflow-level permissions string must be read-only. Got: {perms!r}"
        )
        return
    assert isinstance(perms, dict), f"unexpected permissions shape: {type(perms).__name__}"
    contents = perms.get("contents")
    assert contents in (None, "read"), (
        f"workflow-level `permissions.contents` must be read or omitted (jules-archive "
        f"only checks out the repo for fleet script context). Got: {contents!r}"
    )
    assert "pull-requests" not in perms, (
        "workflow-level `permissions.pull-requests` must not be declared "
        "(this workflow does not touch PRs)."
    )
    # ADR-033 (label-driven dispatch adoption): `--apply` mode adds
    # `ready-for-agent` / `needs-triage` labels via `restoreIssueAfterFailure`
    # when archive succeeds for a current-repo session. The narrow scope is
    # enforced by the `jules-archive-approval` environment gate on
    # `inputs.apply == true`, so unauthorized callers cannot trigger label
    # mutations. Dry-run mode does not exercise this path. The previous
    # blanket prohibition pre-dates label-driven dispatch.
    issues = perms.get("issues")
    assert issues in (None, "read", "write"), (
        f"workflow-level `permissions.issues` must be omitted, read, or write. "
        f"Got: {issues!r}"
    )
