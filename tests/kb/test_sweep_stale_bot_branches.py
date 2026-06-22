"""Tests for scripts/maintenance/sweep_stale_bot_branches.py.

Covers:
- Branch include-regex: parametrized for include and exclude cases.
- Boundary case: jules / google-labs-jules without trailing slash must NOT match.
- Staleness boundary: commit_age_days=13 → NOT flagged; 14 → flagged.
- No-open-PR filter: a stale branch WITH an open PR is NOT swept.
- Exclude-blocklist defense-in-depth: even when a broadened regex erroneously
  matches 'main', the post-filter blocklist still rejects it.

All tests use pytest (ADR-029 — NOT unittest.TestCase).
"""

from __future__ import annotations

import pytest

from scripts.maintenance.sweep_stale_bot_branches import (
    BRANCH_EXCLUDE_BLOCKLIST,
    BRANCH_INCLUDE_REGEX,
    BranchInfo,
    branch_in_exclude_blocklist,
    branch_matches_include,
    filter_branches,
    is_stale,
)


# ---------------------------------------------------------------------------
# Include-regex parametrized tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "branch_name,expected",
    [
        # ── Include cases ────────────────────────────────────────────────
        ("jules/foo", True),
        ("jules/session-abc-123", True),
        ("google-labs-jules/bar", True),
        ("google-labs-jules/long/nested/path", True),
        ("copilot/baz", True),
        ("copilot/port-sweep-stale-bot-branches", True),
        # ── Exclude cases (should NOT match) ────────────────────────────
        ("agents/issue-123", False),
        ("agents/issue-456-feature", False),
        ("slice-8a-foo", False),
        ("fix/whatever", False),
        ("main", False),
        ("fleet-state", False),
        ("gh-pages", False),
        ("feature/my-feature", False),
        ("renovate/some-dep", False),
        # ── Boundary: without trailing slash MUST NOT match ──────────────
        ("jules", False),
        ("google-labs-jules", False),
        ("copilot", False),
    ],
)
def test_branch_matches_include(branch_name: str, expected: bool) -> None:
    """branch_matches_include must respect the narrow include allowlist."""
    result = branch_matches_include(branch_name)
    assert result == expected, (
        f"branch_matches_include({branch_name!r}) = {result}, expected {expected}"
    )


# ---------------------------------------------------------------------------
# Exclude-blocklist tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "branch_name,expected",
    [
        ("main", True),
        ("fleet-state", True),
        ("gh-pages", True),
        ("jules/foo", False),
        ("copilot/bar", False),
        ("google-labs-jules/baz", False),
    ],
)
def test_branch_in_exclude_blocklist(branch_name: str, expected: bool) -> None:
    assert branch_in_exclude_blocklist(branch_name) == expected


def test_exclude_blocklist_is_frozenset() -> None:
    """BRANCH_EXCLUDE_BLOCKLIST must be a frozenset (immutable, O(1) lookup)."""
    assert isinstance(BRANCH_EXCLUDE_BLOCKLIST, frozenset)


def test_exclude_blocklist_defense_in_depth() -> None:
    """Even if a broadened regex erroneously matches 'main', the blocklist rejects it.

    We synthesize a regex that matches everything (including 'main') and confirm
    that filter_branches still excludes 'main' via the post-filter blocklist.
    """
    import re

    broadened_include = re.compile(r"^")  # matches any branch

    # Monkeypatch the module-level constant for this test only
    import scripts.maintenance.sweep_stale_bot_branches as mod

    original = mod.BRANCH_INCLUDE_REGEX
    try:
        mod.BRANCH_INCLUDE_REGEX = broadened_include  # type: ignore[assignment]
        candidates = [
            BranchInfo(name="main", commit_age_days=30, has_open_pr=False),
            BranchInfo(name="fleet-state", commit_age_days=30, has_open_pr=False),
            BranchInfo(name="gh-pages", commit_age_days=30, has_open_pr=False),
            BranchInfo(name="jules/real-branch", commit_age_days=30, has_open_pr=False),
        ]
        swept = filter_branches(candidates, stale_threshold_days=14)
        swept_names = {b.name for b in swept}
        assert "main" not in swept_names, "main must be filtered by blocklist even with broadened regex"
        assert "fleet-state" not in swept_names, "fleet-state must be filtered by blocklist"
        assert "gh-pages" not in swept_names, "gh-pages must be filtered by blocklist"
        assert "jules/real-branch" in swept_names, "jules/real-branch should be swept"
    finally:
        mod.BRANCH_INCLUDE_REGEX = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Staleness boundary tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "commit_age_days,has_open_pr,expected_stale",
    [
        # Boundary: 13 days → NOT flagged
        (13, False, False),
        (13.9, False, False),
        # Boundary: exactly 14 days → flagged
        (14, False, True),
        (14.0, False, True),
        # Older than threshold → flagged
        (15, False, True),
        (20, False, True),
        (100, False, True),
        # Has open PR → NOT flagged regardless of age
        (20, True, False),
        (14, True, False),
        (100, True, False),
    ],
)
def test_is_stale_boundary(commit_age_days: float, has_open_pr: bool, expected_stale: bool) -> None:
    """is_stale must use >= threshold and must require no open PR."""
    branch = BranchInfo(
        name="jules/test-branch",
        commit_age_days=commit_age_days,
        has_open_pr=has_open_pr,
    )
    result = is_stale(branch, stale_threshold_days=14)
    assert result == expected_stale, (
        f"is_stale(age={commit_age_days}, pr={has_open_pr}) = {result}, expected {expected_stale}"
    )


