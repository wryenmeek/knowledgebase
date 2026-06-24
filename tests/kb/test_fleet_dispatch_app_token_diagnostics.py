"""Pytest-style contract tests for Issue #310 / ADR-036 fleet-orchestrator App-token integration.

Originally created for PR #378 (Issue #310 App-token diagnostics).
Extended by ADR-036 to cover the fleet-orchestrator App identity (FLEET_APP_*
secrets) across all three fleet workflows: fleet-dispatch.yml (Phase 2a),
fleet-dispatch-after-merge.yml (Phase 2b), and fleet-merge.yml (Phase 3).

Lives separate from `tests/kb/test_fleet_merge_workflow.py` (legacy unittest-style
per ADR-029 ratchet) so this new pytest module can grow without forcing the
larger legacy file to migrate.

Locks:
- The three-branch App-token warning structure in Phase 2a
- The permissions-not-granted root-cause text
- The operator-grep success line shared between the workflow and the mvp-runbook
- FLEET_APP_* secret naming across all three fleet workflows (ADR-036)
- The kb-source-monitor / fleet-orchestrator identity split (no widening)
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "fleet-dispatch.yml"
FLEET_MERGE_PATH = REPO_ROOT / ".github" / "workflows" / "fleet-merge.yml"
FLEET_AFTER_MERGE_PATH = (
    REPO_ROOT / ".github" / "workflows" / "fleet-dispatch-after-merge.yml"
)
RUNBOOK_PATH = REPO_ROOT / "docs" / "mvp-runbook.md"
ADR_036_PATH = (
    REPO_ROOT / "docs" / "decisions" / "ADR-036-fleet-orchestrator-github-app-identity.md"
)

# Exact operator-grep target — the runbook tells operators to grep for this
# string after Phase 2a to confirm the App token path activated. If the
# workflow emits a different string, the runbook silently lies.
APP_TOKEN_SUCCESS_LINE = (
    "✅ Issue #310: using fleet-orchestrator App installation token for planning PR auto-merge."
)


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def fleet_merge_text() -> str:
    return FLEET_MERGE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def fleet_after_merge_text() -> str:
    return FLEET_AFTER_MERGE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def runbook_text() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def adr_036_text() -> str:
    return ADR_036_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def auto_merge_step_text(workflow_text: str) -> str:
    """Isolate the `Queue auto-merge of planning PR` step run block."""
    marker = "Queue auto-merge of planning PR"
    start = workflow_text.index(marker)
    next_step_idx = workflow_text.find("\n      - name:", start + len(marker))
    end = next_step_idx if next_step_idx != -1 else len(workflow_text)
    return workflow_text[start:end]


def test_phase_2a_distinguishes_token_creation_failure_from_missing_secrets(
    auto_merge_step_text: str,
) -> None:
    """The three-branch conditional must exist as if/elif/else over the two probes."""
    assert (
        '[ "$APP_TOKEN_AVAILABLE" = "true" ] && [ "$APP_TOKEN_CREATED" = "true" ]'
        in auto_merge_step_text
    )
    assert (
        '[ "$APP_TOKEN_AVAILABLE" = "true" ] && [ "$APP_TOKEN_CREATED" != "true" ]'
        in auto_merge_step_text
    )


def test_phase_2a_warning_names_permissions_root_cause(auto_merge_step_text: str) -> None:
    """The 'creation failed' warning must point at the App-permissions click-path."""
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
        "Issue #310 fleet-orchestrator App secrets not configured"
        in auto_merge_step_text
    ), "secrets-absent warning must have a distinct title for operator triage"
    assert (
        "Issue #310 fleet-orchestrator App token creation failed"
        in auto_merge_step_text
    ), "creation-failed warning must have a distinct title for operator triage"


def test_phase_2a_success_line_matches_runbook_grep_target(
    auto_merge_step_text: str, runbook_text: str
) -> None:
    """The success line must match verbatim between the workflow and the runbook."""
    assert APP_TOKEN_SUCCESS_LINE in auto_merge_step_text, (
        f"workflow must emit the exact success line documented in the runbook: "
        f"{APP_TOKEN_SUCCESS_LINE!r}"
    )
    assert APP_TOKEN_SUCCESS_LINE in runbook_text, (
        f"runbook must document the exact success line the workflow emits: "
        f"{APP_TOKEN_SUCCESS_LINE!r}"
    )


def test_runbook_documents_app_permission_requirements(runbook_text: str) -> None:
    """The mvp-runbook's Layer 6 section must spell out the App permission contract."""
    assert "App permission requirements" in runbook_text
    assert "Contents: Read & write" in runbook_text
    assert "Pull requests: Read & write" in runbook_text
    assert "Diagnostic checklist when warning appears" in runbook_text
    assert "422" in runbook_text
    assert "401" in runbook_text
    assert "404" in runbook_text


# ── ADR-036 multi-workflow coverage ──────────────────────────────────────────


def test_fleet_dispatch_references_fleet_app_secrets_not_gh_app(workflow_text: str) -> None:
    """fleet-dispatch.yml must use FLEET_APP_* secrets per ADR-036 — not GH_APP_*.

    GH_APP_* is the kb-source-monitor App which stays narrow read-only. ADR-036
    explicitly forbids widening kb-source-monitor; fleet workflows must reference
    the separate fleet-orchestrator App via FLEET_APP_* secret names.
    """
    assert "secrets.FLEET_APP_ID" in workflow_text, (
        "fleet-dispatch.yml must reference secrets.FLEET_APP_ID per ADR-036"
    )
    assert "secrets.FLEET_APP_PRIVATE_KEY" in workflow_text, (
        "fleet-dispatch.yml must reference secrets.FLEET_APP_PRIVATE_KEY per ADR-036"
    )
    assert "secrets.GH_APP_ID" not in workflow_text, (
        "fleet-dispatch.yml must NOT reference secrets.GH_APP_ID — that is "
        "kb-source-monitor (read-only source ingestion App per ADR-036)"
    )
    assert "secrets.GH_APP_PRIVATE_KEY" not in workflow_text, (
        "fleet-dispatch.yml must NOT reference secrets.GH_APP_PRIVATE_KEY — that "
        "is kb-source-monitor (read-only source ingestion App per ADR-036)"
    )


