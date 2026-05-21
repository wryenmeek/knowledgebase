"""Workflow contract checks for fleet-merge.yml.

Covers:
- Trigger type (workflow_run on CI-2 only — not check_suite, not schedule)
- Fork-PR guard (workflow_run must be from the parent repo, not a fork)
- Job structure (both jobs have timeouts, correct conditions)
- Concurrency serialisation contract
- Secret scoping (JULES_API_KEY must not appear at job level in either job)
- Shell injection guards (inputs.* must not be inline in run: blocks; both spaced
  and no-space expression forms are checked)
- Bun version pin (must be 1.3.1, not latest, in all bun workflow files)
- Re-dispatch ordering (bun re-dispatch must precede gh pr close)
- PR_BASE recovery (gh pr view --json baseRefName must appear in conflict path)
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest
import yaml


WORKFLOW_PATH = Path(".github/workflows/fleet-merge.yml")
DISPATCH_PATH = Path(".github/workflows/fleet-dispatch.yml")
COPILOT_SETUP_PATH = Path(".github/workflows/copilot-setup-steps.yml")

BUN_PINNED_VERSION = "1.3.1"


def _collect_run_blocks(workflow: dict) -> list[str]:
    """Return all run: string values from every step in every job."""
    runs = []
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            run_val = step.get("run")
            if run_val:
                runs.append(str(run_val))
    return runs


class FleetMergeWorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(WORKFLOW_PATH.exists(), f"Missing: {WORKFLOW_PATH}")
        self.workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.workflow = yaml.safe_load(self.workflow_text)
        # YAML parses 'on' as True
        self.on_block: dict = self.workflow.get(True, self.workflow.get("on", {}))

    # ── Trigger contract ─────────────────────────────────────────────────────

    def test_trigger_is_workflow_run_not_check_suite(self) -> None:
        """Must use workflow_run, not check_suite (prevents concurrency queue overflow)."""
        self.assertIn("workflow_run", self.on_block)
        self.assertNotIn("check_suite", self.on_block)

    def test_trigger_is_not_schedule(self) -> None:
        """Must not have a cron schedule (replaced by event-driven architecture)."""
        self.assertNotIn("schedule", self.on_block)

    def test_workflow_run_targets_ci2_only(self) -> None:
        """workflow_run must target CI-2 by name — not all workflows."""
        wr = self.on_block.get("workflow_run", {})
        self.assertEqual(
            wr.get("workflows"),
            ["CI-2 Analyst Read-Only Diagnostics"],
            "workflow_run must target CI-2 exclusively to prevent queue overflow",
        )
        self.assertIn("completed", wr.get("types", []))

    def test_workflow_dispatch_input_declared(self) -> None:
        """Manual sweep must declare base_branch input."""
        wd = self.on_block.get("workflow_dispatch", {})
        inputs = wd.get("inputs", {})
        self.assertIn("base_branch", inputs)

    # ── Fork-PR guard ────────────────────────────────────────────────────────

    def test_merge_on_ci_pass_guards_against_fork_pr_runners(self) -> None:
        """merge-on-ci-pass must only fire for CI-2 runs from the parent repo.

        Without this guard, every fork PR that passes CI-2 causes fleet-merge
        to allocate a runner for the no-op fast-exit path (runner burn).
        The guard: github.event.workflow_run.repository.full_name == github.repository
        """
        job_if = str(self.workflow["jobs"]["merge-on-ci-pass"].get("if", ""))
        self.assertIn(
            "workflow_run.repository.full_name",
            job_if,
            "merge-on-ci-pass must check repository.full_name to block fork-PR runner burn",
        )
        self.assertIn("github.repository", job_if)

    # ── Job structure ────────────────────────────────────────────────────────

    def test_both_jobs_exist(self) -> None:
        jobs = self.workflow.get("jobs", {})
        self.assertIn("merge-on-ci-pass", jobs)
        self.assertIn("manual-sweep", jobs)

    def test_both_jobs_have_timeout(self) -> None:
        jobs = self.workflow.get("jobs", {})
        for job_name in ("merge-on-ci-pass", "manual-sweep"):
            with self.subTest(job=job_name):
                timeout = jobs[job_name].get("timeout-minutes")
                self.assertIsNotNone(timeout, f"{job_name} must declare timeout-minutes")
                self.assertGreater(int(timeout), 0)

    def test_merge_on_ci_pass_condition_checks_workflow_run_conclusion(self) -> None:
        """merge-on-ci-pass must only run when workflow_run concluded successfully."""
        job_if = str(self.workflow["jobs"]["merge-on-ci-pass"].get("if", ""))
        self.assertIn("workflow_run", job_if)
        self.assertIn("conclusion", job_if)
        self.assertIn("success", job_if)

    def test_manual_sweep_condition_is_workflow_dispatch(self) -> None:
        """manual-sweep must only run for workflow_dispatch events."""
        job_if = self.workflow["jobs"]["manual-sweep"].get("if", "")
        self.assertIn("workflow_dispatch", str(job_if))

    # ── Concurrency contract ─────────────────────────────────────────────────

    def test_concurrency_cancel_in_progress_is_false(self) -> None:
        """cancel-in-progress must be False — cancelling a running merge corrupts state."""
        concurrency = self.workflow.get("concurrency", {})
        self.assertFalse(
            concurrency.get("cancel-in-progress", True),
            "cancel-in-progress must be False to prevent mid-merge cancellation",
        )

    # ── Secret scoping ───────────────────────────────────────────────────────

    def test_jules_api_key_not_in_merge_on_ci_pass_job_env(self) -> None:
        """JULES_API_KEY must not be at job level in merge-on-ci-pass.

        Mounting it at job level exposes the key on every workflow_run event,
        including the no-op fast-exit path for non-fleet PRs.
        """
        job_env = self.workflow["jobs"]["merge-on-ci-pass"].get("env", {})
        self.assertNotIn(
            "JULES_API_KEY",
            job_env,
            "JULES_API_KEY must be step-scoped, not job-level, in merge-on-ci-pass",
        )

    def test_jules_api_key_not_in_manual_sweep_job_env(self) -> None:
        """JULES_API_KEY must not be at job level in manual-sweep either.

        Job-level env exposes the key to checkout, bun install, and every other
        step — unnecessary exposure. Must be scoped to the merge/re-dispatch step.
        """
        job_env = self.workflow["jobs"]["manual-sweep"].get("env", {})
        self.assertNotIn(
            "JULES_API_KEY",
            job_env,
            "JULES_API_KEY must be step-scoped, not job-level, in manual-sweep",
        )

    def test_jules_api_key_is_step_scoped_in_merge_on_ci_pass(self) -> None:
        """JULES_API_KEY must be present in at least one step env in merge-on-ci-pass."""
        steps = self.workflow["jobs"]["merge-on-ci-pass"].get("steps", [])
        step_names_with_key = [
            s.get("name", f"step[{i}]")
            for i, s in enumerate(steps)
            if "JULES_API_KEY" in s.get("env", {})
        ]
        self.assertTrue(
            step_names_with_key,
            "JULES_API_KEY must be present in at least one step env in merge-on-ci-pass "
            "(it is correctly step-scoped — do not move it to job level)",
        )

    def test_jules_api_key_is_step_scoped_in_manual_sweep(self) -> None:
        """JULES_API_KEY must be present in at least one step env in manual-sweep."""
        steps = self.workflow["jobs"]["manual-sweep"].get("steps", [])
        step_names_with_key = [
            s.get("name", f"step[{i}]")
            for i, s in enumerate(steps)
            if "JULES_API_KEY" in s.get("env", {})
        ]
        self.assertTrue(
            step_names_with_key,
            "JULES_API_KEY must be present in at least one step env in manual-sweep "
            "(it is correctly step-scoped — do not move it to job level)",
        )

    # ── Shell injection guards ───────────────────────────────────────────────

    def test_inputs_base_branch_not_directly_interpolated_in_run_blocks(self) -> None:
        """${{ inputs.base_branch }} must never appear inside a run: block.

        Direct interpolation enables shell injection via a crafted input value.
        The safe pattern is an env: block + shell variable expansion.

        Uses YAML parse to walk all run: values accurately (avoids regex
        false-matches on `workflow_run:` YAML keys and single-line run: steps).

        Both the spaced form (${{ inputs.base_branch }}) and the no-space form
        (${{inputs.base_branch}}) are checked — GitHub Actions accepts both.
        """
        for block in _collect_run_blocks(self.workflow):
            self.assertNotIn(
                "${{ inputs.base_branch }}",
                block,
                "inputs.base_branch must not be interpolated directly in a run: block",
            )
            self.assertNotIn(
                "${{inputs.base_branch}}",
                block,
                "inputs.base_branch (no-space form) must not be interpolated directly in a run: block",
            )

    def test_base_branch_env_var_pattern_present(self) -> None:
        """The safe expansion pattern must be in the manual-sweep step."""
        self.assertIn(
            "INPUT_BASE_BRANCH: ${{ inputs.base_branch }}",
            self.workflow_text,
        )
        self.assertIn(
            'BASE_BRANCH="${INPUT_BASE_BRANCH:-main}"',
            self.workflow_text,
        )

    def test_bun_redispatch_uses_env_var_not_inline_expression(self) -> None:
        """bun -e re-dispatch must use process.env.JULES_BASE_BRANCH, not a literal."""
        self.assertIn("process.env.JULES_BASE_BRANCH", self.workflow_text)
        # Ensure no baseBranch literal string remains (either 'main' hardcode or
        # shell-var interpolation '${BASE_BRANCH}' inside a JS string)
        self.assertNotIn("baseBranch: 'main'", self.workflow_text)
        self.assertNotIn("baseBranch: '${BASE_BRANCH}'", self.workflow_text)

    # ── Bot filter ───────────────────────────────────────────────────────────

    def test_bot_filter_is_explicit_not_endswith(self) -> None:
        """Author filter must not use endswith('[bot]') — too broad, merges any bot PR."""
        self.assertNotIn('endswith("[bot]")', self.workflow_text)
        self.assertNotIn("endswith('[bot]')", self.workflow_text)
        # Must use an explicit equality check instead
        self.assertIn('"google-labs-jules"', self.workflow_text)

    # ── Re-dispatch ordering ─────────────────────────────────────────────────

    def test_pr_close_happens_after_redispatch(self) -> None:
        """gh pr close must appear after bun -e re-dispatch in every conflict step.

        If bun fails after gh pr close, set -e exits and the task is permanently
        lost (PR gone, new one never created). Fix: re-dispatch first, only close
        the PR once the SDK call has succeeded.
        """
        for job_name in ("merge-on-ci-pass", "manual-sweep"):
            job = self.workflow["jobs"][job_name]
            for i, step in enumerate(job.get("steps", [])):
                run_val = step.get("run", "")
                if "bun -e" not in run_val or "gh pr close" not in run_val:
                    continue
                bun_pos = run_val.find("bun -e")
                close_pos = run_val.find("gh pr close")
                self.assertGreater(
                    close_pos,
                    bun_pos,
                    f"{job_name} step[{i}] ({step.get('name', '?')}): "
                    f"gh pr close must appear after bun -e re-dispatch",
                )


class FleetDispatchInjectionGuardTests(unittest.TestCase):
    """Injection guard tests for fleet-dispatch.yml's unprotected-branch data path."""

    def setUp(self) -> None:
        self.assertTrue(DISPATCH_PATH.exists(), f"Missing: {DISPATCH_PATH}")
        self.workflow_text = DISPATCH_PATH.read_text(encoding="utf-8")
        self.workflow = yaml.safe_load(self.workflow_text)

    def _run_blocks(self) -> list[str]:
        return _collect_run_blocks(self.workflow)

    def test_pending_date_not_directly_interpolated_in_run_blocks(self) -> None:
        """pending_date is read from the unprotected fleet-state branch.

        Direct interpolation into a run: block allows a collaborator to push a
        crafted .pending_session file that executes arbitrary shell commands.
        Must be routed through an env: var instead.

        Both the spaced form and the no-space form are checked — GitHub Actions
        accepts both syntaxes (${{ expr }} and ${{expr}}).
        """
        for block in self._run_blocks():
            self.assertNotIn(
                "${{ steps.check.outputs.pending_date }}",
                block,
                "pending_date from fleet-state (unprotected) must not be inline in run: blocks",
            )
            self.assertNotIn(
                "${{steps.check.outputs.pending_date}}",
                block,
                "pending_date (no-space form) from fleet-state must not be inline in run: blocks",
            )

    def test_pending_date_routed_through_env_var(self) -> None:
        """FLEET_PENDING_DATE env var must carry pending_date to the shell safely.

        The env var must be declared in an env: block (not inlined in the run: block),
        and the bun call must NOT pass it as a positional argument — the script reads
        it exclusively from process.env.FLEET_PENDING_DATE (issue #134 fix).
        """
        self.assertIn(
            "FLEET_PENDING_DATE: ${{ steps.check.outputs.pending_date }}",
            self.workflow_text,
        )
        # The env var must NOT be passed as a positional arg to the bun script.
        # Positional arg exposure was eliminated in issue #134.
        self.assertNotIn(
            'bun fleet-dispatch.ts "$FLEET_PENDING_DATE"',
            self.workflow_text,
            "FLEET_PENDING_DATE must not be passed as positional argv — script reads from process.env",
        )

    def test_git_pull_uses_refspec_terminator(self) -> None:
        """git pull with a fleet-state-derived branch must use -- to stop flag parsing.

        Without --, a crafted FLEET_BASE_BRANCH like '--upload-pack=/tmp/evil'
        would be parsed by git as an option, executing arbitrary code on the runner.
        """
        for block in self._run_blocks():
            if "git pull" in block and "FLEET_BASE_BRANCH" in block:
                self.assertIn(
                    "git pull --ff-only origin -- ",
                    block,
                    "git pull with FLEET_BASE_BRANCH must use -- refspec terminator",
                )

    def test_author_filter_uses_login_equality_only(self) -> None:
        """Author filter must use exact login equality, not broad branch prefixes.

        Branch-prefix conditions (startsWith 'jules/', 'fleet/') allow any
        collaborator to trigger dispatch by naming their branch accordingly.
        Removed — user.login equality is sufficient and avoids the bypass.
        """
        self.assertNotIn("contains(github.event.pull_request.head.ref, 'jules')", self.workflow_text)
        self.assertNotIn("contains(github.event.pull_request.head.ref, 'fleet')", self.workflow_text)
        # Branch-prefix startsWith conditions removed (collaborator bypass risk)
        self.assertNotIn("startsWith(github.event.pull_request.head.ref, 'jules/')", self.workflow_text)
        self.assertNotIn("startsWith(github.event.pull_request.head.ref, 'fleet/')", self.workflow_text)
        # Must use exact login equality
        self.assertIn("'google-labs-jules'", self.workflow_text)


