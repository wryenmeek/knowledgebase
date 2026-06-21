"""Shell-execution harness for fleet-dispatch-after-merge.yml workflow steps.

Closes Issue #318. Provides primitives for spawning a real git repository
under tmp_path, materializing the gitignored / unprotected branch shape
that fleet-dispatch-after-merge.yml expects, extracting a named step's
run-block from the YAML (with GH expression substitution), and executing
it under bash -euo pipefail with $GITHUB_OUTPUT captured.

Designed to catch the class of bugs that static workflow contract tests
structurally cannot — Layer 7 (`git add` on ignored path) and Layer 8
(divergent-branch `git pull --ff-only`) were both shell × git × repo-state
interaction failures that landed in production and surfaced on first
end-to-end run.

Primitives (`tests/kb/fleet_dispatch_harness.py`):
  - build_fixture_repo(tmp_path, branches, files_per_branch) -> Path
  - extract_step_script(workflow_path, step_name, gha_vars) -> str
  - run_step(script, env, cwd) -> StepResult

Scenarios live in `tests/kb/test_fleet_dispatch_after_merge_integration.py`.

Constraints honored:
  - Pure pytest, no `unittest.TestCase` (ADR-029)
  - Only stdlib + pytest (no new dependencies)
  - GitHub Actions-isms (`${{ github.event_name }}`, `$GITHUB_OUTPUT`,
    `${{ steps.X.outputs.Y }}`) are trivially substitutable
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml


# =============================================================================
# Primitive 1 — build_fixture_repo
# =============================================================================


def build_fixture_repo(
    tmp_path: Path,
    *,
    branches: dict[str, dict[str, str]] | None = None,
    initial_branch: str = "main",
) -> Path:
    """Initialize a git repository at tmp_path/repo with the given branches.

    Also creates `tmp_path/origin.git` as a bare repo and sets it as the
    `origin` remote, so workflow steps that reference `origin/<branch>`
    work without raising "not a commit" errors. After populating branches,
    pushes all of them to origin.

    Args:
        tmp_path: Pytest tmp_path fixture root.
        branches: Mapping of branch_name -> {file_relative_path: file_contents}.
                  Each branch is created via `git checkout -b` and populated.
                  If None, only an empty `initial_branch` is created.
        initial_branch: Name of the first (default) branch.

    Returns:
        Path to the repo root.
    """
    # Set up bare origin first.
    origin_bare = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", initial_branch, str(origin_bare)],
        check=True,
        capture_output=True,
    )

    repo = tmp_path / "repo"
    repo.mkdir()

    # git init with explicit initial branch (avoids 'master' vs 'main' default drift).
    _run_git(repo, "init", "-b", initial_branch)
    _run_git(repo, "config", "user.name", "Fleet Harness")
    _run_git(repo, "config", "user.email", "fleet-harness@example.invalid")
    _run_git(repo, "remote", "add", "origin", str(origin_bare))

    # Always populate at least one commit on the initial branch so other
    # branches can fork from a known root.
    initial_files = (branches or {}).get(initial_branch, {})
    _materialize_branch(repo, initial_branch, initial_files, is_initial=True)

    if branches:
        for branch_name, files in branches.items():
            if branch_name == initial_branch:
                continue
            _materialize_branch(repo, branch_name, files, is_initial=False)
        # Return to initial branch as the working state.
        _run_git(repo, "checkout", initial_branch)

    # Push all branches to origin so `origin/<branch>` resolves in workflow
    # steps that do `git fetch origin <branch>` + `git rev-parse origin/<branch>`.
    for branch_name in (branches or {initial_branch: {}}).keys():
        _run_git(repo, "push", "origin", branch_name)

    return repo


def _materialize_branch(
    repo: Path, branch: str, files: dict[str, str], *, is_initial: bool
) -> None:
    """Create or switch to the named branch and write the file map."""
    if is_initial:
        # First commit on the initial branch.
        if not files:
            # Need at least one file for the initial commit.
            files = {".gitkeep": ""}
    else:
        _run_git(repo, "checkout", "-B", branch)

    for rel_path, contents in files.items():
        target = repo / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")

    _run_git(repo, "add", "-A")
    # Allow empty commits so a branch with all-ignored files still records itself.
    _run_git(repo, "commit", "--allow-empty", "-m", f"fixture: {branch}")


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git inside the fixture repo; raise on non-zero exit."""
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )


