"""Adversarial composition tests for the Locality 4 ratchet hook.

Slice 5b's trailer-budget hook is not present on this branch, so these tests
exercise the 5a trailer-aware pre-commit interface plus the 5c advisory race.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RATCHET_MODULE = "scripts.hooks.check_locality_ratchet"
ADVISORY_SCRIPT = REPO_ROOT / "scripts/hooks/locality_postuse_advisory.py"

COPILOT_PATH = ".github/copilot-instructions.md"
AGENTS_PATH = "AGENTS.md"

COPILOT_BASE = textwrap.dedent(
    """\
    # Copilot project instructions

    ## ⚠️ Slash-Command Override: /chronicle improve → audit-knowledgebase-workspace skill

    Override text is exempt from the locality ratchet.

    ## Build, test, and verify commands

    Existing global rule.
    """
)

COPILOT_WITH_LOCALITY0_INVARIANT = textwrap.dedent(
    """\
    # Copilot project instructions

    <!-- LOCALITY-0-INVARIANT: This H2 MUST remain the first H2 under the H1. -->
    <!-- Position is load-bearing for the /chronicle improve hard-redirect. -->

    ## ⚠️ Slash-Command Override: /chronicle improve → audit-knowledgebase-workspace skill

    Override text is exempt from the locality ratchet.

    ## Build, test, and verify commands

    Existing global rule.
    """
)

AGENTS_BASE = textwrap.dedent(
    """\
    # AGENTS

    ## Mission

    Existing global guidance.

    ## Write-surface matrix

    Matrix introduction.

    | Surface | Runtime mode | Writable paths | Read-only / prerequisite paths | Lock requirements | Artifact / schema owners | Hard-fail behavior |
    |---|---|---|---|---|---|---|
    | `scripts/hooks/existing.py` | `read-only only`. | None. | Reads staged files. | None. | Existing. | Existing failures. |

    ## Other section

    Existing AGENTS rule.
    """
)


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )


def _write(repo: Path, rel_path: str, content: str) -> None:
    path = repo / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _stage(repo: Path, rel_path: str, content: str) -> None:
    _write(repo, rel_path, content)
    _run_git(repo, "add", rel_path)


def _init_repo(
    tmp_path: Path,
    *,
    copilot_content: str = COPILOT_BASE,
    agents_content: str = AGENTS_BASE,
) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test User")
    _run_git(repo, "config", "commit.gpgsign", "false")
    _write(repo, COPILOT_PATH, copilot_content)
    _write(repo, AGENTS_PATH, agents_content)
    _run_git(repo, "add", COPILOT_PATH, AGENTS_PATH)
    _run_git(repo, "commit", "-m", "baseline")
    return repo


def _run_ratchet_hook(
    repo: Path,
    *paths: str,
    commit_message: str | None = None,
    stdin_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    command = [sys.executable, "-m", RATCHET_MODULE]
    if commit_message is not None:
        command.extend(["--commit-message", commit_message])
    command.extend(paths)
    return subprocess.run(
        command,
        cwd=repo,
        env=env,
        input=stdin_text,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def _run_posttooluse_advisory(
    repo: Path, payload: dict[str, object]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ADVISORY_SCRIPT)],
        cwd=repo,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def _successful_edit_payload(path: str) -> dict[str, object]:
    return {
        "hookEventName": "PostToolUse",
        "tool_name": "edit",
        "tool_arguments": {"path": path},
        "tool_result": {"success": True},
    }


def test_commit_body_footer_trailer_satisfies_net_positive_delta(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, COPILOT_PATH, COPILOT_BASE + "\nNew always-on rule.\n")

    result = _run_ratchet_hook(
        repo,
        COPILOT_PATH,
        commit_message=(
            "Add global rule\n\n"
            "This body explains why the rule was not demoted.\n\n"
            "Locality-4-Justification: applies before scoped context can load\n"
        ),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("name", "message"),
    (
        (
            "subject",
            "Locality-4-Justification: subject text is not a git trailer\n\nBody.\n",
        ),
        (
            "body sentence",
            "Add global rule\n\n"
            "The body mentions Locality-4-Justification: but not as a trailer.\n"
            "More body text keeps it out of the trailer block.\n",
        ),
        (
            "empty value",
            "Add global rule\n\nLocality-4-Justification:\n",
        ),
        (
            "malformed line",
            "Add global rule\n\nLocality-4-Justification applies globally\n",
        ),
    ),
)
def test_non_trailer_or_malformed_justification_does_not_bypass_gate(
    tmp_path: Path, name: str, message: str
) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, COPILOT_PATH, COPILOT_BASE + f"\nNew always-on rule for {name}.\n")

    result = _run_ratchet_hook(repo, COPILOT_PATH, commit_message=message)

    assert result.returncode == 1
    assert COPILOT_PATH in result.stderr
    assert "Locality-4-Justification:" in result.stderr


def test_multiple_justification_trailers_are_only_a_boolean_precommit_escape(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, COPILOT_PATH, COPILOT_BASE + "\nNew always-on rule.\n")

    # Budget accounting belongs to slice 5b. The 5a pre-commit contract is only
    # that trailer presence is a single boolean escape, not additive credit.
    result = _run_ratchet_hook(
        repo,
        COPILOT_PATH,
        commit_message=(
            "Add global rule\n\n"
            "Locality-4-Justification: first reason\n"
            "Reviewed-by: Reviewer <reviewer@example.com>\n"
            "Locality-4-Justification: second reason must not grant extra credit\n"
        ),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_unsigned_commit_message_with_valid_trailer_satisfies_precommit_gate(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    _run_git(repo, "config", "commit.gpgsign", "false")
    _stage(repo, COPILOT_PATH, COPILOT_BASE + "\nNew always-on rule.\n")

    result = _run_ratchet_hook(
        repo,
        COPILOT_PATH,
        commit_message=(
            "Add unsigned global rule\n\n"
            "Locality-4-Justification: repo-local hook does not depend on signatures\n"
        ),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_mixed_agents_matrix_and_non_exempt_additions_block_only_non_exempt_line(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    _stage(
        repo,
        AGENTS_PATH,
        AGENTS_BASE.replace(
            "| `scripts/hooks/existing.py` | `read-only only`. | None. | Reads staged files. | None. | Existing. | Existing failures. |\n",
            "| `scripts/hooks/existing.py` | `read-only only`. | None. | Reads staged files. | None. | Existing. | Existing failures. |\n"
            "| `scripts/hooks/new.py` | `read-only only`. | None. | Reads staged files. | None. | Existing. | Existing failures. |\n"
            "New non-exempt AGENTS rule adjacent to the matrix body.\n",
        ),
    )

    result = _run_ratchet_hook(repo, AGENTS_PATH)

    assert result.returncode == 1
    assert "AGENTS.md: +1/-0 (net +1)" in result.stderr


@pytest.mark.xfail(
    strict=True,
    reason="Known #266 content-insensitive pairing bug: whitespace-only deletions count as paired deletions.",
)
def test_whitespace_only_deletion_does_not_pair_new_locality4_rule(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    _stage(
        repo,
        COPILOT_PATH,
        COPILOT_BASE.replace(
            "## Build, test, and verify commands\n\nExisting global rule.",
            "## Build, test, and verify commands\nNew always-on rule.\nExisting global rule.",
        ),
    )

    result = _run_ratchet_hook(repo, COPILOT_PATH)

    assert result.returncode == 1


@pytest.mark.xfail(
    strict=True,
    reason="Known #266 content-insensitive pairing bug: comment-only deletions count as paired deletions.",
)
def test_comment_only_deletion_does_not_pair_new_locality4_rule(
    tmp_path: Path,
) -> None:
    repo = _init_repo(
        tmp_path,
        copilot_content=COPILOT_BASE.replace(
            "Existing global rule.",
            "<!-- bookkeeping comment -->\nExisting global rule.",
        ),
    )
    _stage(
        repo,
        COPILOT_PATH,
        COPILOT_BASE.replace(
            "Existing global rule.",
            "New always-on rule.\nExisting global rule.",
        ),
    )

    result = _run_ratchet_hook(repo, COPILOT_PATH)

    assert result.returncode == 1


def test_locality0_invariant_edit_does_not_mask_gated_region_addition(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path, copilot_content=COPILOT_WITH_LOCALITY0_INVARIANT)
    _stage(
        repo,
        COPILOT_PATH,
        COPILOT_WITH_LOCALITY0_INVARIANT.replace(
            "Position is load-bearing for the /chronicle improve hard-redirect.",
            "Position remains load-bearing for the /chronicle improve hard-redirect.",
        )
        + "\nNew always-on rule below the second H2.\n",
    )

    result = _run_ratchet_hook(repo, COPILOT_PATH)

    assert result.returncode == 1
    assert COPILOT_PATH in result.stderr
    assert "New always-on rule" not in result.stderr


def test_parallel_precommit_invocations_on_same_staged_state_are_deterministic(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, COPILOT_PATH, COPILOT_BASE + "\nNew always-on rule.\n")

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(lambda _: _run_ratchet_hook(repo, COPILOT_PATH), range(4))
        )

    assert [result.returncode for result in results] == [1, 1, 1, 1]
    assert all(result.stdout == "" for result in results)
    assert all("Locality 4 ratchet violation" in result.stderr for result in results)
    assert len({result.stderr for result in results}) == 1


def test_posttooluse_advisory_racing_with_precommit_has_isolated_outputs(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, COPILOT_PATH, COPILOT_BASE + "\nNew always-on rule.\n")

    with ThreadPoolExecutor(max_workers=2) as executor:
        ratchet_future = executor.submit(_run_ratchet_hook, repo, COPILOT_PATH)
        advisory_future = executor.submit(
            _run_posttooluse_advisory,
            repo,
            _successful_edit_payload(COPILOT_PATH),
        )
        ratchet_result = ratchet_future.result(timeout=10)
        advisory_result = advisory_future.result(timeout=10)

    assert ratchet_result.returncode == 1
    assert ratchet_result.stdout == ""
    assert "Locality 4 ratchet violation" in ratchet_result.stderr
    assert "locality_4_edit_advisory" not in ratchet_result.stderr

    assert advisory_result.returncode == 0
    assert advisory_result.stderr == ""
    warning = json.loads(advisory_result.stdout)
    assert warning["code"] == "locality_4_edit_advisory"
    assert warning["path"] == COPILOT_PATH