class BunVersionPinTests(unittest.TestCase):
    """Assert bun-version is pinned to a specific version (not 'latest') across
    all workflow files that install bun. Issue #130.

    'latest' was replaced with a pinned version in afb1035 — this test prevents
    silent regression to an unpinned version.
    """

    BUN_WORKFLOW_PATHS = [
        Path(".github/workflows/fleet-merge.yml"),
        Path(".github/workflows/fleet-dispatch.yml"),
        Path(".github/workflows/copilot-setup-steps.yml"),
    ]

    def _load(self, path: Path) -> tuple[str, dict]:
        self.assertTrue(path.exists(), f"Missing: {path}")
        text = path.read_text(encoding="utf-8")
        return text, yaml.safe_load(text)

    def _bun_setup_steps(self, workflow: dict) -> list[dict]:
        """Collect all oven-sh/setup-bun steps from any job."""
        steps = []
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                uses = step.get("uses", "")
                if "setup-bun" in uses:
                    steps.append(step)
        return steps

    def test_bun_version_pinned_not_latest_in_fleet_merge(self) -> None:
        """fleet-merge.yml must pin bun-version to a specific version, not 'latest'."""
        _, wf = self._load(Path(".github/workflows/fleet-merge.yml"))
        for step in self._bun_setup_steps(wf):
            bun_ver = step.get("with", {}).get("bun-version", "")
            self.assertEqual(
                bun_ver,
                BUN_PINNED_VERSION,
                f"fleet-merge.yml: bun-version must be '{BUN_PINNED_VERSION}', got '{bun_ver}'",
            )

    def test_bun_version_pinned_not_latest_in_fleet_dispatch(self) -> None:
        """fleet-dispatch.yml must pin bun-version to a specific version, not 'latest'."""
        _, wf = self._load(Path(".github/workflows/fleet-dispatch.yml"))
        for step in self._bun_setup_steps(wf):
            bun_ver = step.get("with", {}).get("bun-version", "")
            self.assertEqual(
                bun_ver,
                BUN_PINNED_VERSION,
                f"fleet-dispatch.yml: bun-version must be '{BUN_PINNED_VERSION}', got '{bun_ver}'",
            )

    def test_bun_version_pinned_not_latest_in_copilot_setup(self) -> None:
        """copilot-setup-steps.yml must pin bun-version to a specific version, not 'latest'."""
        _, wf = self._load(COPILOT_SETUP_PATH)
        for step in self._bun_setup_steps(wf):
            bun_ver = step.get("with", {}).get("bun-version", "")
            self.assertEqual(
                bun_ver,
                BUN_PINNED_VERSION,
                f"copilot-setup-steps.yml: bun-version must be '{BUN_PINNED_VERSION}', got '{bun_ver}'",
            )


