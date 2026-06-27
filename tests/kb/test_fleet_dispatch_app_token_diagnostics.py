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
- Per-mint `permission-*` token-level least privilege (ADR-036 § Decision)
- The fleet-orchestrator App manifest's load-bearing exclusions (no workflows:write etc.)
- The negative scope (fleet-plan.yml, fleet-submit-prs.yml stay on GITHUB_TOKEN)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "fleet-dispatch.yml"
FLEET_MERGE_PATH = REPO_ROOT / ".github" / "workflows" / "fleet-merge.yml"
FLEET_AFTER_MERGE_PATH = (
    REPO_ROOT / ".github" / "workflows" / "fleet-dispatch-after-merge.yml"
)
FLEET_PLAN_PATH = REPO_ROOT / ".github" / "workflows" / "fleet-plan.yml"
FLEET_SUBMIT_PRS_PATH = REPO_ROOT / ".github" / "workflows" / "fleet-submit-prs.yml"
RUNBOOK_PATH = REPO_ROOT / "docs" / "mvp-runbook.md"
ADR_036_PATH = (
    REPO_ROOT / "docs" / "decisions" / "ADR-036-fleet-orchestrator-github-app-identity.md"
)
CLONEABLE_TEMPLATE_PATH = REPO_ROOT / "raw" / "inbox" / "cloneable-template.md"

# Exact operator-grep target — the runbook tells operators to grep for this
# string after Phase 2a to confirm the App token path activated. If the
# workflow emits a different string, the runbook silently lies.
APP_TOKEN_SUCCESS_LINE = (
    "✅ Issue #310: using fleet-orchestrator App installation token for planning PR auto-merge."
)

# Fleet workflows that MUST migrate to FLEET_APP_* per ADR-036.
FLEET_WRITE_WORKFLOWS = {
    "fleet-dispatch.yml": WORKFLOW_PATH,
    "fleet-merge.yml": FLEET_MERGE_PATH,
    "fleet-dispatch-after-merge.yml": FLEET_AFTER_MERGE_PATH,
}

# Fleet workflows that MUST stay on GITHUB_TOKEN per ADR-036 § Decision.
FLEET_GITHUB_TOKEN_WORKFLOWS = {
    "fleet-plan.yml": FLEET_PLAN_PATH,
    "fleet-submit-prs.yml": FLEET_SUBMIT_PRS_PATH,
}