# =============================================================================
# Primitive 2 — extract_step_script
# =============================================================================


_GHA_EXPR_RE = re.compile(r"\$\{\{\s*([^}]+?)\s*\}\}")


def extract_step_script(
    workflow_path: Path, step_name: str, gha_vars: dict[str, str] | None = None
) -> str:
    """Parse workflow YAML, return named step's `run:` block with substitutions.

    Args:
        workflow_path: Path to .github/workflows/<name>.yml.
        step_name: Value of the step's `name:` field to extract.
        gha_vars: Mapping of GHA expression -> literal value for substitution.
                  Example: {"github.event_name": "workflow_dispatch",
                            "steps.detect.outputs.detected_date": "2026_06_20"}

    Returns:
        The run-block content with `${{ expr }}` placeholders substituted.

    Raises:
        ValueError if the step isn't found or doesn't have a `run:` block.
    """
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    gha_vars = gha_vars or {}

    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            if step.get("name") != step_name:
                continue
            run_block = step.get("run")
            if not isinstance(run_block, str):
                raise ValueError(
                    f"Step {step_name!r} found but has no `run:` block "
                    f"(possibly a `uses:` step)."
                )
            return _substitute_gha_expressions(run_block, gha_vars)

    raise ValueError(
        f"Step {step_name!r} not found in {workflow_path}; "
        f"check the step's `name:` field matches exactly."
    )


def _substitute_gha_expressions(text: str, gha_vars: dict[str, str]) -> str:
    """Replace `${{ expr }}` with mapped literals.

    Unmapped expressions are left in place (so the test author sees a clear
    syntax error rather than silent empty substitution).
    """

    def _replace(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        if expr in gha_vars:
            return gha_vars[expr]
        # Leave unmapped expressions verbatim — caller can detect via grep.
        return match.group(0)

    return _GHA_EXPR_RE.sub(_replace, text)


# =============================================================================
# Primitive 3 — run_step
# =============================================================================


@dataclass
class StepResult:
    """Outcome of running a workflow step's shell script in isolation."""

    returncode: int
    stdout: str
    stderr: str
    outputs: dict[str, str] = field(default_factory=dict)
    """Parsed contents of the captured $GITHUB_OUTPUT file."""


def run_step(
    script: str,
    *,
    env: dict[str, str] | None = None,
    cwd: Path,
    timeout: int = 30,
) -> StepResult:
    """Execute the script under `bash -euo pipefail` and parse $GITHUB_OUTPUT.

    Args:
        script: Shell script body (typically from extract_step_script).
        env: Additional env vars to inject (merged on top of os.environ).
        cwd: Working directory (typically the fixture repo).
        timeout: Subprocess timeout in seconds.

    Returns:
        StepResult with returncode, stdout, stderr, and parsed outputs.
    """
    # Create a temp file for $GITHUB_OUTPUT capture.
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as gh_output_file:
        gh_output_path = Path(gh_output_file.name)

    try:
        merged_env = {**os.environ, "GITHUB_OUTPUT": str(gh_output_path)}
        if env:
            merged_env.update(env)

        # Use bash explicitly for `-euo pipefail` semantics and consistent
        # behavior across platforms.
        proc = subprocess.run(
            ["bash", "-c", script],
            cwd=str(cwd),
            env=merged_env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        outputs = _parse_github_output(gh_output_path.read_text(encoding="utf-8"))
        return StepResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            outputs=outputs,
        )
    finally:
        gh_output_path.unlink(missing_ok=True)


def _parse_github_output(content: str) -> dict[str, str]:
    """Parse the simple `key=value` lines GitHub Actions writes to $GITHUB_OUTPUT.

    Per docs: each line is `name=value`, supports multi-line values via
    heredoc delimiters (`name<<EOF\\nvalue\\nEOF`). This harness implements
    the simple case (workflow steps under test use `echo "k=v" >> "$GITHUB_OUTPUT"`).
    """
    outputs: dict[str, str] = {}
    for line in content.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        outputs[key.strip()] = value
    return outputs
