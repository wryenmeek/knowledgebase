"""Tests for scripts/validation/check_commit_scope.py.

Covers gate B (sensitive-paths acknowledgement), gate C (deletion-ratio guard),
the both-gates-fire case (no short-circuit), and the Scribe regression.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.validation.check_commit_scope import (
    GATE_B_TOKENS,
    GATE_C_NET_DELETION_THRESHOLD,
    check_gate_b,
    check_gate_c,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_reverts(_value: str) -> bool:
    """Mock validator that always approves the Reverts: reference."""
    return True


def _invalid_reverts(_value: str) -> bool:
    """Mock validator that always rejects the Reverts: reference."""
    return False


# ---------------------------------------------------------------------------
# Gate B — sensitive-paths acknowledgement
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "title, body, changed_paths, expected_pass",
    [
        # ------------------------------------------------------------------ #
        # Positive cases (gate fires → FAIL)                                 #
        # ------------------------------------------------------------------ #
        pytest.param(
            "fix: clean up unused imports",
            "",
            ["wiki/foo.md"],
            False,
            id="gate_b_no_token_in_title_wiki_path_fails",
        ),
        pytest.param(
            # ``schema`` token is present but maps to ``schema/``, not ``wiki/``.
            "Adopt schema v2 for foo",
            "",
            ["wiki/bar.md"],
            False,
            id="gate_b_sibling_token_doesnt_satisfy_different_surface_fails",
        ),
        pytest.param(
            # ``wikipedia`` contains ``wiki`` as a substring but is NOT a
            # word-boundary match — the gate must reject substring-only hits.
            "wikipedia integration",
            "",
            ["wiki/baz.md"],
            False,
            id="gate_b_substring_without_word_boundary_rejected",
        ),
        # ------------------------------------------------------------------ #
        # Negative cases (gate does not fire → PASS)                         #
        # ------------------------------------------------------------------ #
        pytest.param(
            "wiki: archive obsolete page",
            "",
            ["wiki/page.md"],
            True,
            id="gate_b_wiki_token_in_title_passes",
        ),
        pytest.param(
            # Body first line has the token; title does not.
            "chore: routine cleanup",
            "Refactors wiki/\nMore detail here.",
            ["wiki/page.md"],
            True,
            id="gate_b_wiki_token_in_body_first_line_passes",
        ),
        # Non-sensitive path: gate B is not triggered.
        pytest.param(
            "fix: some random change",
            "",
            ["src/foo.py"],
            True,
            id="gate_b_non_sensitive_path_not_flagged",
        ),
        # Empty diff: nothing touched → gate does not fire.
        pytest.param(
            "chore: empty diff",
            "",
            [],
            True,
            id="gate_b_empty_diff_passes",
        ),
    ],
)
def test_gate_b(
    title: str,
    body: str,
    changed_paths: list[str],
    expected_pass: bool,
) -> None:
    passed, errors = check_gate_b(title, body, changed_paths)
    assert passed is expected_pass, (
        f"Expected gate B passed={expected_pass} but got {passed}. errors={errors}"
    )


@pytest.mark.parametrize(
    "title, changed_paths, expected_pass",
    [
        ("ADRs update", ["docs/decisions/ADR-042-foo.md"], True),
        ("adr: revise governance model", ["docs/decisions/ADR-042-foo.md"], True),
        ("update copilot config", [".github/copilot-instructions.md"], True),
        ("fix workflows", [".github/workflows/ci.yml"], True),
        ("bump contracts version", ["scripts/kb/contracts.py"], True),
        ("refactor write_utils helpers", ["scripts/kb/write_utils.py"], True),
        ("update AGENTS matrix", ["AGENTS.md"], True),
        ("schema migration", ["schema/page-template.md"], True),
        ("update spec", ["raw/processed/SPEC.md"], True),
        ("fix pre-commit hook", [".pre-commit-config.yaml"], True),
        # Gate B / U6 finding: Jules persona PR learning loop memory paths.
        ("jules-memory: append bolt learning entry", [".jules/bolt.md"], True),
        ("jules-memory: append sentinel learning entry", [".jules/sentinel.md"], True),
        # Missing token: neither path is acknowledged.
        ("fix: routine cleanup", [".jules/bolt.md"], False),
        ("fix: routine cleanup", [".jules/sentinel.md"], False),
        # ``Wikipedia`` must NOT match ``wiki`` (word-boundary enforcement).
        ("Wikipedia article", ["wiki/page.md"], False),
        # ``Adrian`` must NOT match ``adr`` (word-boundary enforcement).
        ("Adrian's fix", ["docs/decisions/ADR-001.md"], False),
    ],
)
def test_gate_b_token_coverage(
    title: str,
    changed_paths: list[str],
    expected_pass: bool,
) -> None:
    passed, errors = check_gate_b(title, "", changed_paths)
    assert passed is expected_pass, (
        f"title={title!r}, paths={changed_paths!r}: "
        f"expected passed={expected_pass} but got {passed}. errors={errors}"
    )


def test_gate_b_token_set_is_pinned() -> None:
    """The gate B token set must match the spec-defined enumeration exactly."""
    expected = frozenset({
        "wiki",
        "schema",
        "adr",
        "adrs",
        "agents",
        "copilot",
        "contracts",
        "write_utils",
        "spec",
        "workflows",
        "pre-commit",
        "jules",
    })
    assert GATE_B_TOKENS == expected, (
        f"GATE_B_TOKENS drifted from spec. "
        f"Extra: {GATE_B_TOKENS - expected}, Missing: {expected - GATE_B_TOKENS}"
    )


def test_gate_b_jules_memory_paths_repro() -> None:
    """Regression for the PR #547 review finding: proposal-mode PRs modify
    `.jules/bolt.md`/`.jules/sentinel.md` (both in SENSITIVE_PATHS), but
    before this fix neither path had a `_PATH_TO_TOKENS` entry nor a Jules
    token in `GATE_B_TOKENS`, so `check_gate_b` always failed for these PRs
    with an empty "Add one of" list — blocking every generated learning
    proposal's normal CI/merge path. Reproduces the exact repro from the
    review comment.
    """
    passed, errors = check_gate_b(
        "jules-memory: append bolt learning entry", "", [".jules/bolt.md"]
    )
    assert passed is True, f"expected gate B to pass; got errors={errors}"


# ---------------------------------------------------------------------------
# Gate C — deletion-ratio guard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "insertions, deletions, body, last_commit, reverts_validator, expected_pass",
    [
        # ------------------------------------------------------------------ #
        # Boundary / threshold cases                                          #
        # ------------------------------------------------------------------ #
        pytest.param(
            0, 50, "", "", None,
            True,
            id="gate_c_boundary_50_strict_gt_passes",
        ),
        pytest.param(
            0, 51, "", "", None,
            False,
            id="gate_c_boundary_51_no_trailer_fails",
        ),
        # Insertions offset: net 51 still fails
        pytest.param(
            49, 100, "", "", None,
            False,
            id="gate_c_net_51_after_offset_fails",
        ),
        # ------------------------------------------------------------------ #
        # Reverts: trailer in PR body last paragraph                          #
        # ------------------------------------------------------------------ #
        pytest.param(
            0, 100,
            "Reverts: wryenmeek/knowledgebase#1",
            "",
            _valid_reverts,
            True,
            id="gate_c_valid_reverts_body_last_para_passes",
        ),
        pytest.param(
            0, 100,
            "Reverts: wryenmeek/knowledgebase#99999",
            "",
            _invalid_reverts,
            False,
            id="gate_c_nonexistent_issue_fails",
        ),
        pytest.param(
            0, 100,
            f"Reverts: {'a' * 40}",
            "",
            _invalid_reverts,
            False,
            id="gate_c_sha_not_on_main_fails",
        ),
        pytest.param(
            0, 100,
            "Some description\n\nReverts: wryenmeek/knowledgebase#1\n\nFinal paragraph.",
            "",
            _valid_reverts,
            False,
            id="gate_c_reverts_buried_mid_body_fails",
        ),
        # ------------------------------------------------------------------ #
        # Cleanup: trailer                                                    #
        # ------------------------------------------------------------------ #
        pytest.param(
            0, 100, "",
            "feat: cleanup\n\nCleanup: dead-code removal, 200 lines",
            None,
            True,
            id="gate_c_cleanup_in_last_commit_footer_passes",
        ),
        pytest.param(
            0, 100, "", "feat: cleanup\n\nCleanup: x",
            None,
            False,
            id="gate_c_cleanup_reason_too_short_fails",
        ),
        pytest.param(
            0, 100, "", "feat: cleanup\n\nCleanup: exactly10c",
            None,
            True,
            id="gate_c_cleanup_exactly_10_chars_passes",
        ),
        # ------------------------------------------------------------------ #
        # Trailer location: last commit message                               #
        # ------------------------------------------------------------------ #
        pytest.param(
            0, 100, "",
            "feat: refactor\n\nReverts: #123",
            _valid_reverts,
            True,
            id="gate_c_valid_reverts_last_commit_message_passes",
        ),
        # ------------------------------------------------------------------ #
        # Trailer location: PR body last paragraph                            #
        # ------------------------------------------------------------------ #
        pytest.param(
            0, 100, "Reverts: #456", "",
            _valid_reverts,
            True,
            id="gate_c_valid_reverts_body_only_passes",
        ),
        # ------------------------------------------------------------------ #
        # Cleanup: in PR body last paragraph                                  #
        # ------------------------------------------------------------------ #
        pytest.param(
            0, 100,
            "Some description\n\nCleanup: dead-code removal, 200 lines",
            "",
            None,
            True,
            id="gate_c_cleanup_in_body_last_paragraph_passes",
        ),
    ],
)
def test_gate_c(
    insertions: int,
    deletions: int,
    body: str,
    last_commit: str,
    reverts_validator,
    expected_pass: bool,
) -> None:
    passed, errors = check_gate_c(
        insertions, deletions, body, last_commit,
        reverts_validator=reverts_validator,
    )
    assert passed is expected_pass, (
        f"Expected gate C passed={expected_pass} but got {passed}. errors={errors}"
    )


def test_gate_c_threshold_constant_is_pinned() -> None:
    """The net-deletion threshold must be exactly 50 (strict ``>``)."""
    assert GATE_C_NET_DELETION_THRESHOLD == 50


# ---------------------------------------------------------------------------
# Both gates fire independently (no short-circuit)
# ---------------------------------------------------------------------------

def test_both_gates_fire_independently() -> None:
    """When both gates fail, both produce error messages — no short-circuit."""
    # Gate B: wiki touched, no wiki token in title or body.
    b_passed, b_errors = check_gate_b(
        "fix: tiny invisible change",
        "",
        ["wiki/important.md"],
    )
    # Gate C: net deletion > 50, no trailer.
    c_passed, c_errors = check_gate_c(0, 200, "", "")

    assert b_passed is False, "Gate B should fire"
    assert c_passed is False, "Gate C should fire"
    assert len(b_errors) >= 1, "Gate B should produce an error message"
    assert len(c_errors) >= 1, "Gate C should produce an error message"


# ---------------------------------------------------------------------------
# Scribe regression test
# ---------------------------------------------------------------------------

def test_scribe_regression_both_gates_fire() -> None:
    """Regression: the Scribe-style silent-revert pattern must fail both gates.

    The canonical attack:
    - Benign title with no sensitive-surface token.
    - ``Reverts:`` mention buried mid-body (not last paragraph → gate C
      does not consider it a valid trailer).
    - Massive net deletion from ``wiki/``.

    Both gate B and gate C must fire.
    """
    title = "bolt: optimize set conversion"
    body = (
        "Optimizing for performance.\n"
        "\n"
        "Reverts: wryenmeek/knowledgebase#1\n"
        "\n"
        "This final paragraph has no trailer."
    )
    changed_paths = [f"wiki/strategies/doc-{i}.md" for i in range(10)]
    insertions, deletions = 0, 2474

    b_passed, b_errors = check_gate_b(title, body, changed_paths)
    c_passed, c_errors = check_gate_c(
        insertions,
        deletions,
        body,
        "",
        reverts_validator=_valid_reverts,  # validator would approve #1 if it were valid
    )

    assert b_passed is False, (
        f"Gate B should fail: title has no wiki/schema/adr/etc token. errors={b_errors}"
    )
    assert c_passed is False, (
        f"Gate C should fail: Reverts: is mid-body, not last paragraph. errors={c_errors}"
    )
