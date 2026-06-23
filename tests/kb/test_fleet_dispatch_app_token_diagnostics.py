"""Pytest-style contract tests for PR #378 / Issue #310 App-token diagnostics.

Lives separate from `tests/kb/test_fleet_merge_workflow.py` (legacy unittest-style
per ADR-029 ratchet) so this new pytest module can grow without forcing the
larger legacy file to migrate.

Locks the three-branch App-token warning structure, the permissions-not-granted
root-cause text, and the operator-grep success line shared between the workflow
and the mvp-runbook. The existing
`test_phase_2a_auto_merge_prefers_app_token_with_github_token_fallback` test in
test_fleet_merge_workflow.py is substring-blind to all of these — it asserts
only that *a* warning containing "Issue #310" and "Layer 6" exists, which is
true in both the pre-PR generic warning and the new three-branch split.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "fleet-dispatch.yml"
RUNBOOK_PATH = REPO_ROOT / "docs" / "mvp-runbook.md"

# Exact operator-grep target — the runbook tells operators to grep for this
# string after Phase 2a to confirm the App token path activated. If the
# workflow emits a different string, the runbook silently lies.
APP_TOKEN_SUCCESS_LINE = (
    "✅ Issue #310: using GitHub App installation token for planning PR auto-merge."
)


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def runbook_text() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def auto_merge_step_text(workflow_text: str) -> str:
    """Isolate the `Queue auto-merge of planning PR` step run block."""
    marker = "Queue auto-merge of planning PR"
    start = workflow_text.index(marker)
    # End at the next top-level step marker, or EOF if this is the final step.
    next_step_idx = workflow_text.find("\n      - name:", start + len(marker))
    end = next_step_idx if next_step_idx != -1 else len(workflow_text)
    return workflow_text[start:end]


def test_phase_2a_distinguishes_token_creation_failure_from_missing_secrets(
    auto_merge_step_text: str,
) -> None:
    """The three-branch conditional must exist as if/elif/else over the two probes."""
    # Branch 1: App token created successfully
    assert (
        '[ "$APP_TOKEN_AVAILABLE" = "true" ] && [ "$APP_TOKEN_CREATED" = "true" ]'
        in auto_merge_step_text
    )
    # Branch 2: secrets present but creation FAILED (the diagnostic that PR #378
    # explicitly added — operator needs the permissions-not-granted hint here)
    assert (
        '[ "$APP_TOKEN_AVAILABLE" = "true" ] && [ "$APP_TOKEN_CREATED" != "true" ]'
        in auto_merge_step_text
    )
    # Branch 3: implicit else for secrets absent (no explicit elif needed)


def test_phase_2a_warning_names_permissions_root_cause(auto_merge_step_text: str) -> None:
    """The 'creation failed' warning must point at the App-permissions click-path.

    Without these substrings the operator cannot tell whether the 422 is a
    permissions gap, a private-key issue, or a missing install. PR #378 was
    explicitly created to add this specificity; lock it down so a "simplify
    the warning" refactor cannot silently regress.
    """
    assert "422" in auto_merge_step_text, (
        "warning must reference HTTP 422 — the actual GitHub API error code "
        "returned when installation permissions are missing"
    )
    assert "permissions requested are not granted" in auto_merge_step_text, (
        "warning must echo the GitHub API error message verbatim so operators "
        "can grep CI logs"
    )
    assert "Settings → Developer settings → GitHub Apps" in auto_merge_step_text, (
        "warning must name the exact UI click-path the operator needs"
    )
    assert "re-accept" in auto_merge_step_text, (
        "warning must mention the re-accept requirement — GitHub blocks silent "
        "grants after App permission changes"
    )


def test_phase_2a_secrets_absent_warning_is_distinct(auto_merge_step_text: str) -> None:
    """The 'secrets absent' warning must be a separate title from 'creation failed'."""
    assert (
        "Issue #310 GitHub App secrets not configured" in auto_merge_step_text
    ), "secrets-absent warning must have a distinct title for operator triage"
    assert (
        "Issue #310 GitHub App token creation failed" in auto_merge_step_text
    ), "creation-failed warning must have a distinct title for operator triage"


def test_phase_2a_success_line_matches_runbook_grep_target(
    auto_merge_step_text: str, runbook_text: str
) -> None:
    """The success line must match verbatim between the workflow and the runbook.

    The runbook's diagnostic checklist tells the operator to grep for this
    exact string to confirm Phase 2a worked. Any drift between the workflow
    output and the documented grep target silently breaks the operator
    workflow.
    """
    assert APP_TOKEN_SUCCESS_LINE in auto_merge_step_text, (
        f"workflow must emit the exact success line documented in the runbook: "
        f"{APP_TOKEN_SUCCESS_LINE!r}"
    )
    assert APP_TOKEN_SUCCESS_LINE in runbook_text, (
        f"runbook must document the exact success line the workflow emits: "
        f"{APP_TOKEN_SUCCESS_LINE!r}"
    )


def test_runbook_documents_app_permission_requirements(runbook_text: str) -> None:
    """The mvp-runbook's Layer 6 section must spell out the App permission contract.

    PR #378 added this content because the operator was previously left to
    re-derive the 422 root cause from CI logs every cycle. Lock the contract
    so a future runbook prune cannot silently delete it.
    """
    assert "App permission requirements (HITL operator step)" in runbook_text
    assert "Contents: Read & write" in runbook_text
    assert "Pull requests: Read & write" in runbook_text
    assert "Diagnostic checklist when warning appears" in runbook_text
    # The three actionable HTTP statuses operators may encounter:
    assert "422" in runbook_text
    assert "401" in runbook_text
    assert "404" in runbook_text
