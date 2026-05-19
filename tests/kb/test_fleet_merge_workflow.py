"""Workflow contract checks for fleet-merge.yml.

Covers:
- Trigger type (workflow_run on CI-2 only — not check_suite, not schedule)
- Job structure (both jobs have timeouts, correct conditions)
- Concurrency serialisation contract
- Secret scoping (JULES_API_KEY must not appear at job level)
- Shell injection guards (inputs.* must not be inline in run: blocks)
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest
import yaml


WORKFLOW_PATH = Path(".github/workflows/fleet-merge.yml")
DISPATCH_PATH = Path(".github/workflows/fleet-dispatch.yml")


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
        """merge-on-ci-pass must only run when workflow_run succeeded."""
        job_if = self.workflow["jobs"]["merge-on-ci-pass"].get("if", "")
        self.assertIn("workflow_run", str(job_if))
        self.assertIn("conclusion", str(job_if))

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
        """JULES_API_KEY must not be at job level — scoped to step only.

        Mounting it at job level exposes the key on every workflow_run event,
        including the no-op fast-exit path for non-fleet PRs.
        """
        job_env = self.workflow["jobs"]["merge-on-ci-pass"].get("env", {})
        self.assertNotIn(
            "JULES_API_KEY",
            job_env,
            "JULES_API_KEY must be step-scoped, not job-level, in merge-on-ci-pass",
        )

    # ── Shell injection guards ───────────────────────────────────────────────

    def test_inputs_base_branch_not_directly_interpolated_in_run_blocks(self) -> None:
        """${{ inputs.base_branch }} must never appear inside a run: block.

        Direct interpolation enables shell injection via a crafted input value.
        The safe pattern is an env: block + shell variable expansion.
        """
        # Split on 'run:' boundaries to check only run block content
        run_blocks = re.findall(r"run:\s*\|?\n((?:[ \t]+.*\n?)*)", self.workflow_text)
        for block in run_blocks:
            self.assertNotIn(
                "${{ inputs.base_branch }}",
                block,
                "inputs.base_branch must not be interpolated directly in a run: block",
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


class FleetDispatchInjectionGuardTests(unittest.TestCase):
    """Injection guard tests for fleet-dispatch.yml's unprotected-branch data path."""

    def setUp(self) -> None:
        self.assertTrue(DISPATCH_PATH.exists(), f"Missing: {DISPATCH_PATH}")
        self.workflow_text = DISPATCH_PATH.read_text(encoding="utf-8")

    def test_pending_date_not_directly_interpolated_in_run_blocks(self) -> None:
        """pending_date is read from the unprotected fleet-state branch.

        Direct interpolation into a run: block allows a collaborator to push a
        crafted .pending_session file that executes arbitrary shell commands.
        Must be routed through an env: var instead.
        """
        run_blocks = re.findall(r"run:\s*\|?\n((?:[ \t]+.*\n?)*)", self.workflow_text)
        for block in run_blocks:
            self.assertNotIn(
                "${{ steps.check.outputs.pending_date }}",
                block,
                "pending_date from fleet-state (unprotected) must not be inline in run: blocks",
            )

    def test_pending_date_routed_through_env_var(self) -> None:
        """FLEET_PENDING_DATE env var must carry pending_date to the shell safely."""
        self.assertIn(
            "FLEET_PENDING_DATE: ${{ steps.check.outputs.pending_date }}",
            self.workflow_text,
        )
        # Shell must reference the env var, not the expression
        self.assertIn('"$FLEET_PENDING_DATE"', self.workflow_text)

    def test_author_filter_uses_startswith_not_contains(self) -> None:
        """Branch name filter must use startsWith to avoid substring false-positives.

        contains(head.ref, 'jules') would match 'my-jules-fix', 'refuels-pipeline', etc.
        """
        self.assertNotIn("contains(github.event.pull_request.head.ref, 'jules')", self.workflow_text)
        self.assertNotIn("contains(github.event.pull_request.head.ref, 'fleet')", self.workflow_text)
        self.assertIn("startsWith(github.event.pull_request.head.ref, 'jules/')", self.workflow_text)
        self.assertIn("startsWith(github.event.pull_request.head.ref, 'fleet/')", self.workflow_text)


if __name__ == "__main__":
    unittest.main()
