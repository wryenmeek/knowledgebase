from __future__ import annotations

from pathlib import Path
import shlex
import subprocess

import yaml


WORKFLOW_PATH = Path(".github/workflows/fleet-dispatch.yml")


def _check_step_run_block() -> str:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["dispatch"]["steps"]
    step = next(
        step
        for step in steps
        if step.get("name") == "Check if this PR is the fleet planning PR"
    )
    return step["run"]


def _run_planning_pr_check(pr_files_tsv: str) -> subprocess.CompletedProcess[str]:
    run = _check_step_run_block()
    session_id = "jules-session-123"
    wrapper = f"""
MOCK_PR_FILES_TSV={shlex.quote(pr_files_tsv)}
MOCK_PENDING_SESSION_ID={shlex.quote(session_id)}
MOCK_PENDING_DATE=2099_01_01
export GH_TOKEN=mock-token
export REPOSITORY=wryenmeek/knowledgebase
export PR_NUMBER=328
export PR_BODY="planning PR for $MOCK_PENDING_SESSION_ID"
export PR_BRANCH="fleet/$MOCK_PENDING_SESSION_ID"
export GITHUB_OUTPUT=/dev/null

git() {{
  if [ "${{1:-}}" = "fetch" ]; then
    return 0
  fi
  if [ "${{1:-}}" = "rev-parse" ] && [ "${{2:-}}" = "origin/fleet-state" ]; then
    return 0
  fi
  if [ "${{1:-}}" = "show" ] && [ "${{2:-}}" = "origin/fleet-state:.fleet/.pending_session" ]; then
    printf '%s\\n\\n%s\\n' "$MOCK_PENDING_SESSION_ID" "$MOCK_PENDING_DATE"
    return 0
  fi
  echo "unexpected git invocation: $*" >&2
  return 2
}}

gh() {{
  if [ "${{1:-}}" = "api" ]; then
    printf '%s' "$MOCK_PR_FILES_TSV"
    return 0
  fi
  echo "unexpected gh invocation: $*" >&2
  return 2
}}

{run}
"""
    return subprocess.run(
        ["bash", "-c", wrapper],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )


def test_phase_2a_planning_pr_sanity_uses_status_aware_file_api() -> None:
    run = _check_step_run_block()

    assert 'gh api "repos/$REPOSITORY/pulls/$PR_NUMBER/files"' in run
    assert "--paginate" in run
    assert ".filename, .status, (.previous_filename // \"\")" in run
    assert "could not inspect planning PR" in run


def test_phase_2a_planning_pr_sanity_accepts_exact_expected_files() -> None:
    result = _run_planning_pr_check(
        ".fleet/2099_01_01/issue_tasks.md\tadded\t\n"
        ".fleet/2099_01_01/issue_tasks.json\tadded\t\n"
    )

    assert result.returncode == 0, result.stderr
    assert "Fleet pre-merge sanity check passed" in result.stdout


def test_phase_2a_planning_pr_sanity_rejects_empty_diff() -> None:
    result = _run_planning_pr_check("")

    assert result.returncode != 0
    assert "0/0/0 diff" in result.stdout


def test_phase_2a_planning_pr_sanity_rejects_missing_expected_path() -> None:
    result = _run_planning_pr_check(".fleet/2099_01_01/issue_tasks.md\tadded\t\n")

    assert result.returncode != 0
    assert "missing expected path .fleet/2099_01_01/issue_tasks.json" in result.stdout


def test_phase_2a_planning_pr_sanity_rejects_unexpected_path() -> None:
    result = _run_planning_pr_check(
        ".fleet/2099_01_01/issue_tasks.md\tadded\t\n"
        ".fleet/2099_01_01/issue_tasks.json\tadded\t\n"
        "README.md\tadded\t\n"
    )

    assert result.returncode != 0
    assert "changed unexpected path README.md" in result.stdout


def test_phase_2a_planning_pr_sanity_rejects_removed_expected_path() -> None:
    result = _run_planning_pr_check(
        ".fleet/2099_01_01/issue_tasks.md\tremoved\t\n"
        ".fleet/2099_01_01/issue_tasks.json\tadded\t\n"
    )

    assert result.returncode != 0
    assert "unsupported removed path .fleet/2099_01_01/issue_tasks.md" in result.stdout


def test_phase_2a_planning_pr_sanity_rejects_renamed_expected_path() -> None:
    result = _run_planning_pr_check(
        ".fleet/2099_01_01/issue_tasks.md\trenamed\t.fleet/2099_01_01/old_tasks.md\n"
        ".fleet/2099_01_01/issue_tasks.json\tadded\t\n"
    )

    assert result.returncode != 0
    assert "unsupported renamed path .fleet/2099_01_01/issue_tasks.md" in result.stdout


def test_phase_2a_planning_pr_sanity_declares_failure_modes() -> None:
    run = _check_step_run_block()

    assert "0/0/0 diff" in run
    assert "issue_tasks.md" in run
    assert "issue_tasks.json" in run
    assert "missing expected path" in run
    assert "changed unexpected path" in run
    assert 'changed_status" = "removed"' in run
    assert 'changed_status" = "renamed"' in run


def test_phase_2a_pending_session_inputs_fail_closed_before_identity_match() -> None:
    run = _check_step_run_block()

    assert "tr -d '\\r'" in run
    assert "Malformed pending fleet session ID" in run
    assert "grep -qF -- \"$PENDING_SESSION_ID\"" in run
    assert "pending fleet date is not YYYY_MM_DD" in run