def test_fleet_merge_uses_fleet_orchestrator_app_token(fleet_merge_text: str) -> None:
    """fleet-merge.yml (Phase 3) must prefer fleet-orchestrator App token.

    Phase 3 sequential PR merges must fire downstream push workflows (e.g.,
    wiki freshness chained automations, future parent-issue auto-comment).
    GITHUB_TOKEN-authored merges hit the Layer 6 trap.
    """
    assert "secrets.FLEET_APP_ID" in fleet_merge_text, (
        "fleet-merge.yml must reference secrets.FLEET_APP_ID per ADR-036"
    )
    assert "secrets.FLEET_APP_PRIVATE_KEY" in fleet_merge_text, (
        "fleet-merge.yml must reference secrets.FLEET_APP_PRIVATE_KEY per ADR-036"
    )
    assert "actions/create-github-app-token" in fleet_merge_text, (
        "fleet-merge.yml must call create-github-app-token to mint the App token"
    )
    assert "steps.app-token.outputs.token || secrets.GITHUB_TOKEN" in fleet_merge_text, (
        "fleet-merge.yml must preserve GITHUB_TOKEN fallback per ADR-036 backout"
    )


def test_fleet_dispatch_after_merge_uses_fleet_orchestrator_app_token(
    fleet_after_merge_text: str,
) -> None:
    """fleet-dispatch-after-merge.yml (Phase 2b) must prefer fleet-orchestrator App.

    Per-task tracker comments author as fleet-orchestrator[bot] for unified
    bot identity and use the App's installation grant (which includes
    issues: write — closes Issue #311 permission gap on this surface).
    """
    assert "secrets.FLEET_APP_ID" in fleet_after_merge_text, (
        "fleet-dispatch-after-merge.yml must reference secrets.FLEET_APP_ID per ADR-036"
    )
    assert "secrets.FLEET_APP_PRIVATE_KEY" in fleet_after_merge_text, (
        "fleet-dispatch-after-merge.yml must reference secrets.FLEET_APP_PRIVATE_KEY per ADR-036"
    )
    assert "actions/create-github-app-token" in fleet_after_merge_text
    assert (
        "steps.app-token.outputs.token || secrets.GITHUB_TOKEN"
        in fleet_after_merge_text
    ), "fleet-dispatch-after-merge.yml must preserve GITHUB_TOKEN fallback per ADR-036"


def test_adr_036_exists_and_names_identity_split(adr_036_text: str) -> None:
    """ADR-036 must explicitly document the identity split to prevent re-widening."""
    assert "fleet-orchestrator" in adr_036_text
    assert "kb-source-monitor" in adr_036_text
    assert "FLEET_APP_ID" in adr_036_text
    assert "FLEET_APP_PRIVATE_KEY" in adr_036_text
    assert "Issue #310" in adr_036_text
    # The four fleet repos this App serves — locks the multi-repo scope
    assert "knowledgebase" in adr_036_text
    assert "vscode-genai" in adr_036_text
    assert "hot-springs-island" in adr_036_text
    assert "Scribe" in adr_036_text


def test_adr_036_indexed_in_decisions_readme() -> None:
    """ADR-036 must appear in the decisions README index per documentation cascade."""
    readme = (REPO_ROOT / "docs" / "decisions" / "README.md").read_text(encoding="utf-8")
    assert "ADR-036" in readme
    assert "Fleet orchestrator GitHub App identity" in readme


def test_cloneable_template_does_not_widen_source_monitor() -> None:
    """raw/inbox/cloneable-template.md must NOT grant pull_requests:write to source-monitor App.

    PR #378 originally widened this manifest, conflating the source-monitor
    identity with fleet orchestration. ADR-036 separates them. The source-monitor
    manifest stays narrow; a separate fleet-orchestrator manifest follows.
    """
    template = (REPO_ROOT / "raw" / "inbox" / "cloneable-template.md").read_text(
        encoding="utf-8"
    )
    # The source-monitor manifest section must not include pull_requests:write
    source_monitor_section_start = template.index("YOUR-REPO-source-monitor")
    # Look at the manifest block immediately after this marker
    source_monitor_block_end = template.index(
        "</form>", source_monitor_section_start
    )
    source_monitor_block = template[source_monitor_section_start:source_monitor_block_end]
    assert '"pull_requests": "write"' not in source_monitor_block, (
        "source-monitor App manifest must NOT include pull_requests:write per ADR-036"
    )

    # A separate fleet-orchestrator section must exist with the wider grants
    assert "fleet-orchestrator" in template, (
        "cloneable-template.md must document the fleet-orchestrator App "
        "provisioning per ADR-036"
    )
    fleet_section_start = template.index("fleet-orchestrator")
    fleet_section_end = template.find("\n### ", fleet_section_start + 1)
    if fleet_section_end == -1:
        fleet_section_end = len(template)
    fleet_section = template[fleet_section_start:fleet_section_end]
    assert '"pull_requests": "write"' in fleet_section, (
        "fleet-orchestrator manifest must include pull_requests:write"
    )
    assert '"issues": "write"' in fleet_section, (
        "fleet-orchestrator manifest must include issues:write"
    )
    assert '"contents": "write"' in fleet_section, (
        "fleet-orchestrator manifest must include contents:write"
    )

