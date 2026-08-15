"""Workflow contract checks for CI-2 read-only analyst diagnostics."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile

import pytest

from tests.kb._workflow_yaml import (
    extract_named_step_block,
    leading_spaces,
    parse_job_mapping_block,
    parse_top_level_mapping_block,
)


WORKFLOW_PATH = Path(".github/workflows/ci-2-analyst-diagnostics.yml")


def _parse_top_level_mapping_block(text: str, key: str) -> dict[str, str]:
    return parse_top_level_mapping_block(text, key, workflow_path=WORKFLOW_PATH)


def _extract_run_block(step_block: str) -> str:
    """Pull the ``run: |`` script body out of one extracted step block."""
    lines = step_block.splitlines()
    run_index = next(
        (index for index, line in enumerate(lines) if line.strip() == "run: |"),
        None,
    )
    if run_index is None:
        raise AssertionError("Unable to locate 'run: |' block in extracted step")
    run_indent = leading_spaces(lines[run_index])

    raw_script_lines: list[str] = []
    for line in lines[run_index + 1 :]:
        if line.strip() and leading_spaces(line) <= run_indent:
            break
        raw_script_lines.append(line if line.strip() else "")

    non_empty = [line for line in raw_script_lines if line.strip()]
    if not non_empty:
        raise AssertionError("Extracted run block is empty")
    script_indent = min(leading_spaces(line) for line in non_empty)
    return "\n".join(line[script_indent:] if line.strip() else "" for line in raw_script_lines)


def _run_freshness_scope_script(
    workflow_text: str,
    *,
    event_name: str,
    changed_target_files: tuple[str, ...] = (),
    changed_other_files: tuple[str, ...] = (),
    deleted_target_files: tuple[str, ...] = (),
) -> tuple[subprocess.CompletedProcess[str], dict[str, str], str]:
    """Execute the real "Compute freshness check scope" step in a throwaway git repo."""
    scope_step = extract_named_step_block(
        workflow_text, "Compute freshness check scope", workflow_path=WORKFLOW_PATH
    )
    script = _extract_run_block(scope_step)

    with tempfile.TemporaryDirectory() as temp_dir:
        repo = Path(temp_dir)
        run = lambda *args: subprocess.run(  # noqa: E731
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True
        )
        run("init", "--quiet", "-b", "main")
        run("config", "user.email", "test@example.com")
        run("config", "user.name", "Test")

        (repo / "wiki/concepts").mkdir(parents=True, exist_ok=True)
        (repo / "wiki/entities").mkdir(parents=True, exist_ok=True)
        (repo / "wiki/analyses").mkdir(parents=True, exist_ok=True)
        (repo / "unrelated-scope-base.md").write_text("base\n", encoding="utf-8")
        for rel in deleted_target_files:
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text("to be deleted\n", encoding="utf-8")
        run("add", "-A")
        run("commit", "--quiet", "-m", "base commit")
        base_sha = run("rev-parse", "HEAD").stdout.strip()

        run("checkout", "--quiet", "-b", "pr-branch")
        for rel in changed_target_files:
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("changed content\n", encoding="utf-8")
        for rel in changed_other_files:
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("changed content\n", encoding="utf-8")
        for rel in deleted_target_files:
            (repo / rel).unlink()
        if changed_target_files or changed_other_files or deleted_target_files:
            run("add", "-A")
            run("commit", "--quiet", "-m", "pr commit")
        head_sha = run("rev-parse", "HEAD").stdout.strip()

        # "origin/<base_ref>" must resolve for the fetch+merge-base logic; a
        # same-repo bare-less setup can use the local branch as its own "origin".
        run("update-ref", "refs/remotes/origin/main", base_sha)
        # Make `git fetch --quiet origin main` a no-op success (no real remote).
        run("remote", "add", "origin", str(repo))

        github_output_path = repo / "github-output.txt"
        github_output_path.write_text("", encoding="utf-8")

        env = os.environ.copy()
        env.update(
            {
                "GITHUB_EVENT_NAME": event_name,
                "PR_BASE_SHA": base_sha,
                "PR_BASE_REF": "main",
                "GITHUB_OUTPUT": str(github_output_path),
            }
        )

        completed = subprocess.run(
            ["bash", "-c", script],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        outputs: dict[str, str] = {}
        for line in github_output_path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                outputs[key] = value
        scope_paths_file = repo / "diagnostics/freshness-scope-paths.txt"
        scope_paths_text = scope_paths_file.read_text(encoding="utf-8") if scope_paths_file.exists() else ""
        return completed, outputs, scope_paths_text


def _run_freshness_diagnostics_branch_script(
    workflow_text: str,
    *,
    freshness_scoped: str,
    freshness_skip: str,
    scope_paths_file_content: str | None,
) -> tuple[subprocess.CompletedProcess[str], str]:
    """Execute just the freshness branch of the diagnostics step against a fake check_doc_freshness.py stub."""
    diagnostics_step = extract_named_step_block(
        workflow_text, "Run analyst diagnostics (lint + unit tests)", workflow_path=WORKFLOW_PATH
    )
    full_script = _extract_run_block(diagnostics_step)

    # Isolate the freshness branch: from "freshness_start=" through the
    # "freshness_duration=" assignment, so this test exercises exactly the
    # logic this PR changed without needing the wrapper/quality/lint/tests
    # commands earlier in the same step to succeed.
    start_marker = 'freshness_start="$(date -u +%s)"'
    end_marker = 'freshness_duration="$((freshness_end - freshness_start))"'
    start_index = full_script.index(start_marker)
    end_index = full_script.index(end_marker) + len(end_marker)
    freshness_branch = full_script[start_index:end_index]
    script = (
        "set -uo pipefail\nset +e\nmkdir -p diagnostics\n"
        + freshness_branch
        + '\necho "freshness_exit=${freshness_exit}"\n'
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        repo = Path(temp_dir)
        (repo / "diagnostics").mkdir(parents=True, exist_ok=True)
        if scope_paths_file_content is not None:
            (repo / "diagnostics/freshness-scope-paths.txt").write_text(
                scope_paths_file_content, encoding="utf-8"
            )

        fake_bin = repo / "bin"
        fake_bin.mkdir(parents=True, exist_ok=True)
        fake_python = fake_bin / "python3"
        # Records every invocation's argv (one per line) and always exits 0,
        # so this test asserts argument construction, not check_doc_freshness's
        # own pass/fail logic (already covered by test_check_doc_freshness.py).
        fake_python.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'if [[ "$1" == "scripts/validation/check_doc_freshness.py" ]]; then\n'
            '  echo "$*" >> \"$(dirname "$0")/../fake-python-invocations.txt\"\n'
            "  exit 0\n"
            "fi\n"
            "exit 1\n",
            encoding="utf-8",
        )
        fake_python.chmod(0o755)

        env = os.environ.copy()
        env.update(
            {
                "FRESHNESS_SCOPED": freshness_scoped,
                "FRESHNESS_SKIP": freshness_skip,
                "PATH": f"{fake_bin}:{env.get('PATH', '')}",
            }
        )

        completed = subprocess.run(
            ["bash", "-c", script],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        invocations_file = repo / "fake-python-invocations.txt"
        invocations = invocations_file.read_text(encoding="utf-8") if invocations_file.exists() else ""
        return completed, invocations


@pytest.fixture()
def workflow_text() -> str:
    assert WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}"
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_ci2_metadata_and_triggers_are_explicit(workflow_text: str) -> None:
    assert "name: CI-2 Analyst Read-Only Diagnostics" in workflow_text
    assert "CI_ID: CI-2" in workflow_text
    assert "TOKEN_PROFILE: tp-analyst-readonly" in workflow_text
    assert 'CLOSURE_EVIDENCE_POLICY_START: "2026-05-25T00:00:00Z"' in workflow_text
    assert "push:" in workflow_text
    assert "pull_request:" in workflow_text
    assert "workflow_dispatch:" in workflow_text


def test_permissions_match_tp_analyst_readonly(workflow_text: str) -> None:
    assert _parse_top_level_mapping_block(workflow_text, "permissions") == {
        "actions": "read",
        "checks": "read",
        "contents": "read",
    }
    assert (
        re.search(
            r"(?im)^\s*(actions|checks|contents|pull-requests|issues|packages|id-token)\s*:\s*write\s*$",
            workflow_text,
        )
        is None
    ), "Workflow must not request write token scopes"
    # issues: read is scoped to the analyst-diagnostics job, not workflow level
    job_perms = parse_job_mapping_block(
        workflow_text, "analyst-diagnostics", "permissions", WORKFLOW_PATH
    )
    assert job_perms == {
        "actions": "read",
        "checks": "read",
        "contents": "read",
        "issues": "read",
    }, "analyst-diagnostics job must declare issues: read at job level"


def test_workflow_yaml_syntax_validated_by_python_test_suite(workflow_text: str) -> None:
    # YAML syntax validation moved to WorkflowYamlSyntaxTests in the Python
    # test suite (issue #16: eliminate duplicate YAML parse in CI-2).
    # The Ruby Psych step was removed; CI-2 no longer parses workflow YAML directly.
    assert 'require "psych"' not in workflow_text
    assert "Psych.parse_file" not in workflow_text


def test_workflow_is_diagnostics_only_with_explicit_failures(workflow_text: str) -> None:
    assert "Install pinned qmd runtime" in workflow_text
    assert "Set up Node.js" in workflow_text
    assert "uses: actions/setup-node@a0853c24544627f65ddf259abe73b1d18a591444" in workflow_text
    assert 'QMD_NPM_PACKAGE="@tobilu/qmd"' in workflow_text
    assert 'QMD_VERSION="2.5.1"' in workflow_text
    assert (
        'QMD_EXPECTED_INTEGRITY="sha512-Ep9ccOj1bNRinfTIszp5UZP8xfi5AJNtmzwWDD4ZVm2YdWVS+rFobWJQovj0HD2uIAFrryvbSpZYeGa3flEO7g=="'
        in workflow_text
    )
    assert (
        'npm view "${QMD_NPM_PACKAGE}@${QMD_VERSION}" dist.integrity --registry=https://registry.npmjs.org'
        in workflow_text
    )
    assert 'if [ "${QMD_DIST_INTEGRITY}" != "${QMD_EXPECTED_INTEGRITY}" ]; then' in workflow_text
    assert "::error::qmd dist.integrity mismatch" in workflow_text
    assert "exit 1" in workflow_text
    assert (
        'npm install --global "${QMD_NPM_PACKAGE}@${QMD_VERSION}" --registry=https://registry.npmjs.org'
        in workflow_text
    )
    assert "qmd init" in workflow_text
    assert "cp .qmd/index.sqlite .qmd/index/index.sqlite" in workflow_text
    assert "cp .qmd/index.yml .qmd/index/index.yml" in workflow_text
    assert "python3 scripts/kb/qmd_preflight.py --repo-root ." in workflow_text
    assert ".ci-bin" not in workflow_text
    assert "cat > .ci-bin/qmd" not in workflow_text
    assert (
        "python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py"
        in workflow_text
    )
    assert "python3 scripts/kb/lint_wiki.py --wiki-root wiki --strict" in workflow_text
    assert "python3 -m pytest tests/ -q" in workflow_text
    assert (
        "python3 scripts/validation/check_doc_freshness.py --scope wiki --path wiki/concepts --path wiki/entities --path wiki/analyses"
        in workflow_text
    )
    assert "python3 -m scripts.validation.check_issue_closure_evidence" in workflow_text
    assert (
        re.search(
            r"python3 -m scripts\.validation\.check_issue_closure_evidence.*?--lookback-days 3650.*?--issue-limit 500.*?--closed-after",
            workflow_text,
            flags=re.DOTALL,
        )
        is not None
    ), "Closure evidence command must include lookback, issue-limit, and closed-after flags"
    assert "--cov=scripts.validation._runtime_budget" in workflow_text
    assert "Secret scan (gitleaks)" in workflow_text
    assert "Dependency vulnerability audit (pip-audit)" in workflow_text
    assert (
        "uses: actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f" in workflow_text
    )
    assert "if: always()" in workflow_text
    assert (
        "always() && (steps.diagnostics.outcome != 'success' || steps.closure-evidence.outcome != 'success' || steps.diagnostics.outputs.exit_code != '0' || steps.closure-evidence.outputs.closure_evidence_exit != '0' || steps.runtime-budget.outputs.overall_status == 'fail')"
        in workflow_text
    )
    assert "Evaluate CI-2 runtime budgets" in workflow_text
    assert "schema/runtime-budgets.json" in workflow_text
    assert "diagnostics/runtime-budget-report.json" in workflow_text
    assert "exit 1" in workflow_text

    forbidden_write_or_release_commands = (
        "git push",
        "git commit",
        "gh pr",
        "scripts/kb/update_index.py --write",
        "scripts/kb/persist_query.py",
    )
    for forbidden in forbidden_write_or_release_commands:
        assert forbidden not in workflow_text


def test_diagnostics_step_propagates_lint_and_test_failures(workflow_text: str) -> None:
    diagnostics_step = extract_named_step_block(
        workflow_text,
        "Run analyst diagnostics (lint + unit tests)",
        workflow_path=WORKFLOW_PATH,
    )
    assert "set -uo pipefail" in diagnostics_step
    assert (
        "set +e" in diagnostics_step
    ), "Diagnostics step must disable inherited bash -e so it can emit all outputs deterministically"

    closure_step = extract_named_step_block(
        workflow_text,
        "Check issue closure evidence",
        workflow_path=WORKFLOW_PATH,
    )
    assert "set -uo pipefail" in closure_step
    assert (
        "set +e" in closure_step
    ), "Closure-evidence step must disable inherited bash -e so closure_evidence_exit is always emitted"

    assert (
        re.search(
            r"python3 \.github/skills/validate-wiki-governance/logic/validate_wiki_governance\.py.*?wrapper_exit=\"\$\{PIPESTATUS\[0\]\}\"",
            workflow_text,
            flags=re.DOTALL,
        )
        is not None
    ), "Wrapper command status must be captured for final diagnostics exit_code"
    assert (
        re.search(
            r"python3 scripts/validation/check_doc_freshness\.py.*?freshness_exit=\"\$\{PIPESTATUS\[0\]\}\"",
            workflow_text,
            flags=re.DOTALL,
        )
        is not None
    ), "Freshness command status must be captured for final diagnostics exit_code"
    assert (
        re.search(
            r"python3 scripts/reporting/content_quality_report\.py.*?quality_exit=\"\$\{PIPESTATUS\[0\]\}\"",
            workflow_text,
            flags=re.DOTALL,
        )
        is not None
    ), "Quality report command status must be captured for final diagnostics exit_code"
    # closure_evidence runs in its own dedicated step (issue #154: GH_TOKEN scoped to that step only)
    assert (
        re.search(
            r"python3 -m scripts\.validation\.check_issue_closure_evidence.*?closure_evidence_exit=\"\$\{PIPESTATUS\[0\]\}\"",
            workflow_text,
            flags=re.DOTALL,
        )
        is not None
    ), "Closure evidence command status must be captured in the dedicated closure-evidence step"
    assert (
        "steps.closure-evidence.outputs.closure_evidence_exit" in workflow_text
    ), "Closure evidence exit must be propagated via steps.closure-evidence.outputs"
    assert (
        re.search(
            r"python3 scripts/kb/lint_wiki\.py --wiki-root wiki --strict.*?lint_exit=\"\$\{PIPESTATUS\[0\]\}\"",
            workflow_text,
            flags=re.DOTALL,
        )
        is not None
    ), "Lint command status must be captured for final diagnostics exit_code"
    assert (
        re.search(
            r"python3 -m pytest tests/ -q.*?tests_exit=\"\$\{PIPESTATUS\[0\]\}\"",
            workflow_text,
            flags=re.DOTALL,
        )
        is not None
    ), "Test command status must be captured for final diagnostics exit_code"
    assert (
        'if [ "${wrapper_exit}" -ne 0 ] || [ "${freshness_exit}" -ne 0 ] || [ "${quality_exit}" -ne 0 ] || [ "${lint_exit}" -ne 0 ] || [ "${tests_exit}" -ne 0 ]; then'
        in workflow_text
    )
    assert "CLOSURE_EVIDENCE_EXIT" in workflow_text
    assert 'echo "exit_code=${diagnostics_exit}" >> "${GITHUB_OUTPUT}"' in workflow_text


def test_freshness_check_is_diff_scoped_on_pull_request(workflow_text: str) -> None:
    # Issue #558: a repo-wide freshness scan on every pull_request blocks
    # ALL open PRs the moment any single wiki page anywhere crosses the
    # 90-day SLA, regardless of what that PR touches. Guard that the
    # pull_request path is scoped to files the PR itself changed, while
    # push/workflow_dispatch retain the full repo-wide scan as the
    # systemic safety net.
    scope_step = extract_named_step_block(
        workflow_text,
        "Compute freshness check scope",
        workflow_path=WORKFLOW_PATH,
    )
    assert "github.event.pull_request.base.sha" in scope_step
    assert "github.event.pull_request.base.ref" in scope_step
    assert "git merge-base -- HEAD" in scope_step
    assert 'git -c core.quotePath=false diff --name-only --diff-filter=ACMR' in scope_step
    assert "wiki/concepts wiki/entities wiki/analyses" in scope_step
    assert 'if [ "${GITHUB_EVENT_NAME}" = "pull_request" ]; then' in scope_step

    diagnostics_step = extract_named_step_block(
        workflow_text,
        "Run analyst diagnostics (lint + unit tests)",
        workflow_path=WORKFLOW_PATH,
    )
    assert "FRESHNESS_SCOPED" in diagnostics_step
    assert "FRESHNESS_SKIP" in diagnostics_step
    assert (
        "check_doc_freshness skipped: PR touches no wiki/concepts, wiki/entities, or wiki/analyses markdown files (issue #558)"
        in diagnostics_step
    )
    assert "diff-scoped, issue #558" in diagnostics_step
    # The unscoped (push/workflow_dispatch) invocation must remain the
    # full repo-wide scan as the systemic safety net.
    assert (
        "python3 scripts/validation/check_doc_freshness.py --scope wiki --path wiki/concepts --path wiki/entities --path wiki/analyses --as-of"
        in diagnostics_step
    )


def test_closure_evidence_token_is_step_scoped(workflow_text: str) -> None:
    closure_step = extract_named_step_block(
        workflow_text,
        "Check issue closure evidence",
        workflow_path=WORKFLOW_PATH,
    )
    assert (
        "GH_TOKEN: ${{ github.token }}" in closure_step
    ), "Closure-evidence step must bind GH_TOKEN locally"

    diagnostics_step = extract_named_step_block(
        workflow_text,
        "Run analyst diagnostics (lint + unit tests)",
        workflow_path=WORKFLOW_PATH,
    )
    assert (
        "GH_TOKEN:" not in diagnostics_step
    ), "Diagnostics step must not bind GH_TOKEN across all commands"
    assert (
        workflow_text.count("GH_TOKEN:") == 1
    ), "CI-2 workflow must bind GH_TOKEN exactly once in the closure-evidence step"


# --- Ci2FreshnessScopeBehaviorTests ---
# Executes the real extracted bash from the freshness-scoping steps (issue #558).
# Complements the contract tests' string-presence assertions with behavioral
# coverage: real git repos and a stub check_doc_freshness.py.


def test_pull_request_with_target_changes_is_scoped_to_changed_paths(workflow_text: str) -> None:
    completed, outputs, scope_paths = _run_freshness_scope_script(
        workflow_text,
        event_name="pull_request",
        changed_target_files=("wiki/concepts/a.md", "wiki/entities/b.md"),
        changed_other_files=("README.md",),
    )
    assert completed.returncode == 0, completed.stderr
    assert outputs.get("scoped") == "true"
    assert outputs.get("skip") == "false"
    scoped_lines = set(scope_paths.splitlines())
    assert scoped_lines == {"wiki/concepts/a.md", "wiki/entities/b.md"}
    assert "README.md" not in scope_paths


def test_pull_request_touching_no_target_files_is_skipped(workflow_text: str) -> None:
    completed, outputs, scope_paths = _run_freshness_scope_script(
        workflow_text,
        event_name="pull_request",
        changed_other_files=("README.md", "scripts/kb/foo.py"),
    )
    assert completed.returncode == 0, completed.stderr
    assert outputs.get("scoped") == "true"
    assert outputs.get("skip") == "true"
    assert scope_paths.strip() == ""


def test_pull_request_deleting_a_target_file_excludes_it_from_scope(workflow_text: str) -> None:
    completed, outputs, scope_paths = _run_freshness_scope_script(
        workflow_text,
        event_name="pull_request",
        deleted_target_files=("wiki/concepts/stale.md",),
    )
    assert completed.returncode == 0, completed.stderr
    # Nothing else changed besides the deletion, so this PR is a no-op for
    # freshness scope (deleted files need no freshness check).
    assert outputs.get("scoped") == "true"
    assert outputs.get("skip") == "true"
    assert "wiki/concepts/stale.md" not in scope_paths


def test_push_event_disables_scoping_and_leaves_paths_file_empty(workflow_text: str) -> None:
    completed, outputs, scope_paths = _run_freshness_scope_script(
        workflow_text,
        event_name="push",
        changed_target_files=("wiki/concepts/a.md",),
    )
    assert completed.returncode == 0, completed.stderr
    assert outputs.get("scoped") == "false"
    assert outputs.get("skip") == "false"
    assert scope_paths.strip() == ""


def test_workflow_dispatch_event_disables_scoping(workflow_text: str) -> None:
    completed, outputs, _scope_paths = _run_freshness_scope_script(
        workflow_text,
        event_name="workflow_dispatch",
        changed_target_files=("wiki/concepts/a.md",),
    )
    assert completed.returncode == 0, completed.stderr
    assert outputs.get("scoped") == "false"
    assert outputs.get("skip") == "false"


def test_skip_branch_short_circuits_without_invoking_freshness_check(workflow_text: str) -> None:
    completed, invocations = _run_freshness_diagnostics_branch_script(
        workflow_text,
        freshness_scoped="true",
        freshness_skip="true",
        scope_paths_file_content=None,
    )
    assert "freshness_exit=0" in completed.stdout
    assert invocations == "", "Skip branch must not invoke check_doc_freshness.py at all"


def test_scoped_branch_passes_one_path_flag_per_changed_file(workflow_text: str) -> None:
    completed, invocations = _run_freshness_diagnostics_branch_script(
        workflow_text,
        freshness_scoped="true",
        freshness_skip="false",
        scope_paths_file_content="wiki/concepts/a.md\nwiki/entities/b.md\n",
    )
    assert "freshness_exit=0" in completed.stdout
    assert "--path wiki/concepts/a.md" in invocations
    assert "--path wiki/entities/b.md" in invocations
    assert "--path wiki/concepts --path wiki/entities --path wiki/analyses" not in invocations


def test_scoped_branch_with_missing_scope_file_fails_closed(workflow_text: str) -> None:
    completed, invocations = _run_freshness_diagnostics_branch_script(
        workflow_text,
        freshness_scoped="true",
        freshness_skip="false",
        scope_paths_file_content=None,
    )
    assert "freshness_exit=1" in completed.stdout
    assert (
        invocations == ""
    ), "Must fail closed instead of invoking check_doc_freshness.py with no paths"


def test_unscoped_branch_passes_full_repo_wide_directories(workflow_text: str) -> None:
    completed, invocations = _run_freshness_diagnostics_branch_script(
        workflow_text,
        freshness_scoped="false",
        freshness_skip="false",
        scope_paths_file_content=None,
    )
    assert "freshness_exit=0" in completed.stdout
    assert "--path wiki/concepts --path wiki/entities --path wiki/analyses" in invocations


# --- WorkflowYamlSyntaxTests ---
# Validate that all CI workflow YAML files parse cleanly (#16).
#
# This single Python-level check replaces the Ruby Psych step that previously
# ran in CI-2 as a separate workflow step. One canonical parse path is cheaper
# than two and keeps validation inside the pytest suite.


def test_all_workflow_yaml_files_parse_without_error() -> None:
    import yaml  # pyyaml — available in dev extras

    workflows_dir = Path(".github/workflows")
    assert workflows_dir.is_dir(), f"Missing workflows dir: {workflows_dir}"
    yaml_files = sorted(workflows_dir.glob("*.yml"))
    assert len(yaml_files) > 0, "No workflow YAML files found"
    errors: list[str] = []
    for yf in yaml_files:
        try:
            yaml.safe_load(yf.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            errors.append(f"{yf}: {exc}")
    assert errors == [], "Workflow YAML syntax errors found:\n" + "\n".join(errors)


def test_ci2_workflow_file_is_included_in_scanned_yaml_files() -> None:
    """CI-2's own workflow file must be in the YAML scan list.

    Guards against the file being accidentally deleted or moved, which would
    allow test_all_workflow_yaml_files_parse_without_error to still pass
    trivially while the CI-2 file went unvalidated.
    """
    workflows_dir = Path(".github/workflows")
    yaml_files = [f.name for f in sorted(workflows_dir.glob("*.yml"))]
    assert (
        "ci-2-analyst-diagnostics.yml" in yaml_files
    ), "ci-2-analyst-diagnostics.yml must be present and scanned by WorkflowYamlSyntaxTests"