class CopilotSetupFleetValidationTests(unittest.TestCase):
    """Assert copilot setup runs fleet Bun tests before build checks."""

    def test_copilot_setup_runs_fleet_bun_tests(self) -> None:
        self.assertTrue(COPILOT_SETUP_PATH.exists(), f"Missing: {COPILOT_SETUP_PATH}")
        workflow = yaml.safe_load(COPILOT_SETUP_PATH.read_text(encoding="utf-8"))
        steps = workflow.get("jobs", {}).get("copilot-setup-steps", {}).get("steps", [])
        matching = [
            step
            for step in steps
            if step.get("working-directory") == "scripts/fleet"
            and "bun test --bail" in str(step.get("run", ""))
        ]
        self.assertTrue(
            matching,
            "copilot-setup-steps.yml must run 'bun test --bail' in scripts/fleet",
        )

    def test_copilot_setup_triggers_on_fleet_script_changes(self) -> None:
        self.assertTrue(COPILOT_SETUP_PATH.exists(), f"Missing: {COPILOT_SETUP_PATH}")
        workflow = yaml.safe_load(COPILOT_SETUP_PATH.read_text(encoding="utf-8"))
        on_block = workflow.get(True, workflow.get("on", {}))
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                paths = on_block.get(event, {}).get("paths", [])
                self.assertIn(
                    "scripts/fleet/**",
                    paths,
                    f"copilot-setup-steps.yml must trigger on scripts/fleet/** for {event}",
                )


