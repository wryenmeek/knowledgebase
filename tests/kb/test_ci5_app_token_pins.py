"""Pytest contract tests for CI-5 GitHub App token mint steps (Issue #384).

PR #381's security audit (sec L-5) noted that CI-5
(`.github/workflows/ci-5-github-monitor.yml`) was pinned to
`actions/create-github-app-token@d72941d7…` (v1) which lacks the
`permission-*` token-level narrowing inputs added in v3. Issue #384's PR
(merged as #396) upgraded the pin to `@bcd2ba49…` (v3.2.0) and added
`permission-contents: read` + `permission-metadata: read` to both mint steps.

This module locks the upgrade:
- The v3.2.0 SHA pin must remain stable (a regression to v1's SHA would
  silently lose the entire purpose of #384 because v1 ignores
  `permission-*` inputs)
- Both mint steps must request `permission-contents: read` +
  `permission-metadata: read` and nothing else (a regression that widens
  to `write` would over-grant; a regression that omits one would either
  re-broaden by default OR cause runtime failures)

Lives in a separate pytest module per ADR-029 (legacy
`test_ci5_workflow.py` is `unittest.TestCase`-style and protected by the
test framework ratchet — new tests for CI-5 must be pytest-style).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CI5_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci-5-github-monitor.yml"

# Per ADR-036 § Decision: the fleet workflows and CI-5 both pin
# actions/create-github-app-token to v3.2.0 (bcd2ba49…). Earlier v1/v2 pins
# lack the `permission-*` token-level narrowing inputs.
EXPECTED_ACTION_SHA = "bcd2ba49218906704ab6c1aa796996da409d3eb1"
EXPECTED_ACTION_USES = f"actions/create-github-app-token@{EXPECTED_ACTION_SHA}"

# Permissions kb-source-monitor actually uses at runtime per ADR-012:
# external-source GET requests via scripts/github_monitor/_http.py only.
# The host-repo write path in CI-5's synthesize job uses GITHUB_TOKEN, not
# this App token (see ADR-036 amendment 2026-06-27 + ADR-012 §Authentication).
EXPECTED_TOKEN_PERMISSIONS = {
    "permission-contents": "read",
    "permission-metadata": "read",
}

# Permissions explicitly NOT requested at mint time. A regression that adds
# any of these silently widens the token's blast radius beyond what the
# workflow actually uses.
FORBIDDEN_TOKEN_PERMISSIONS = {
    "permission-pull-requests",
    "permission-issues",
    "permission-actions",
    "permission-workflows",
    "permission-administration",
}

SHA_PIN_REGEX = re.compile(r"actions/create-github-app-token@([0-9a-f]{40})\b")


@pytest.fixture(scope="module")
def ci5_workflow_doc() -> dict:
    return yaml.safe_load(CI5_WORKFLOW_PATH.read_text(encoding="utf-8"))


def _collect_mint_steps(ci5_workflow_doc: dict) -> list[tuple[str, dict]]:
    """Return [(job_name, mint_step)] tuples for every CI-5 step that mints the App token.

    CI-5 has 4 jobs; only 2 mint the App token (`check-drift` and
    `fetch-and-update`). `classify-drift` needs no GitHub auth.
    `synthesize` uses GITHUB_TOKEN for host-repo writes (not the App token).
    """
    mints: list[tuple[str, dict]] = []
    for job_name, job in ci5_workflow_doc.get("jobs", {}).items():
        for step in job.get("steps", []):
            uses = step.get("uses", "")
            if uses.startswith("actions/create-github-app-token@"):
                mints.append((job_name, step))
    return mints


def test_ci5_has_two_app_token_mint_steps(ci5_workflow_doc: dict) -> None:
    """CI-5 mints the App token in exactly 2 jobs (check-drift + fetch-and-update).

    A regression that drops one mint would silently revert that job to
    GITHUB_TOKEN auth (cross-repo API calls would fail with 404 on private
    sources, or rate-limit much faster).
    A regression that adds a third mint would suggest a new code path
    needs an explicit ADR review.
    """
    mints = _collect_mint_steps(ci5_workflow_doc)
    assert len(mints) == 2, (
        f"CI-5 must have exactly 2 App-token mint steps (check-drift + "
        f"fetch-and-update); found {len(mints)}: "
        f"{[(j, s.get('name', '<unnamed>')) for j, s in mints]}"
    )
    job_names = {job_name for job_name, _ in mints}
    assert job_names == {"check-drift", "fetch-and-update"}, (
        f"CI-5 App-token mints must live in check-drift + fetch-and-update jobs only; "
        f"got {sorted(job_names)}"
    )


def test_ci5_mint_steps_pin_create_github_app_token_v3(ci5_workflow_doc: dict) -> None:
    """Every CI-5 mint step MUST pin actions/create-github-app-token@bcd2ba49 (v3.2.0) per Issue #384.

    The v3.2.0 pin is the load-bearing prerequisite for the permission-*
    token-level narrowing inputs. A regression to v1 (d72941d7…) or v2 would
    silently drop the narrowing (v1/v2 ignore permission-* inputs without
    erroring) and defeat the entire purpose of Issue #384.
    """
    mints = _collect_mint_steps(ci5_workflow_doc)
    assert mints, "no CI-5 App-token mint steps found"
    for job_name, mint in mints:
        uses = mint.get("uses", "")
        sha_match = SHA_PIN_REGEX.match(uses)
        assert sha_match, (
            f"CI-5/{job_name}: create-github-app-token must be SHA-pinned by 40-char hex; "
            f"got uses={uses!r}"
        )
        assert uses == EXPECTED_ACTION_USES, (
            f"CI-5/{job_name}: create-github-app-token must pin v3.2.0 "
            f"({EXPECTED_ACTION_SHA}); got {uses!r}. Earlier v1/v2 pins lack "
            f"the permission-* token-level narrowing inputs per ADR-036."
        )


def test_ci5_mint_steps_narrow_to_contents_read_and_metadata_read(
    ci5_workflow_doc: dict,
) -> None:
    """Every CI-5 mint step MUST narrow to permission-contents: read + permission-metadata: read.

    Per Issue #384 + ADR-012: kb-source-monitor's runtime usage is external
    GitHub API GET requests only (see scripts/github_monitor/_http.py). The
    minted token must request only that scope.

    A regression that widens to `write` would over-grant; a regression that
    omits either permission would either re-broaden by default (no narrowing
    → full installation grant) OR cause runtime failures (v3 requires
    permission-metadata: read for installation lookup).
    """
    mints = _collect_mint_steps(ci5_workflow_doc)
    assert mints, "no CI-5 App-token mint steps found"
    for job_name, mint in mints:
        with_block = mint.get("with") or {}
        for key, expected_scope in EXPECTED_TOKEN_PERMISSIONS.items():
            actual_scope = with_block.get(key)
            assert actual_scope == expected_scope, (
                f"CI-5/{job_name}: mint step must request {key}: {expected_scope}; "
                f"got {actual_scope!r}. kb-source-monitor scope per ADR-012 is "
                f"contents:read + metadata:read only."
            )


def test_ci5_mint_steps_do_not_request_forbidden_permissions(
    ci5_workflow_doc: dict,
) -> None:
    """Every CI-5 mint step MUST NOT request pull-requests, issues, actions, workflows, or administration.

    Per ADR-012 (kb-source-monitor scope) + ADR-036 ('Permissions explicitly
    NOT granted'): kb-source-monitor must never mint a token with these
    permissions. Adding one silently widens blast radius beyond the App's
    documented scope and conflates kb-source-monitor with fleet-orchestrator
    (which is the OPPOSITE direction from what ADR-036 enforces).
    """
    mints = _collect_mint_steps(ci5_workflow_doc)
    assert mints, "no CI-5 App-token mint steps found"
    for job_name, mint in mints:
        with_block = mint.get("with") or {}
        for forbidden in FORBIDDEN_TOKEN_PERMISSIONS:
            assert forbidden not in with_block, (
                f"CI-5/{job_name}: mint step must NOT request {forbidden} "
                f"(kb-source-monitor scope per ADR-012 is contents:read + "
                f"metadata:read only; widening conflates with fleet-orchestrator "
                f"per ADR-036 § Decision). "
                f"Got: {forbidden}={with_block.get(forbidden)!r}"
            )


def test_ci5_mint_steps_have_consistent_inputs(ci5_workflow_doc: dict) -> None:
    """All CI-5 mint steps MUST use identical input contracts (no copy-paste drift).

    Symmetric narrowing across the two mint steps prevents a copy-paste
    regression where one mint step gets upgraded/narrowed but the other
    silently retains the old contract. Both jobs use the App token for the
    same runtime purpose (external-source GET via _http.py).
    """
    mints = _collect_mint_steps(ci5_workflow_doc)
    assert len(mints) >= 2, "test requires at least 2 mint steps for comparison"
    # Use first mint as baseline; all others must match its `with:` block.
    _, baseline_mint = mints[0]
    baseline_with = baseline_mint.get("with") or {}
    for job_name, mint in mints[1:]:
        current_with = mint.get("with") or {}
        assert current_with == baseline_with, (
            f"CI-5/{job_name}: mint step `with:` block must match the other CI-5 mint "
            f"step exactly (both jobs use the same App token for the same purpose). "
            f"Baseline: {baseline_with!r}; got: {current_with!r}"
        )
