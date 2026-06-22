"""Workflow contract checks for `.github/workflows/pre-commit.yml`.

PR #337 wired ``GITHUB_PR_HEAD_SHA: ${{ github.event.pull_request.head.sha }}``
into the "Run pre-commit on all files" step so that
``check_locality_ratchet.py`` can verify PR-head commit parentage in CI.
This test pins that wiring so future refactors cannot silently remove it.

Follows the per-workflow contract test pattern established by
``tests/kb/test_jules_archive_stale_workflow.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pre-commit.yml"
)

_RUN_STEP_NAME = "Run pre-commit on all files"


@pytest.fixture(scope="module")
def workflow() -> dict:
    """Parse the workflow YAML once per test session."""
    assert WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}"
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def run_step(workflow: dict) -> dict:
    """The 'Run pre-commit on all files' step."""
    jobs = workflow.get("jobs", {})
    pre_commit_job = jobs.get("pre-commit", {})
    steps = pre_commit_job.get("steps", [])
    matching = [s for s in steps if s.get("name") == _RUN_STEP_NAME]
    assert matching, (
        f"Could not find a step named {_RUN_STEP_NAME!r} in "
        f"jobs.pre-commit.steps of {WORKFLOW_PATH}"
    )
    return matching[0]


def test_run_step_env_contains_github_pr_head_sha(run_step: dict) -> None:
    """GITHUB_PR_HEAD_SHA must be wired to github.event.pull_request.head.sha.

    ``check_locality_ratchet.py`` reads this env variable in CI to resolve
    the PR-head commit when verifying the Locality-4 ratchet diff.  Without
    this binding the hook falls back to a heuristic that can match the wrong
    revision on re-runs (Issue #340 / PR #337 remediation).
    """
    env = run_step.get("env") or {}
    assert "GITHUB_PR_HEAD_SHA" in env, (
        f"Step {_RUN_STEP_NAME!r} must declare GITHUB_PR_HEAD_SHA in its env block. "
        f"Found env keys: {sorted(env)}"
    )
    expected = "${{ github.event.pull_request.head.sha }}"
    actual = env["GITHUB_PR_HEAD_SHA"]
    assert actual == expected, (
        f"env.GITHUB_PR_HEAD_SHA must equal {expected!r}. "
        f"Got: {actual!r}"
    )
