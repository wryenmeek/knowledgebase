from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/hooks/check_cross_functional_review.py"
RUNTIME_ROOT = REPO_ROOT / "tests/kb/.runtime/check_cross_functional_review"


@pytest.fixture(autouse=True)
def clean_runtime() -> Path:
    shutil.rmtree(RUNTIME_ROOT, ignore_errors=True)
    RUNTIME_ROOT.mkdir(parents=True)
    yield RUNTIME_ROOT
    shutil.rmtree(RUNTIME_ROOT, ignore_errors=True)


def _head_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _payload(command: str, *, tool_name: str = "bash") -> dict[str, object]:
    return {
        "hookEventName": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": {"command": command},
        "cwd": str(REPO_ROOT),
    }


def _run_hook(
    payload: object | str, *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    run_env = {**os.environ, **(env or {})}
    run_env.pop("BYPASS_CROSS_FUNCTIONAL_REVIEW", None)
    if env and "BYPASS_CROSS_FUNCTIONAL_REVIEW" in env:
        run_env["BYPASS_CROSS_FUNCTIONAL_REVIEW"] = env["BYPASS_CROSS_FUNCTIONAL_REVIEW"]
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        env=run_env,
    )


def _session_state_with_evidence(runtime_root: Path) -> Path:
    session_state = runtime_root / "session-state"
    evidence_dir = session_state / "cross-functional-review-evidence"
    evidence_dir.mkdir(parents=True)
    evidence = {
        "pr_number": 323,
        "reviewers": [
            "code-reviewer",
            "test-engineer",
            "security-auditor",
            "documentation-engineer",
        ],
        "findings_resolved": True,
        "timestamp": "2026-06-21T00:00:00Z",
    }
    (evidence_dir / f"{_head_sha()}.json").write_text(
        json.dumps(evidence), encoding="utf-8"
    )
    return session_state


def _fake_gh(runtime_root: Path, labels: list[str]) -> dict[str, str]:
    bin_dir = runtime_root / "bin"
    bin_dir.mkdir(parents=True)
    labels_json = json.dumps({"labels": [{"name": label} for label in labels]})
    gh = bin_dir / "gh"
    gh.write_text(f"#!/bin/sh\nprintf '%s\\n' '{labels_json}'\n", encoding="utf-8")
    gh.chmod(0o755)
    return {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}


def test_allows_when_evidence_present(clean_runtime: Path) -> None:
    session_state = _session_state_with_evidence(clean_runtime)

    result = _run_hook(
        _payload("gh pr merge 323 --merge"),
        env={"COPILOT_SESSION_STATE_DIR": str(session_state)},
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == ""


def test_allows_when_cross_functional_reviewed_label_present(
    clean_runtime: Path,
) -> None:
    env = {
        **_fake_gh(clean_runtime, ["cross-functional-reviewed"]),
        "COPILOT_SESSION_STATE_DIR": str(clean_runtime / "missing-session-state"),
    }

    result = _run_hook(_payload("gh pr merge 323 --squash"), env=env)

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == ""


def test_allows_when_bypass_env_var_set(clean_runtime: Path) -> None:
    result = _run_hook(
        _payload("gh pr merge 323 --delete-branch"),
        env={
            "COPILOT_SESSION_STATE_DIR": str(clean_runtime / "missing-session-state"),
            "BYPASS_CROSS_FUNCTIONAL_REVIEW": "1",
        },
    )

    assert result.returncode == 0
    assert result.stderr == ""
    audit = json.loads(result.stdout)
    assert audit["code"] == "cross_functional_review_bypass"
    assert audit["audited"] is True


def test_blocks_when_no_evidence_label_or_bypass(clean_runtime: Path) -> None:
    session_state = clean_runtime / "session-state"
    session_state.mkdir()
    env = {
        **_fake_gh(clean_runtime, []),
        "COPILOT_SESSION_STATE_DIR": str(session_state),
    }

    result = _run_hook(_payload("gh pr merge 323 --merge"), env=env)

    assert result.returncode == 1
    assert result.stderr == ""
    assert "Cross-functional review required before `gh pr merge`" in result.stdout
    assert "cross-functional-review-evidence" in result.stdout
    assert "cross-functional-reviewed" in result.stdout


def test_noop_on_non_bash_tool_calls(clean_runtime: Path) -> None:
    result = _run_hook(_payload("gh pr merge 323 --merge", tool_name="edit"))

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == ""


def test_noop_on_bash_calls_that_do_not_match_gh_pr_merge(clean_runtime: Path) -> None:
    result = _run_hook(_payload("git status --short"))

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == ""


def test_fails_closed_on_malformed_json(clean_runtime: Path) -> None:
    result = _run_hook("{not json")

    assert result.returncode == 1
    assert result.stderr == ""
    assert "Malformed PreToolUse hook payload" in result.stdout


def test_fails_closed_on_missing_session_state_directory(clean_runtime: Path) -> None:
    env = {
        **_fake_gh(clean_runtime, []),
        "COPILOT_SESSION_STATE_DIR": str(clean_runtime / "missing-session-state"),
    }

    result = _run_hook(_payload("gh pr merge 323 --merge"), env=env)

    assert result.returncode == 1
    assert result.stderr == ""
    assert "session-state directory is missing" in result.stdout
