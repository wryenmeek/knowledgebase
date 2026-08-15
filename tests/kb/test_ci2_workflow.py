"""Workflow contract checks for CI-2 read-only analyst diagnostics."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

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


class Ci2WorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}")
        self.workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_ci2_metadata_and_triggers_are_explicit(self) -> None:
        self.assertIn("name: CI-2 Analyst Read-Only Diagnostics", self.workflow_text)
        self.assertIn("CI_ID: CI-2", self.workflow_text)
        self.assertIn("TOKEN_PROFILE: tp-analyst-readonly", self.workflow_text)
        self.assertIn('CLOSURE_EVIDENCE_POLICY_START: "2026-05-25T00:00:00Z"', self.workflow_text)
        self.assertIn("push:", self.workflow_text)
        self.assertIn("pull_request:", self.workflow_text)
        self.assertIn("workflow_dispatch:", self.workflow_text)

    def test_permissions_match_tp_analyst_readonly(self) -> None:
        self.assertEqual(
            _parse_top_level_mapping_block(self.workflow_text, "permissions"),
            {
                "actions": "read",
                "checks": "read",
                "contents": "read",
            },
        )
        self.assertIsNone(
            re.search(
                r"(?im)^\s*(actions|checks|contents|pull-requests|issues|packages|id-token)\s*:\s*write\s*$",
                self.workflow_text,
            ),
            "Workflow must not request write token scopes",
        )
        # issues: read is scoped to the analyst-diagnostics job, not workflow level
        job_perms = parse_job_mapping_block(
            self.workflow_text, "analyst-diagnostics", "permissions", WORKFLOW_PATH
        )
        self.assertEqual(
            job_perms,
            {
                "actions": "read",
                "checks": "read",
                "contents": "read",
                "issues": "read",
            },
            "analyst-diagnostics job must declare issues: read at job level",
        )

    def test_workflow_yaml_syntax_validated_by_python_test_suite(self) -> None:
        # YAML syntax validation moved to WorkflowYamlSyntaxTests in the Python
        # test suite (issue #16: eliminate duplicate YAML parse in CI-2).
        # The Ruby Psych step was removed; CI-2 no longer parses workflow YAML directly.
        self.assertNotIn('require "psych"', self.workflow_text)
        self.assertNotIn("Psych.parse_file", self.workflow_text)

    def test_workflow_is_diagnostics_only_with_explicit_failures(self) -> None:
        self.assertIn("Install pinned qmd runtime", self.workflow_text)
        self.assertIn("Set up Node.js", self.workflow_text)
        self.assertIn("uses: actions/setup-node@a0853c24544627f65ddf259abe73b1d18a591444", self.workflow_text)
        self.assertIn('QMD_NPM_PACKAGE="@tobilu/qmd"', self.workflow_text)
        self.assertIn('QMD_VERSION="2.5.1"', self.workflow_text)
        self.assertIn(
            'QMD_EXPECTED_INTEGRITY="sha512-Ep9ccOj1bNRinfTIszp5UZP8xfi5AJNtmzwWDD4ZVm2YdWVS+rFobWJQovj0HD2uIAFrryvbSpZYeGa3flEO7g=="',
            self.workflow_text,
        )
        self.assertIn(
            'npm view "${QMD_NPM_PACKAGE}@${QMD_VERSION}" dist.integrity --registry=https://registry.npmjs.org',
            self.workflow_text,
        )
        self.assertIn(
            'if [ "${QMD_DIST_INTEGRITY}" != "${QMD_EXPECTED_INTEGRITY}" ]; then',
            self.workflow_text,
        )
        self.assertIn(
            "::error::qmd dist.integrity mismatch",
            self.workflow_text,
        )
        self.assertIn("exit 1", self.workflow_text)
        self.assertIn(
            'npm install --global "${QMD_NPM_PACKAGE}@${QMD_VERSION}" --registry=https://registry.npmjs.org',
            self.workflow_text,
        )
        self.assertIn("qmd init", self.workflow_text)
        self.assertIn("cp .qmd/index.sqlite .qmd/index/index.sqlite", self.workflow_text)
        self.assertIn("cp .qmd/index.yml .qmd/index/index.yml", self.workflow_text)
        self.assertIn("python3 scripts/kb/qmd_preflight.py --repo-root .", self.workflow_text)
        self.assertNotIn(".ci-bin", self.workflow_text)
        self.assertNotIn("cat > .ci-bin/qmd", self.workflow_text)
        self.assertIn(
            "python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py",
            self.workflow_text,
        )
        self.assertIn("python3 scripts/kb/lint_wiki.py --wiki-root wiki --strict", self.workflow_text)
        self.assertIn("python3 -m pytest tests/ -q", self.workflow_text)
        self.assertIn(
            "python3 scripts/validation/check_doc_freshness.py --scope wiki --path wiki/concepts --path wiki/entities --path wiki/analyses",
            self.workflow_text,
        )
        self.assertIn(
            "python3 -m scripts.validation.check_issue_closure_evidence",
            self.workflow_text,
        )
        self.assertIsNotNone(
            re.search(
                r"python3 -m scripts\.validation\.check_issue_closure_evidence.*?--lookback-days 3650.*?--issue-limit 500.*?--closed-after",
                self.workflow_text,
                flags=re.DOTALL,
            ),
            "Closure evidence command must include lookback, issue-limit, and closed-after flags",
        )
        self.assertIn("--cov=scripts.validation._runtime_budget", self.workflow_text)
        self.assertIn("Secret scan (gitleaks)", self.workflow_text)
        self.assertIn("Dependency vulnerability audit (pip-audit)", self.workflow_text)
        self.assertIn(
            "uses: actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f",
            self.workflow_text,
        )
        self.assertIn("if: always()", self.workflow_text)
        self.assertIn(
            "always() && (steps.diagnostics.outcome != 'success' || steps.closure-evidence.outcome != 'success' || steps.diagnostics.outputs.exit_code != '0' || steps.closure-evidence.outputs.closure_evidence_exit != '0' || steps.runtime-budget.outputs.overall_status == 'fail')",
            self.workflow_text,
        )
        self.assertIn("Evaluate CI-2 runtime budgets", self.workflow_text)
        self.assertIn("schema/runtime-budgets.json", self.workflow_text)
        self.assertIn("diagnostics/runtime-budget-report.json", self.workflow_text)
        self.assertIn("exit 1", self.workflow_text)

        forbidden_write_or_release_commands = (
            "git push",
            "git commit",
            "gh pr",
            "scripts/kb/update_index.py --write",
            "scripts/kb/persist_query.py",
        )
        for forbidden in forbidden_write_or_release_commands:
            self.assertNotIn(forbidden, self.workflow_text)

    def test_diagnostics_step_propagates_lint_and_test_failures(self) -> None:
        diagnostics_step = extract_named_step_block(
            self.workflow_text,
            "Run analyst diagnostics (lint + unit tests)",
            workflow_path=WORKFLOW_PATH,
        )
        self.assertIn("set -uo pipefail", diagnostics_step)
        self.assertIn(
            "set +e",
            diagnostics_step,
            "Diagnostics step must disable inherited bash -e so it can emit all outputs deterministically",
        )

        closure_step = extract_named_step_block(
            self.workflow_text,
            "Check issue closure evidence",
            workflow_path=WORKFLOW_PATH,
        )
        self.assertIn("set -uo pipefail", closure_step)
        self.assertIn(
            "set +e",
            closure_step,
            "Closure-evidence step must disable inherited bash -e so closure_evidence_exit is always emitted",
        )

        self.assertIsNotNone(
            re.search(
                r"python3 \.github/skills/validate-wiki-governance/logic/validate_wiki_governance\.py.*?wrapper_exit=\"\$\{PIPESTATUS\[0\]\}\"",
                self.workflow_text,
                flags=re.DOTALL,
            ),
            "Wrapper command status must be captured for final diagnostics exit_code",
        )
        self.assertIsNotNone(
            re.search(
                r"python3 scripts/validation/check_doc_freshness\.py.*?freshness_exit=\"\$\{PIPESTATUS\[0\]\}\"",
                self.workflow_text,
                flags=re.DOTALL,
            ),
            "Freshness command status must be captured for final diagnostics exit_code",
        )
        self.assertIsNotNone(
            re.search(
                r"python3 scripts/reporting/content_quality_report\.py.*?quality_exit=\"\$\{PIPESTATUS\[0\]\}\"",
                self.workflow_text,
                flags=re.DOTALL,
            ),
            "Quality report command status must be captured for final diagnostics exit_code",
        )
        # closure_evidence runs in its own dedicated step (issue #154: GH_TOKEN scoped to that step only)
        self.assertIsNotNone(
            re.search(
                r"python3 -m scripts\.validation\.check_issue_closure_evidence.*?closure_evidence_exit=\"\$\{PIPESTATUS\[0\]\}\"",
                self.workflow_text,
                flags=re.DOTALL,
            ),
            "Closure evidence command status must be captured in the dedicated closure-evidence step",
        )
        self.assertIn(
            "steps.closure-evidence.outputs.closure_evidence_exit",
            self.workflow_text,
            "Closure evidence exit must be propagated via steps.closure-evidence.outputs",
        )
        self.assertIsNotNone(
            re.search(
                r"python3 scripts/kb/lint_wiki\.py --wiki-root wiki --strict.*?lint_exit=\"\$\{PIPESTATUS\[0\]\}\"",
                self.workflow_text,
                flags=re.DOTALL,
            ),
            "Lint command status must be captured for final diagnostics exit_code",
        )
        self.assertIsNotNone(
            re.search(
                r"python3 -m pytest tests/ -q.*?tests_exit=\"\$\{PIPESTATUS\[0\]\}\"",
                self.workflow_text,
                flags=re.DOTALL,
            ),
            "Test command status must be captured for final diagnostics exit_code",
        )
        self.assertIn(
            'if [ "${wrapper_exit}" -ne 0 ] || [ "${freshness_exit}" -ne 0 ] || [ "${quality_exit}" -ne 0 ] || [ "${lint_exit}" -ne 0 ] || [ "${tests_exit}" -ne 0 ]; then',
            self.workflow_text,
        )
        self.assertIn("CLOSURE_EVIDENCE_EXIT", self.workflow_text)
        self.assertIn('echo "exit_code=${diagnostics_exit}" >> "${GITHUB_OUTPUT}"', self.workflow_text)

    def test_freshness_check_is_diff_scoped_on_pull_request(self) -> None:
        # Issue #558: a repo-wide freshness scan on every pull_request blocks
        # ALL open PRs the moment any single wiki page anywhere crosses the
        # 90-day SLA, regardless of what that PR touches. Guard that the
        # pull_request path is scoped to files the PR itself changed, while
        # push/workflow_dispatch retain the full repo-wide scan as the
        # systemic safety net.
        scope_step = extract_named_step_block(
            self.workflow_text,
            "Compute freshness check scope",
            workflow_path=WORKFLOW_PATH,
        )
        self.assertIn("github.event.pull_request.base.sha", scope_step)
        self.assertIn("github.event.pull_request.base.ref", scope_step)
        self.assertIn("git merge-base -- HEAD", scope_step)
        self.assertIn('git -c core.quotePath=false diff --name-only --diff-filter=ACMR', scope_step)
        self.assertIn("wiki/concepts wiki/entities wiki/analyses", scope_step)
        self.assertIn('if [ "${GITHUB_EVENT_NAME}" = "pull_request" ]; then', scope_step)

        diagnostics_step = extract_named_step_block(
            self.workflow_text,
            "Run analyst diagnostics (lint + unit tests)",
            workflow_path=WORKFLOW_PATH,
        )
        self.assertIn("FRESHNESS_SCOPED", diagnostics_step)
        self.assertIn("FRESHNESS_SKIP", diagnostics_step)
        self.assertIn(
            "check_doc_freshness skipped: PR touches no wiki/concepts, wiki/entities, or wiki/analyses markdown files (issue #558)",
            diagnostics_step,
        )
        self.assertIn("diff-scoped, issue #558", diagnostics_step)
        # The unscoped (push/workflow_dispatch) invocation must remain the
        # full repo-wide scan as the systemic safety net.
        self.assertIn(
            "python3 scripts/validation/check_doc_freshness.py --scope wiki --path wiki/concepts --path wiki/entities --path wiki/analyses --as-of",
            diagnostics_step,
        )

    def test_closure_evidence_token_is_step_scoped(self) -> None:
        closure_step = extract_named_step_block(
            self.workflow_text,
            "Check issue closure evidence",
            workflow_path=WORKFLOW_PATH,
        )
        self.assertIn(
            "GH_TOKEN: ${{ github.token }}",
            closure_step,
            "Closure-evidence step must bind GH_TOKEN locally",
        )

        diagnostics_step = extract_named_step_block(
            self.workflow_text,
            "Run analyst diagnostics (lint + unit tests)",
            workflow_path=WORKFLOW_PATH,
        )
        self.assertNotIn(
            "GH_TOKEN:",
            diagnostics_step,
            "Diagnostics step must not bind GH_TOKEN across all commands",
        )
        self.assertEqual(
            self.workflow_text.count("GH_TOKEN:"),
            1,
            "CI-2 workflow must bind GH_TOKEN exactly once in the closure-evidence step",
        )



class Ci2FreshnessScopeBehaviorTests(unittest.TestCase):
    """Executes the real extracted bash from the freshness-scoping steps (issue #558).

    Complements Ci2WorkflowContractTests' string-presence assertions with
    behavioral coverage: real git repos and a stub check_doc_freshness.py.
    """

    def setUp(self) -> None:
        self.assertTrue(WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}")
        self.workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_pull_request_with_target_changes_is_scoped_to_changed_paths(self) -> None:
        completed, outputs, scope_paths = _run_freshness_scope_script(
            self.workflow_text,
            event_name="pull_request",
            changed_target_files=("wiki/concepts/a.md", "wiki/entities/b.md"),
            changed_other_files=("README.md",),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(outputs.get("scoped"), "true")
        self.assertEqual(outputs.get("skip"), "false")
        scoped_lines = set(scope_paths.splitlines())
        self.assertEqual(scoped_lines, {"wiki/concepts/a.md", "wiki/entities/b.md"})
        self.assertNotIn("README.md", scope_paths)

    def test_pull_request_touching_no_target_files_is_skipped(self) -> None:
        completed, outputs, scope_paths = _run_freshness_scope_script(
            self.workflow_text,
            event_name="pull_request",
            changed_other_files=("README.md", "scripts/kb/foo.py"),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(outputs.get("scoped"), "true")
        self.assertEqual(outputs.get("skip"), "true")
        self.assertEqual(scope_paths.strip(), "")

    def test_pull_request_deleting_a_target_file_excludes_it_from_scope(self) -> None:
        completed, outputs, scope_paths = _run_freshness_scope_script(
            self.workflow_text,
            event_name="pull_request",
            deleted_target_files=("wiki/concepts/stale.md",),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        # Nothing else changed besides the deletion, so this PR is a no-op for
        # freshness scope (deleted files need no freshness check).
        self.assertEqual(outputs.get("scoped"), "true")
        self.assertEqual(outputs.get("skip"), "true")
        self.assertNotIn("wiki/concepts/stale.md", scope_paths)

    def test_push_event_disables_scoping_and_leaves_paths_file_empty(self) -> None:
        completed, outputs, scope_paths = _run_freshness_scope_script(
            self.workflow_text,
            event_name="push",
            changed_target_files=("wiki/concepts/a.md",),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(outputs.get("scoped"), "false")
        self.assertEqual(outputs.get("skip"), "false")
        self.assertEqual(scope_paths.strip(), "")

    def test_workflow_dispatch_event_disables_scoping(self) -> None:
        completed, outputs, _scope_paths = _run_freshness_scope_script(
            self.workflow_text,
            event_name="workflow_dispatch",
            changed_target_files=("wiki/concepts/a.md",),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(outputs.get("scoped"), "false")
        self.assertEqual(outputs.get("skip"), "false")

    def test_skip_branch_short_circuits_without_invoking_freshness_check(self) -> None:
        completed, invocations = _run_freshness_diagnostics_branch_script(
            self.workflow_text,
            freshness_scoped="true",
            freshness_skip="true",
            scope_paths_file_content=None,
        )
        self.assertIn("freshness_exit=0", completed.stdout)
        self.assertEqual(invocations, "", "Skip branch must not invoke check_doc_freshness.py at all")

    def test_scoped_branch_passes_one_path_flag_per_changed_file(self) -> None:
        completed, invocations = _run_freshness_diagnostics_branch_script(
            self.workflow_text,
            freshness_scoped="true",
            freshness_skip="false",
            scope_paths_file_content="wiki/concepts/a.md\nwiki/entities/b.md\n",
        )
        self.assertIn("freshness_exit=0", completed.stdout)
        self.assertIn("--path wiki/concepts/a.md", invocations)
        self.assertIn("--path wiki/entities/b.md", invocations)
        self.assertNotIn("--path wiki/concepts --path wiki/entities --path wiki/analyses", invocations)

    def test_scoped_branch_with_missing_scope_file_fails_closed(self) -> None:
        completed, invocations = _run_freshness_diagnostics_branch_script(
            self.workflow_text,
            freshness_scoped="true",
            freshness_skip="false",
            scope_paths_file_content=None,
        )
        self.assertIn("freshness_exit=1", completed.stdout)
        self.assertEqual(
            invocations,
            "",
            "Must fail closed instead of invoking check_doc_freshness.py with no paths",
        )

    def test_unscoped_branch_passes_full_repo_wide_directories(self) -> None:
        completed, invocations = _run_freshness_diagnostics_branch_script(
            self.workflow_text,
            freshness_scoped="false",
            freshness_skip="false",
            scope_paths_file_content=None,
        )
        self.assertIn("freshness_exit=0", completed.stdout)
        self.assertIn(
            "--path wiki/concepts --path wiki/entities --path wiki/analyses",
            invocations,
        )


class WorkflowYamlSyntaxTests(unittest.TestCase):
    """Validate that all CI workflow YAML files parse cleanly (#16).

    This single Python-level check replaces the Ruby Psych step that previously
    ran in CI-2 as a separate workflow step. One canonical parse path is cheaper
    than two and keeps validation inside the pytest suite.
    """

    def test_all_workflow_yaml_files_parse_without_error(self) -> None:
        import yaml  # pyyaml — available in dev extras

        workflows_dir = Path(".github/workflows")
        self.assertTrue(workflows_dir.is_dir(), f"Missing workflows dir: {workflows_dir}")
        yaml_files = sorted(workflows_dir.glob("*.yml"))
        self.assertGreater(len(yaml_files), 0, "No workflow YAML files found")
        errors: list[str] = []
        for yf in yaml_files:
            try:
                yaml.safe_load(yf.read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                errors.append(f"{yf}: {exc}")
        self.assertEqual(errors, [], "Workflow YAML syntax errors found:\n" + "\n".join(errors))

    def test_ci2_workflow_file_is_included_in_scanned_yaml_files(self) -> None:
        """CI-2's own workflow file must be in the YAML scan list.

        Guards against the file being accidentally deleted or moved, which would
        allow test_all_workflow_yaml_files_parse_without_error to still pass
        trivially while the CI-2 file went unvalidated.
        """
        workflows_dir = Path(".github/workflows")
        yaml_files = [f.name for f in sorted(workflows_dir.glob("*.yml"))]
        self.assertIn(
            "ci-2-analyst-diagnostics.yml",
            yaml_files,
            "ci-2-analyst-diagnostics.yml must be present and scanned by WorkflowYamlSyntaxTests",
        )


if __name__ == "__main__":
    unittest.main()
