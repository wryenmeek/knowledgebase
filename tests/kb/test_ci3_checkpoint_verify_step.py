"""Pytest-style contract tests for the PR4 CI-3 checkpoint-registry verify step.

Lives separate from `test_ci3_workflow.py` (legacy unittest-style per
ADR-029 ratchet) so this new pytest module can grow without forcing the
larger legacy file to migrate in the same change. Pins the CI-3
`Surface checkpoint registry verify report` step that PR #376 added.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci-3-pr-producer.yml"
STEP_MARKER = "Surface checkpoint registry verify report"
NEXT_STEP_MARKER = "Create or update CI-3 PR"
PRECEDING_STEP_MARKER = "Fail on severe CI-3 runtime budget breach"


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def verify_step_text(workflow_text: str) -> str:
    start = workflow_text.index(STEP_MARKER)
    end = workflow_text.index(NEXT_STEP_MARKER, start)
    return workflow_text[start:end]


def test_checkpoint_registry_verify_step_name_present(workflow_text: str) -> None:
    """PR4 (#376) — verify step must remain wired into the producer workflow."""
    assert STEP_MARKER in workflow_text


def test_checkpoint_registry_verify_step_uses_warn_only_invocation(
    workflow_text: str,
) -> None:
    """Verify invocation must use --warn-only telemetry mode (ADR-026)."""
    assert (
        "python3 scripts/kb/checkpoint_registry.py --verify --warn-only"
        in workflow_text
    )


def test_checkpoint_registry_verify_step_does_not_acquire_write_lock(
    verify_step_text: str,
) -> None:
    """Step must not pass --mutate / --bootstrap / --apply (would acquire lock)."""
    assert "--mutate" not in verify_step_text
    assert "--bootstrap" not in verify_step_text
    assert "--apply" not in verify_step_text


def test_checkpoint_registry_verify_step_gate(verify_step_text: str) -> None:
    """Gate must be always() so verify surfaces even on upstream failure,
    but still scoped to runs that processed sources."""
    assert (
        "always() && steps.sources.outputs.has_sources == 'true'"
        in verify_step_text
    )


def test_checkpoint_registry_verify_step_writes_step_summary(
    verify_step_text: str,
) -> None:
    """Step must write to GITHUB_STEP_SUMMARY — the contract surface for telemetry."""
    assert "${GITHUB_STEP_SUMMARY}" in verify_step_text


def test_checkpoint_registry_verify_step_position_after_runtime_budget(
    workflow_text: str,
) -> None:
    """Verify step must run after runtime-budget evaluation so budget context exists."""
    runtime_budget_idx = workflow_text.index(PRECEDING_STEP_MARKER)
    verify_idx = workflow_text.index(STEP_MARKER)
    assert runtime_budget_idx < verify_idx, (
        "verify step must follow runtime-budget evaluation"
    )


def test_checkpoint_registry_verify_step_never_fails_workflow(
    verify_step_text: str,
) -> None:
    """Per ADR-026 verify telemetry contract — step must terminate with exit 0
    so verify warnings or hard crashes never block the CI-3 PR producer pipeline."""
    assert "exit 0" in verify_step_text