# ---------------------------------------------------------------------------
# No-open-PR filter test
# ---------------------------------------------------------------------------


def test_stale_branch_with_open_pr_not_swept() -> None:
    """A jules/foo branch with commit_age_days=20 AND an open PR is NOT flagged."""
    branch = BranchInfo(name="jules/foo", commit_age_days=20, has_open_pr=True)
    assert not is_stale(branch, stale_threshold_days=14), (
        "Branch with open PR must not be swept regardless of age"
    )
    swept = filter_branches([branch], stale_threshold_days=14)
    assert swept == [], "Branch with open PR must not appear in sweep results"


# ---------------------------------------------------------------------------
# filter_branches integration tests
# ---------------------------------------------------------------------------


def test_filter_branches_returns_only_eligible() -> None:
    """filter_branches must combine include regex, blocklist, staleness, and open-PR checks."""
    candidates = [
        BranchInfo(name="jules/stale-no-pr", commit_age_days=20, has_open_pr=False),
        BranchInfo(name="jules/stale-with-pr", commit_age_days=20, has_open_pr=True),
        BranchInfo(name="jules/fresh-no-pr", commit_age_days=5, has_open_pr=False),
        BranchInfo(name="copilot/stale-no-pr", commit_age_days=30, has_open_pr=False),
        BranchInfo(name="google-labs-jules/stale-no-pr", commit_age_days=15, has_open_pr=False),
        BranchInfo(name="agents/issue-99", commit_age_days=60, has_open_pr=False),
        BranchInfo(name="main", commit_age_days=60, has_open_pr=False),
        BranchInfo(name="feature/something", commit_age_days=60, has_open_pr=False),
    ]
    swept = filter_branches(candidates, stale_threshold_days=14)
    swept_names = {b.name for b in swept}

    assert "jules/stale-no-pr" in swept_names
    assert "copilot/stale-no-pr" in swept_names
    assert "google-labs-jules/stale-no-pr" in swept_names

    assert "jules/stale-with-pr" not in swept_names
    assert "jules/fresh-no-pr" not in swept_names
    assert "agents/issue-99" not in swept_names
    assert "main" not in swept_names
    assert "feature/something" not in swept_names


def test_empty_candidates_returns_empty() -> None:
    assert filter_branches([], stale_threshold_days=14) == []


# ---------------------------------------------------------------------------
# Regex anchoring regression tests
# ---------------------------------------------------------------------------


def test_include_regex_is_anchored_at_start() -> None:
    """The include regex must use ^ anchor to prevent partial-prefix matches."""
    pattern = BRANCH_INCLUDE_REGEX.pattern
    assert pattern.startswith("^"), (
        f"BRANCH_INCLUDE_REGEX must start with ^ to prevent prefix-match bugs; got: {pattern!r}"
    )


def test_include_regex_requires_trailing_slash() -> None:
    """jules / google-labs-jules / copilot without a trailing slash must NOT match."""
    for bare in ("jules", "google-labs-jules", "copilot"):
        assert not branch_matches_include(bare), (
            f"Bare prefix '{bare}' (no trailing slash) must not match include regex"
        )
