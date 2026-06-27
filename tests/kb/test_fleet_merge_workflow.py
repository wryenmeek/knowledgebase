"""Workflow contract checks for fleet-merge.yml and fleet-dispatch.yml.

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
- Author filter on fleet-dispatch.yml (Phase 2a) must use login equality only

Migrated to pytest (ADR-029) on 2026-06-20 to clear the way for the
Layer 4 architectural change that split fleet-dispatch.yml into Phase 2a
(this file's `FleetDispatchInjectionGuardTests`) and Phase 2b (separate
workflow + separate test file `test_fleet_dispatch_after_merge.py`).
The pre-commit ratchet hook (scripts/hooks/check_test_framework.py)
required removing `unittest.TestCase` before modifying the assertion logic
that previously asserted Phase 1 contained the now-Phase-2b steps.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
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


class _AssertMixin:
    """unittest-compatible assertion methods backed by plain `assert`.

    Used in lieu of `unittest.TestCase` to satisfy ADR-029's pytest ratchet
    while preserving the existing assertion style across the file.
    """

    def assertEqual(self, left, right, msg=None) -> None:
        assert left == right, msg or f"expected {left!r} == {right!r}"

    def assertIn(self, member, container, msg=None) -> None:
        assert member in container, msg or f"expected {member!r} in {container!r}"

    def assertNotIn(self, member, container, msg=None) -> None:
        assert member not in container, msg or f"expected {member!r} not in {container!r}"

    def assertTrue(self, expr, msg=None) -> None:
        assert expr, msg or f"expected truthy, got {expr!r}"

    def assertFalse(self, expr, msg=None) -> None:
        assert not expr, msg or f"expected falsy, got {expr!r}"

    def assertIsNotNone(self, value, msg=None) -> None:
        assert value is not None, msg or "expected not None"

    def assertIsNone(self, value, msg=None) -> None:
        assert value is None, msg or f"expected None, got {value!r}"

    def assertGreater(self, left, right, msg=None) -> None:
        assert left > right, msg or f"expected {left!r} > {right!r}"

    def assertGreaterEqual(self, left, right, msg=None) -> None:
        assert left >= right, msg or f"expected {left!r} >= {right!r}"

    def assertLessEqual(self, left, right, msg=None) -> None:
        assert left <= right, msg or f"expected {left!r} <= {right!r}"

    def assertIsInstance(self, obj, cls, msg=None) -> None:
        assert isinstance(obj, cls), msg or f"expected {obj!r} to be instance of {cls!r}"

    @contextmanager
    def subTest(self, **kwargs):
        # Non-TestCase pytest classes have no subTest equivalent. Use a no-op
        # context manager: the surrounding for-loop's iteration variable in
        # the assertion's f-string message still identifies which iteration
        # failed (subTest in unittest is mainly used for failure reporting,
        # not for execution semantics).
        _ = kwargs
        yield


class TestFleetMergeWorkflowContract(_AssertMixin):
    def setup_method(self) -> None:
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


class TestFleetDispatchInjectionGuard(_AssertMixin):
    """Author-filter and injection-guard tests for fleet-dispatch.yml (Phase 2a).

    Phase 2a was simplified on 2026-06-20 to only queue the auto-merge of
    the Jules planning PR — the post-merge dispatch logic (clearing
    .pending_session, running fleet-dispatch.ts) moved to Phase 2b
    (fleet-dispatch-after-merge.yml). The injection-guard tests for that
    moved logic live in tests/kb/test_fleet_dispatch_after_merge.py.

    This class keeps the contracts that still apply to Phase 2a:
    the author filter (login equality only, no branch-prefix bypass).
    """

    def setup_method(self) -> None:
        self.assertTrue(DISPATCH_PATH.exists(), f"Missing: {DISPATCH_PATH}")
        self.workflow_text = DISPATCH_PATH.read_text(encoding="utf-8")
        self.workflow = yaml.safe_load(self.workflow_text)

    def test_author_filter_uses_login_equality_only(self) -> None:
        """Author filter must use exact login equality, not broad branch prefixes.

        Branch-prefix conditions (startsWith 'jules/', 'fleet/') allow any
        collaborator to trigger dispatch by naming their branch accordingly.
        Removed — user.login equality is sufficient and avoids the bypass.
        The downstream session-ID check in the "Check if this PR is the
        fleet planning PR" step is the authoritative gate.
        """
        self.assertNotIn("contains(github.event.pull_request.head.ref, 'jules')", self.workflow_text)
        self.assertNotIn("contains(github.event.pull_request.head.ref, 'fleet')", self.workflow_text)
        # Branch-prefix startsWith conditions removed (collaborator bypass risk)
        self.assertNotIn("startsWith(github.event.pull_request.head.ref, 'jules/')", self.workflow_text)
        self.assertNotIn("startsWith(github.event.pull_request.head.ref, 'fleet/')", self.workflow_text)
        # Must use exact login equality
        self.assertIn("'google-labs-jules'", self.workflow_text)

    def test_phase_2a_does_not_run_fleet_dispatch_ts(self) -> None:
        """Phase 2a must NOT call fleet-dispatch.ts directly.

        The Layer 4 fix split fleet-dispatch into Phase 2a (queue auto-merge)
        and Phase 2b (run fleet-dispatch.ts after merge lands on main). If a
        future change re-adds the dispatch step here, the race condition
        between the merge and CI-2 returns. Phase 2a must exit after queuing.
        """
        for block in _collect_run_blocks(self.workflow):
            self.assertNotIn(
                "bun fleet-dispatch.ts",
                block,
                "Phase 2a must not invoke fleet-dispatch.ts directly — "
                "that lives in Phase 2b (fleet-dispatch-after-merge.yml)",
            )

    def test_phase_2a_uses_auto_merge(self) -> None:
        """The merge command in Phase 2a must use --auto to wait for required checks.

        Without --auto, the merge fires synchronously and loses the race against
        branch-protection required checks (notably CI-2 diagnostics ~90s runtime).
        """
        self.assertIn(
            "gh pr merge",
            self.workflow_text,
            "Phase 2a must still attempt to merge the planning PR",
        )
        self.assertIn(
            "--auto",
            self.workflow_text,
            "Phase 2a's gh pr merge must use --auto to queue the merge "
            "until branch-protection required checks pass",
        )

    def test_phase_2a_creates_github_app_token_when_credentials_exist(self) -> None:
        """Issue #310 / ADR-036 / Issue #385: Phase 2a should mint a fleet-orchestrator App token.

        Updated post-#385: detect+mint were extracted into the
        `.github/actions/fleet-orchestrator-token` composite action. Phase 2a
        now invokes the composite via a single `uses:` step with `id: app-token`.
        """
        steps = self.workflow["jobs"]["dispatch"]["steps"]
        composite_invocation = next(
            (
                step
                for step in steps
                if step.get("uses") == "./.github/actions/fleet-orchestrator-token"
            ),
            None,
        )
        self.assertIsNotNone(
            composite_invocation,
            "Phase 2a must invoke the fleet-orchestrator-token composite action per #385",
        )
        self.assertEqual(
            composite_invocation.get("id"),
            "app-token",
            "composite invocation must have id: app-token so downstream "
            "`steps.app-token.outputs.*` references resolve",
        )
        self.assertEqual(
            composite_invocation.get("if"),
            "steps.check.outputs.is_fleet_pr == 'true'",
            "composite invocation must gate on is_fleet_pr (only minted when a "
            "Jules planning PR is being processed)",
        )
        self.assertEqual(
            composite_invocation.get("with", {}).get("app-id"),
            "${{ secrets.FLEET_APP_ID }}",
        )
        self.assertEqual(
            composite_invocation.get("with", {}).get("private-key"),
            "${{ secrets.FLEET_APP_PRIVATE_KEY }}",
        )
        # The SHA pin lives inside the composite action (single source of
        # truth). This test no longer asserts the pin here; the per-workflow
        # contract is now "use the composite", and the composite owns the pin.
        # See test_composite_action_pins_create_github_app_token_v3 in
        # tests/kb/test_fleet_dispatch_app_token_diagnostics.py.

    def test_phase_2a_auto_merge_prefers_app_token_with_github_token_fallback(self) -> None:
        """Issue #310: auto-merge should use App token output when present.

        Updated post-#385: APP_TOKEN_AVAILABLE now binds to the composite
        action's `available` output (`steps.app-token.outputs.available`),
        not the pre-#385 separate detect step (`steps.app-token-inputs.outputs.available`).
        """
        steps = self.workflow["jobs"]["dispatch"]["steps"]
        auto_merge_step = next(
            (step for step in steps if step.get("name") == "Queue auto-merge of planning PR"),
            None,
        )
        self.assertIsNotNone(auto_merge_step, "Phase 2a must keep the auto-merge step")
        env = auto_merge_step.get("env", {})
        self.assertEqual(
            env.get("GH_TOKEN"),
            "${{ steps.app-token.outputs.token || secrets.GITHUB_TOKEN }}",
            "Phase 2a must prefer the App token and only fall back to GITHUB_TOKEN",
        )
        self.assertEqual(
            env.get("APP_TOKEN_AVAILABLE"),
            "${{ steps.app-token.outputs.available }}",
        )
        run = auto_merge_step.get("run", "")
        self.assertIn("::warning", run)
        self.assertIn("Issue #310", run)
        self.assertIn("Layer 6", run)


class TestBunVersionPin(_AssertMixin):
    """Assert bun-version is pinned to a specific version (not 'latest') across
    all workflow files that install bun. Issue #130.

    'latest' was replaced with a pinned version in afb1035 — this test prevents
    silent regression to an unpinned version.
    """

    # fleet-dispatch.yml (Phase 2a) no longer installs bun — that moved to
    # fleet-dispatch-after-merge.yml (Phase 2b) as part of the Layer 4 fix.
    BUN_WORKFLOW_PATHS = [
        Path(".github/workflows/fleet-merge.yml"),
        Path(".github/workflows/fleet-dispatch-after-merge.yml"),
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
        steps = self._bun_setup_steps(wf)
        self.assertTrue(steps, "fleet-merge.yml must have at least one setup-bun step")
        for step in steps:
            bun_ver = step.get("with", {}).get("bun-version", "")
            self.assertEqual(
                bun_ver,
                BUN_PINNED_VERSION,
                f"fleet-merge.yml: bun-version must be '{BUN_PINNED_VERSION}', got '{bun_ver}'",
            )

    def test_bun_version_pinned_not_latest_in_fleet_dispatch_after_merge(self) -> None:
        """fleet-dispatch-after-merge.yml must pin bun-version to a specific version, not 'latest'.

        Replaces the prior test against fleet-dispatch.yml — Phase 2a no longer
        installs bun, the bun install + fleet-dispatch.ts steps moved to Phase 2b
        (this workflow) as part of the Layer 4 fix.
        """
        _, wf = self._load(Path(".github/workflows/fleet-dispatch-after-merge.yml"))
        steps = self._bun_setup_steps(wf)
        self.assertTrue(
            steps,
            "fleet-dispatch-after-merge.yml must have at least one setup-bun step "
            "(it owns the bun install + fleet-dispatch.ts invocation post-merge)",
        )
        for step in steps:
            bun_ver = step.get("with", {}).get("bun-version", "")
            self.assertEqual(
                bun_ver,
                BUN_PINNED_VERSION,
                f"fleet-dispatch-after-merge.yml: bun-version must be '{BUN_PINNED_VERSION}', got '{bun_ver}'",
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


class TestCopilotSetupFleetValidation(_AssertMixin):
    """Assert copilot setup runs fleet Bun tests before build checks."""

    def test_copilot_setup_timeout_is_raised_above_ten_minutes(self) -> None:
        """timeout-minutes must stay above the 10m cap without ballooning indefinitely."""
        workflow = yaml.safe_load(COPILOT_SETUP_PATH.read_text(encoding="utf-8"))
        jobs = workflow.get("jobs", {})
        self.assertIn(
            "copilot-setup-steps",
            jobs,
            "copilot-setup-steps job must exist in copilot-setup-steps.yml",
        )
        timeout = jobs["copilot-setup-steps"].get("timeout-minutes")
        self.assertIsNotNone(timeout, "copilot-setup-steps must declare timeout-minutes")
        self.assertIsInstance(timeout, int, "timeout-minutes must be a bare integer")
        self.assertGreaterEqual(
            timeout,
            15,
            "copilot-setup-steps.yml timeout must be at least 15 minutes to avoid the 10-minute cap",
        )
        self.assertLessEqual(
            timeout,
            30,
            "copilot-setup-steps.yml timeout must stay bounded unless the workload changes",
        )

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


class TestFleetMergePRBaseRecovery(_AssertMixin):
    """Assert PR_BASE recovery uses gh pr view (not a hardcoded fallback). Issue #131.

    Regressing to PR_BASE="main" or any hardcoded branch would silently break
    re-dispatch for PRs targeting non-main branches.
    """

    def setup_method(self) -> None:
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