# Regex catches any `secrets.GH_APP_*` reference (with or without `${{ ... }}`).
GH_APP_REGEX = re.compile(r"secrets\.GH_APP_(ID|PRIVATE_KEY)\b")
SHA_PIN_REGEX = re.compile(r"actions/create-github-app-token@([0-9a-f]{40})\b")


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
def cloneable_template_text() -> str:
    return CLONEABLE_TEMPLATE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def workflow_yaml() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fleet_merge_yaml() -> dict:
    return yaml.safe_load(FLEET_MERGE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fleet_after_merge_yaml() -> dict:
    return yaml.safe_load(FLEET_AFTER_MERGE_PATH.read_text(encoding="utf-8"))


def _step_run_text(yaml_doc: dict, job_name: str, step_name: str) -> str:
    """Return a step's run-block text by job + step name (YAML-safe vs string slicing).

    Robust to YAML reformatting because we go through the parsed structure.
    """
    job = yaml_doc["jobs"][job_name]
    for step in job["steps"]:
        if step.get("name") == step_name:
            return step.get("run", "")
    raise AssertionError(f"step {step_name!r} not found in job {job_name!r}")


@pytest.fixture(scope="module")
def auto_merge_step_text(workflow_yaml: dict) -> str:
    """YAML-anchored isolation of the auto-merge step (robust to indentation drift)."""
    return _step_run_text(workflow_yaml, "dispatch", "Queue auto-merge of planning PR")


# ── ADR-036 multi-workflow coverage ──────────────────────────────────────────


@pytest.mark.parametrize("workflow_name,workflow_path", FLEET_WRITE_WORKFLOWS.items())
def test_fleet_write_workflows_use_fleet_app_secrets_not_gh_app(
    workflow_name: str, workflow_path: Path
) -> None:
    """All 3 fleet WRITE workflows must use FLEET_APP_* secrets per ADR-036 — not GH_APP_*.

    Addresses test-engineer F1: the previous version of this test only checked
    fleet-dispatch.yml. A copy-paste regression that re-introduces
    `${{ secrets.GH_APP_ID }}` into fleet-merge.yml or fleet-dispatch-after-merge.yml
    would have passed the old test. This parameterized version closes that hole.

    Uses regex on the raw YAML text to defeat partial regressions like
    `secrets.GH_APP_PRIVATE_KEY` slipping in without `secrets.GH_APP_ID`.
    """
    workflow_text = workflow_path.read_text(encoding="utf-8")
    assert "secrets.FLEET_APP_ID" in workflow_text, (
        f"{workflow_name} must reference secrets.FLEET_APP_ID per ADR-036"
    )
    assert "secrets.FLEET_APP_PRIVATE_KEY" in workflow_text, (
        f"{workflow_name} must reference secrets.FLEET_APP_PRIVATE_KEY per ADR-036"
    )
    matches = GH_APP_REGEX.findall(workflow_text)
    assert not matches, (
        f"{workflow_name} must NOT reference secrets.GH_APP_* — that is "
        f"kb-source-monitor (read-only source ingestion App per ADR-036). "
        f"Found: {matches!r}"
    )


@pytest.mark.parametrize("workflow_name,workflow_path", FLEET_GITHUB_TOKEN_WORKFLOWS.items())
def test_fleet_readonly_workflows_stay_on_github_token(
    workflow_name: str, workflow_path: Path
) -> None:
    """Per ADR-036 § Decision: fleet-plan and fleet-submit-prs MUST stay on GITHUB_TOKEN.

    Addresses test-engineer F13: ADR-036 explicitly says wiki/framework workflows
    don't migrate because they only OPEN PRs (HITL-reviewed before merge, no Layer 6
    hit). fleet-plan also only opens a planning PR. If a future change accidentally
    copies the App-token block into these workflows, the ADR-036 scope contract
    silently widens.
    """
    workflow_text = workflow_path.read_text(encoding="utf-8")
    assert "secrets.FLEET_APP_ID" not in workflow_text, (
        f"{workflow_name} must NOT reference FLEET_APP_* per ADR-036 § Decision "
        f"(only Phase 2a/2b/3 fleet-write workflows use the App token)"
    )
    assert "secrets.FLEET_APP_PRIVATE_KEY" not in workflow_text, (
        f"{workflow_name} must NOT reference FLEET_APP_PRIVATE_KEY per ADR-036"
    )
    assert "actions/create-github-app-token" not in workflow_text, (
        f"{workflow_name} must NOT mint a fleet App token — it only opens HITL-reviewed "
        f"PRs and stays on the default GITHUB_TOKEN per ADR-036 § Decision"
    )


# ── ADR-036: per-workflow App-token contract (YAML-parsed, robust) ───────────


def _collect_app_token_steps(yaml_doc: dict, workflow_name: str) -> list[tuple[str, dict, dict]]:
    """Return [(job_name, detect_step, mint_step)] tuples for every job that mints an App token.

    Iterates ALL jobs so multi-job workflows (fleet-merge.yml has both
    `merge-on-ci-pass` and `manual-sweep`) are not silently missed. Addresses
    test-engineer F2.
    """
    pairs: list[tuple[str, dict, dict]] = []
    for job_name, job in yaml_doc.get("jobs", {}).items():
        steps = job.get("steps", [])
        detect = next(
            (s for s in steps if s.get("id") == "app-token-inputs"), None
        )
        mint = next((s for s in steps if s.get("id") == "app-token"), None)
        if detect is not None or mint is not None:
            assert (
                detect is not None and mint is not None
            ), (
                f"{workflow_name}/{job_name}: detect step (id: app-token-inputs) "
                f"and mint step (id: app-token) must both exist or neither — "
                f"one without the other leaves dangling references."
            )
            pairs.append((job_name, detect, mint))
    return pairs


@pytest.mark.parametrize("workflow_name,workflow_path", FLEET_WRITE_WORKFLOWS.items())
def test_each_fleet_write_workflow_mints_token_per_job(
    workflow_name: str, workflow_path: Path
) -> None:
    """Every job that performs a write must mint the App token at the job level.

    Addresses test-engineer F2: fleet-merge.yml has TWO jobs (merge-on-ci-pass +
    manual-sweep), each performing writes. Both must mint the token; a regression
    that drops the step from one job would have passed the old substring-on-whole-file
    test. This iterates per job.
    """
    yaml_doc = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    pairs = _collect_app_token_steps(yaml_doc, workflow_name)
    expected_min_jobs = {
        "fleet-dispatch.yml": 1,
        "fleet-merge.yml": 2,
        "fleet-dispatch-after-merge.yml": 1,
    }
    assert len(pairs) >= expected_min_jobs[workflow_name], (
        f"{workflow_name} must mint App token in at least "
        f"{expected_min_jobs[workflow_name]} job(s); found {len(pairs)}"
    )
    for job_name, detect, mint in pairs:
        # Detect step: secrets bound via step-scoped env (security: not job-scoped)
        env = detect.get("env") or {}
        assert env.get("FLEET_APP_ID") == "${{ secrets.FLEET_APP_ID }}", (
            f"{workflow_name}/{job_name}: detect step must bind FLEET_APP_ID step-scoped"
        )
        assert env.get("FLEET_APP_PRIVATE_KEY") == "${{ secrets.FLEET_APP_PRIVATE_KEY }}", (
            f"{workflow_name}/{job_name}: detect step must bind FLEET_APP_PRIVATE_KEY step-scoped"
        )

        # Mint step: SHA-pinned action; FLEET_APP_* in with:; continue-on-error
        uses = mint.get("uses", "")
        sha_match = SHA_PIN_REGEX.match(uses)
        assert sha_match, (
            f"{workflow_name}/{job_name}: create-github-app-token must be pinned by 40-char hex SHA; "
            f"got uses={uses!r}"
        )
        assert mint.get("continue-on-error") is True, (
            f"{workflow_name}/{job_name}: mint step must continue-on-error: true so the "
            f"|| GITHUB_TOKEN fallback can engage"
        )
        with_block = mint.get("with") or {}
        assert with_block.get("app-id") == "${{ secrets.FLEET_APP_ID }}"
        assert with_block.get("private-key") == "${{ secrets.FLEET_APP_PRIVATE_KEY }}"


# ── ADR-036: token-level least privilege (permission-* contracts) ────────────

# Per ADR-036 § Decision: each workflow mints only the permissions it uses.
EXPECTED_TOKEN_PERMISSIONS = {
    "fleet-dispatch.yml": {
        # Phase 2a: merge the planning PR
        "dispatch": {"permission-contents": "write", "permission-pull-requests": "write"},
    },
    "fleet-merge.yml": {
        # Phase 3 event-driven and manual: merge per-task PRs
        "merge-on-ci-pass": {"permission-contents": "write", "permission-pull-requests": "write"},
        "manual-sweep": {"permission-contents": "write", "permission-pull-requests": "write"},
    },
    "fleet-dispatch-after-merge.yml": {
        # Phase 2b: dispatch sessions + post per-task tracker comments on issues
        # NOTE: permission-pull-requests intentionally absent (sec L-2 — Phase 2b
        # script only calls issues.createComment).
        "dispatch": {"permission-contents": "write", "permission-issues": "write"},
    },
}


@pytest.mark.parametrize("workflow_name,workflow_path", FLEET_WRITE_WORKFLOWS.items())
def test_app_token_permissions_match_adr_036_per_workflow(
    workflow_name: str, workflow_path: Path
) -> None:
    """Each App-token mint must request exactly the permissions ADR-036 documents.

    Addresses sec L-1 and test-engineer F6. Token-level least privilege: even if
    the App's INSTALLATION grants {contents,pull_requests,issues,metadata}:write,
    each minted token narrows to the workflow's actual usage. A regression that
    drops `permission-issues: write` from Phase 2b silently re-opens Issue #311's
    `Resource not accessible by integration` failure; a regression that adds
    `permission-issues: write` to Phase 2a/3 widens token blast radius
    unnecessarily.
    """
    yaml_doc = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    expected_per_job = EXPECTED_TOKEN_PERMISSIONS[workflow_name]

    for job_name, expected_perms in expected_per_job.items():
        job = yaml_doc["jobs"][job_name]
        mint = next((s for s in job["steps"] if s.get("id") == "app-token"), None)
        assert mint is not None, f"{workflow_name}/{job_name}: missing mint step"
        with_block = mint.get("with") or {}

        # Positive: every expected permission is present with the expected scope
        for key, scope in expected_perms.items():
            assert with_block.get(key) == scope, (
                f"{workflow_name}/{job_name}: mint step must request {key}: {scope}; "
                f"got {with_block.get(key)!r}"
            )

        # Negative: forbidden permissions must NOT be requested
        forbidden = {"permission-workflows", "permission-actions", "permission-administration"}
        for key in forbidden:
            assert key not in with_block, (
                f"{workflow_name}/{job_name}: mint step must NOT request {key} "
                f"(ADR-036 'Permissions explicitly NOT granted' subsection)"
            )

        # Job-specific extra constraint: Phase 2a/3 must NOT request issues:write
        if expected_perms.get("permission-issues") is None:
            assert "permission-issues" not in with_block, (
                f"{workflow_name}/{job_name}: mint step must NOT request issues:write — "
                f"only Phase 2b (which posts tracker comments) needs it per ADR-036"
            )


# ── Existing fleet-dispatch contract (Phase 2a only) — kept for completeness ─


def test_fleet_dispatch_app_token_created_env_binds_to_token_not_outcome(
    workflow_yaml: dict,
) -> None:
    """APP_TOKEN_CREATED must bind to outputs.token != '' — NOT outputs.outcome.

    Addresses test-engineer F9: `continue-on-error: true` masks failures so
    `steps.app-token.outcome` is 'success' even when 422 was returned and no
    token was minted. The load-bearing detector is the empty-string check on
    `outputs.token`. A regression to outcome/conclusion silently breaks the
    3-branch warning.
    """
    auto_merge = next(
        s for s in workflow_yaml["jobs"]["dispatch"]["steps"]
        if s.get("name") == "Queue auto-merge of planning PR"
    )
    env = auto_merge.get("env") or {}
    assert env.get("APP_TOKEN_CREATED") == "${{ steps.app-token.outputs.token != '' }}", (
        "APP_TOKEN_CREATED must bind to outputs.token != '' (the only reliable "
        "detector under continue-on-error: true). Got: "
        f"{env.get('APP_TOKEN_CREATED')!r}"
    )
    assert env.get("APP_TOKEN_AVAILABLE") == "${{ steps.app-token-inputs.outputs.available }}"


def test_phase_2a_warning_enumerates_all_three_permissions(auto_merge_step_text: str) -> None:
    """Phase 2a 422-warning must enumerate all 3 App permissions per ADR-036.

    Addresses test-engineer F5: a regression that narrows the warning to just
    `contents:write` (dropping pull-requests:write or issues:write) would have
    passed the old "names a permission" test. Issue #311 is resolved specifically
    by including issues:write; lock the enumeration.
    """
    for permission in ("contents:write", "pull-requests:write", "issues:write"):
        assert permission in auto_merge_step_text, (
            f"Phase 2a 422-warning must explicitly mention {permission} so the "
            f"operator knows the full set of permissions to grant. Without the "
            f"enumeration, a regression that drops issues:write silently "
            f"re-opens Issue #311."
        )


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
    assert "422" in auto_merge_step_text
    assert "permissions requested are not granted" in auto_merge_step_text
    assert "Settings → Developer settings → GitHub Apps" in auto_merge_step_text
    assert "re-accept" in auto_merge_step_text


def test_phase_2a_secrets_absent_warning_is_distinct(auto_merge_step_text: str) -> None:
    """The 'secrets absent' warning must be a separate title from 'creation failed'."""
    assert (
        "Issue #310 fleet-orchestrator App secrets not configured"
        in auto_merge_step_text
    )
    assert (
        "Issue #310 fleet-orchestrator App token creation failed"
        in auto_merge_step_text
    )


def test_phase_2a_success_line_matches_runbook_grep_target(
    auto_merge_step_text: str, runbook_text: str
) -> None:
    """The success line must match verbatim between the workflow and the runbook."""
    assert APP_TOKEN_SUCCESS_LINE in auto_merge_step_text
    assert APP_TOKEN_SUCCESS_LINE in runbook_text


def test_runbook_documents_app_permission_requirements(runbook_text: str) -> None:
    """The mvp-runbook's Layer 6 section must spell out the App permission contract."""
    assert "App permission requirements" in runbook_text
    assert "Contents: Read & write" in runbook_text
    assert "Pull requests: Read & write" in runbook_text
    assert "Diagnostic checklist when warning appears" in runbook_text
    assert "422" in runbook_text
    assert "401" in runbook_text
    assert "404" in runbook_text


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


def test_adr_036_documents_permissions_not_granted(adr_036_text: str) -> None:
    """ADR-036 must explicitly enumerate permissions NOT granted (load-bearing exclusions).

    Addresses sec L-3: the App's lack of `workflows: write` is the load-bearing
    defense against the Jules-PR-bootstraps-workflow attack. The ADR must
    document the safeguard so a future contributor cannot remove it without
    consciously amending the ADR.
    """
    assert "Permissions explicitly NOT granted" in adr_036_text, (
        "ADR-036 must have a 'Permissions explicitly NOT granted' subsection "
        "documenting load-bearing exclusions"
    )
    for forbidden in ("workflows", "actions", "administration"):
        assert forbidden in adr_036_text, (
            f"ADR-036 must explicitly call out `{forbidden}` as a permission "
            f"NOT granted — without this, the exclusion is enforced only by "
            f"the manifest"
        )


def test_adr_036_documents_multi_repo_pem_coupling(adr_036_text: str) -> None:
    """ADR-036 Negative consequences must honestly note the shared-PEM coupling.

    Addresses sec M-1: although installation tokens are per-installation-scoped,
    the App's private key authenticates the App globally. Document that an
    exfil event in any one of the 4 fleet repos couples blast radius across all 4.
    """
    # Look for the negative-consequences disclosure (case-insensitive on the
    # specific risk wording).
    text_lower = adr_036_text.lower()
    assert (
        "pem" in text_lower or "private key" in text_lower
    ), "ADR-036 must mention the PEM/private-key as the global auth credential"
    assert (
        "couples" in text_lower
        or "coupling" in text_lower
        or "blast radius" in text_lower
    ), "ADR-036 Negative consequences must describe the multi-repo coupling risk"


def test_adr_036_indexed_in_decisions_readme() -> None:
    """ADR-036 must appear in the decisions README index per documentation cascade."""
    readme = (REPO_ROOT / "docs" / "decisions" / "README.md").read_text(encoding="utf-8")
    assert "ADR-036" in readme
    assert "Fleet orchestrator GitHub App identity" in readme


# ── cloneable-template manifest invariants (test-engineer F7+F8, sec M-2) ────


def _slice_source_monitor_manifest(template: str) -> str:
    """Return the source-monitor App manifest block (anchored on the JSON literal)."""
    # Anchor on the manifest's name field — stable across doc reorganization.
    start = template.index('"name": "YOUR-REPO-source-monitor"')
    end = template.index("</form>", start)
    return template[start:end]


def _slice_fleet_orchestrator_manifest(template: str) -> str:
    """Return the fleet-orchestrator App manifest block (anchored on the JSON literal).

    Addresses test-engineer F7: the previous version anchored on the prose
    first-mention of `fleet-orchestrator`, which broke under doc reorganization.
    This version anchors on the manifest's JSON `"name"` field — a stable marker
    that only appears once in the document and identifies the manifest unambiguously.

    Per #383 (sec L-4): the slug `fleet-orchestrator` is globally unique across
    GitHub. The manifest now ships with the placeholder `YOUR-OWNER-fleet-orchestrator`
    so downstream forks substitute their owner prefix without slug collision.
    """
    start = template.index('"name": "YOUR-OWNER-fleet-orchestrator"')
    end = template.index("</form>", start)
    return template[start:end]


def test_cloneable_template_source_monitor_manifest_is_narrow(
    cloneable_template_text: str,
) -> None:
    """source-monitor App manifest must stay narrow per ADR-036.

    Addresses test-engineer F8 (positive scope assertions): tests both the
    upper bound (no pull_requests:write, no issues:write, no workflows:write)
    AND the lower bound (contents:write + metadata:read remain — required for
    CI-5 ingestion per ADR-012).
    """
    block = _slice_source_monitor_manifest(cloneable_template_text)

    # Upper bound: forbidden permissions
    assert '"pull_requests"' not in block, (
        "source-monitor manifest must NOT include pull_requests permission per ADR-036"
    )
    assert '"issues"' not in block, (
        "source-monitor manifest must NOT include issues permission per ADR-036"
    )
    assert '"workflows"' not in block, (
        "source-monitor manifest must NOT include workflows permission — would "
        "bootstrap arbitrary workflow modification"
    )

    # Lower bound: required scopes still present (ADR-012)
    assert '"contents": "write"' in block, (
        "source-monitor manifest must still grant contents:write (ADR-012 CI-5 fetch-and-update)"
    )
    assert '"metadata": "read"' in block, (
        "source-monitor manifest must still grant metadata:read"
    )


def test_cloneable_template_fleet_orchestrator_manifest_matches_adr_036(
    cloneable_template_text: str,
) -> None:
    """fleet-orchestrator manifest must match the permission table in ADR-036.

    Addresses sec M-2: the manifest is what the operator actually submits to
    GitHub. If it drifts from ADR-036's permission table, the deployment
    doesn't match the documented decision.
    """
    block = _slice_fleet_orchestrator_manifest(cloneable_template_text)

    # Placeholder name pattern (per #383 / sec L-4): the slug is globally
    # unique on GitHub, so the manifest ships with an owner-prefix placeholder
    # that downstream forks substitute before submission.
    assert '"name": "YOUR-OWNER-fleet-orchestrator"' in block, (
        "manifest must use the YOUR-OWNER-fleet-orchestrator placeholder so "
        "downstream forks substitute their owner prefix (per #383 / sec L-4)"
    )

    # Positive: every permission ADR-036 grants
    assert '"contents": "write"' in block, "manifest must grant contents:write"
    assert '"pull_requests": "write"' in block, "manifest must grant pull_requests:write"
    assert '"issues": "write"' in block, "manifest must grant issues:write"
    assert '"metadata": "read"' in block, "manifest must grant metadata:read"

    # Negative: permissions explicitly NOT granted per ADR-036 § Decision
    assert '"workflows"' not in block, (
        "fleet-orchestrator manifest must NOT grant workflows — load-bearing "
        "defense against Jules-PR-bootstraps-workflow attack class (ADR-036 § Decision)"
    )
    assert '"actions"' not in block, (
        "fleet-orchestrator manifest must NOT grant actions — would let a "
        "compromised token cancel CI runs (ADR-036)"
    )
    assert '"administration"' not in block, (
        "fleet-orchestrator manifest must NOT grant administration — would let "
        "the App rotate collaborators / branch protection (ADR-036)"
    )
    assert '"members"' not in block, (
        "fleet-orchestrator manifest must NOT grant members — would let the App "
        "escalate org membership (ADR-036)"
    )


def test_cloneable_template_fleet_orchestrator_has_no_webhooks(
    cloneable_template_text: str,
) -> None:
    """fleet-orchestrator manifest must declare no webhooks and no event subscriptions.

    Addresses sec M-2: ADR-036 says "no webhooks; the App is consumed
    server-to-server via actions/create-github-app-token only." If a future
    contributor turns on webhooks (e.g., for an event-driven sidecar), the App
    becomes a runtime ingress vector. Lock both invariants.
    """
    block = _slice_fleet_orchestrator_manifest(cloneable_template_text)
    assert '"hook_attributes": {"active": false}' in block, (
        "manifest must declare hook_attributes.active: false (no webhooks)"
    )
    assert '"default_events": []' in block, (
        "manifest must declare default_events: [] (no event subscriptions)"
    )