class FleetMergePRBaseRecoveryTests(unittest.TestCase):
    """Assert PR_BASE recovery uses gh pr view (not a hardcoded fallback). Issue #131.

    Regressing to PR_BASE="main" or any hardcoded branch would silently break
    re-dispatch for PRs targeting non-main branches.
    """

    def setUp(self) -> None:
        self.assertTrue(WORKFLOW_PATH.exists(), f"Missing: {WORKFLOW_PATH}")
        self.workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))

    def _conflict_run_blocks(self) -> list[str]:
        """Return run: blocks from steps that contain both bun -e and gh pr close."""
        blocks = []
        for job in self.workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                run_val = step.get("run", "")
                if "bun -e" in run_val and "gh pr close" in run_val:
                    blocks.append(run_val)
        return blocks

    def _merge_on_ci_pass_conflict_blocks(self) -> list[str]:
        """Return conflict run: blocks from the merge-on-ci-pass job only."""
        blocks = []
        job = self.workflow.get("jobs", {}).get("merge-on-ci-pass", {})
        for step in job.get("steps", []):
            run_val = step.get("run", "")
            if "bun -e" in run_val and "gh pr close" in run_val:
                blocks.append(run_val)
        return blocks

    def test_pr_base_recovered_via_gh_pr_view(self) -> None:
        """PR_BASE must be recovered from gh pr view --json baseRefName in merge-on-ci-pass.

        The merge-on-ci-pass conflict path has no workflow input for base_branch,
        so it must recover the branch dynamically from the PR. Regressing to a
        hardcoded 'main' fallback would silently break re-dispatch for non-main PRs.
        The manual-sweep job legitimately uses INPUT_BASE_BRANCH from its input.
        """
        conflict_blocks = self._merge_on_ci_pass_conflict_blocks()
        self.assertTrue(
            conflict_blocks,
            "Expected at least one conflict-path step (containing bun -e and gh pr close) in merge-on-ci-pass",
        )
        for block in conflict_blocks:
            self.assertIn(
                "baseRefName",
                block,
                "merge-on-ci-pass conflict step must recover PR_BASE via gh pr view --json baseRefName",
            )
            self.assertIn(
                "gh pr view",
                block,
                "merge-on-ci-pass conflict step must use gh pr view to recover PR_BASE dynamically",
            )


if __name__ == "__main__":
    unittest.main()
