"""Workflow contract tests for fleet-dispatch-after-merge.yml (Phase 2b).

Covers the workflow that fires on `push` to main when a planning artifact
lands and runs the per-task agent dispatch. Split out from fleet-dispatch.yml
(Phase 2a) on 2026-06-20 to eliminate the race condition where the merge
step ran synchronously against branch protection (CI-2 takes ~90s, dispatch
fired immediately on PR open). See Issue #82 Layer 4 diagnosis trail.

Contracts enforced here:
- Trigger correctness (push to main with .fleet/*/issue_tasks.json path filter)
- Concurrency group separate from Phase 2a (must not block on it)
- Detection step matches the canonical planning artifact path pattern
- Cross-check against fleet-state pending_date prevents spurious dispatch
  on manual imports or replays
- Injection guards inherited from the pre-split Phase 2a contract:
  pending_date routed via env var, git pull uses -- refspec terminator
- Bun version pin (in companion TestBunVersionPin class in
  test_fleet_merge_workflow.py — that file's BUN_WORKFLOW_PATHS list now
  references this workflow)
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import yaml


DISPATCH_AFTER_MERGE_PATH = Path(".github/workflows/fleet-dispatch-after-merge.yml")


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

    Same shape as the mixin in test_fleet_merge_workflow.py; duplicated here
    rather than imported to keep test files self-contained per the existing
    codebase pattern (e.g., test_contracts.py also defines a local _AssertMixin).
    """

    def assertEqual(self, left, right, msg=None) -> None:
        assert left == right, msg or f"expected {left!r} == {right!r}"

    def assertNotEqual(self, left, right, msg=None) -> None:
        assert left != right, msg or f"expected {left!r} != {right!r}"

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

    def assertGreater(self, left, right, msg=None) -> None:
        assert left > right, msg or f"expected {left!r} > {right!r}"

    def assertGreaterEqual(self, left, right, msg=None) -> None:
        assert left >= right, msg or f"expected {left!r} >= {right!r}"

    @contextmanager
    def subTest(self, **kwargs):
        _ = kwargs
        yield


class TestFleetDispatchAfterMergeTrigger(_AssertMixin):
    """Trigger correctness for Phase 2b — must fire on planning-artifact merges only."""

    def setup_method(self) -> None:
        self.assertTrue(
            DISPATCH_AFTER_MERGE_PATH.exists(),
            f"Missing: {DISPATCH_AFTER_MERGE_PATH}",
        )
        self.workflow_text = DISPATCH_AFTER_MERGE_PATH.read_text(encoding="utf-8")
        self.workflow = yaml.safe_load(self.workflow_text)
        self.on_block: dict = self.workflow.get(True, self.workflow.get("on", {}))

    def test_trigger_is_push_to_main(self) -> None:
        """Workflow must trigger on push to main (the post-auto-merge event).

        pull_request would not fire post-merge; workflow_run on Phase 2a
        wouldn't either because Phase 2a exits after queuing, not after the
        merge. push to main is the right primitive — fires when the queued
        --auto merge eventually lands.
        """
        self.assertIn("push", self.on_block)
        push_block = self.on_block.get("push", {})
        self.assertEqual(
            push_block.get("branches"),
            ["main"],
            "push trigger must be scoped to main only",
        )

    def test_trigger_has_path_filter_for_planning_artifact(self) -> None:
        """Path filter must scope the runner to planning-artifact pushes.

        Without the path filter, every push to main spins up a runner that
        usually exits immediately at the detection step. The filter narrows
        the trigger surface to pushes that actually touch the canonical
        planning artifact path.
        """
        push_block = self.on_block.get("push", {})
        paths = push_block.get("paths", [])
        self.assertIn(
            ".fleet/*/issue_tasks.json",
            paths,
            "push trigger must filter on .fleet/*/issue_tasks.json so non-planning "
            "pushes do not spin up a runner",
        )

    def test_trigger_does_not_listen_to_pull_request(self) -> None:
        """Phase 2b must NOT trigger on pull_request — that's Phase 2a's job.

        If both phases trigger on pull_request, dispatch would race CI-2 again
        (the exact bug the Layer 4 split was meant to fix).
        """
        self.assertNotIn("pull_request", self.on_block)

    def test_trigger_supports_workflow_dispatch_escape_hatch(self) -> None:
        """Phase 2b must expose workflow_dispatch as the operator escape hatch.

        Background (Layer 6): GitHub suppresses every workflow that would
        normally fire from a `push` event when the push was authored by the
        repository's GITHUB_TOKEN (see GitHub Actions docs on triggering
        workflows from other workflows). Phase 2a queues `gh pr merge --auto`
        using the default GITHUB_TOKEN, so the resulting squash-merge push to
        main does NOT fire any push-triggered workflows — including this one.
        Until Phase 2a switches to a non-GITHUB_TOKEN identity (GitHub App
        token recommended; see Issue #310), the operator must manually
        trigger this workflow with `gh workflow run` after the planning PR
        auto-merges. The workflow_dispatch trigger is the supported entry
        point for that recovery flow.
        """
        self.assertIn(
            "workflow_dispatch",
            self.on_block,
            "Phase 2b must expose workflow_dispatch so an operator can "
            "manually dispatch after a GITHUB_TOKEN-authored auto-merge "
            "(which would otherwise suppress the push event). See Layer 6.",
        )


class TestFleetDispatchAfterMergeStructure(_AssertMixin):
    """Job structure contracts for Phase 2b."""

    def setup_method(self) -> None:
        self.assertTrue(
            DISPATCH_AFTER_MERGE_PATH.exists(),
            f"Missing: {DISPATCH_AFTER_MERGE_PATH}",
        )
        self.workflow_text = DISPATCH_AFTER_MERGE_PATH.read_text(encoding="utf-8")
        self.workflow = yaml.safe_load(self.workflow_text)

    def test_concurrency_group_separate_from_phase_2a(self) -> None:
        """Concurrency group must NOT be 'fleet-dispatch' (Phase 2a's group).

        If both workflows share a group, Phase 2b serialises on Phase 2a's
        runs and could deadlock when Phase 2a is waiting for an auto-merge
        that requires Phase 2b's runtime.
        """
        concurrency = self.workflow.get("concurrency", {})
        group = concurrency.get("group", "")
        self.assertNotEqual(
            group,
            "fleet-dispatch",
            "Phase 2b must use a different concurrency group from Phase 2a "
            "to avoid serialisation deadlock",
        )
        self.assertTrue(group, "Phase 2b must declare a concurrency group")

    def test_concurrency_cancel_in_progress_is_false(self) -> None:
        """cancel-in-progress must be False — cancelling a running dispatch
        leaves agent sessions half-spawned."""
        concurrency = self.workflow.get("concurrency", {})
        self.assertFalse(
            concurrency.get("cancel-in-progress", True),
            "cancel-in-progress must be False to prevent mid-dispatch cancellation",
        )

    def test_dispatch_job_has_timeout(self) -> None:
        """Dispatch job must declare timeout-minutes to bound runner cost."""
        jobs = self.workflow.get("jobs", {})
        self.assertIn("dispatch", jobs)
        timeout = jobs["dispatch"].get("timeout-minutes")
        self.assertIsNotNone(timeout, "dispatch job must declare timeout-minutes")
        self.assertGreater(int(timeout), 0)

    def test_clear_pending_uses_git_rm_not_git_add(self) -> None:
        """The clear-pending step must use `git rm` (not `rm + git add`) so
        the .gitignore exclusion of `.fleet/**` does not block staging the
        deletion of the tracked `.fleet/.pending_session` file.

        Layer 7 bug observed 2026-06-20 on the first end-to-end Phase 2b run:
        `git add .fleet/.pending_session` errored with "path is ignored"
        because `.gitignore` excludes `.fleet/**` and `.pending_session` is
        not in the allowlist. `git rm` operates on the index (tracked files)
        and is unaffected by .gitignore matching, so it correctly stages the
        deletion. See Issue #82 diagnostic trail.
        """
        blocks = _collect_run_blocks(self.workflow)
        clear_blocks = [b for b in blocks if ".pending_session" in b and "checkout -B fleet-state" in b]
        self.assertTrue(
            clear_blocks,
            "Phase 2b must have a clear-pending step that checks out fleet-state",
        )
        for block in clear_blocks:
            self.assertIn(
                "git rm",
                block,
                "Clear-pending step must use `git rm` to stage the deletion "
                "of .fleet/.pending_session (it's tracked but gitignored; "
                "`git add` would error with 'path is ignored').",
            )
            # Belt-and-suspenders: assert the buggy pattern is NOT present.
            self.assertNotIn(
                "rm -f .fleet/.pending_session\n          git add .fleet/.pending_session",
                block,
                "Clear-pending step must not use the rm + git-add pattern — "
                "git add refuses ignored paths even for staging deletions.",
            )


class TestFleetDispatchAfterMergeDetection(_AssertMixin):
    """Detection-step correctness — Phase 2b must only dispatch on real planning merges."""

    def setup_method(self) -> None:
        self.assertTrue(
            DISPATCH_AFTER_MERGE_PATH.exists(),
            f"Missing: {DISPATCH_AFTER_MERGE_PATH}",
        )
        self.workflow_text = DISPATCH_AFTER_MERGE_PATH.read_text(encoding="utf-8")
        self.workflow = yaml.safe_load(self.workflow_text)

    def test_checkout_uses_fetch_depth_at_least_2(self) -> None:
        """Detection step diffs HEAD vs HEAD~1, so fetch-depth must be >= 2."""
        steps = self.workflow.get("jobs", {}).get("dispatch", {}).get("steps", [])
        checkout_steps = [s for s in steps if "actions/checkout" in s.get("uses", "")]
        self.assertTrue(checkout_steps, "Phase 2b must check out the repository")
        for step in checkout_steps:
            fetch_depth = step.get("with", {}).get("fetch-depth", 1)
            # 0 means full history; >= 2 means at least HEAD + HEAD~1
            self.assertTrue(
                int(fetch_depth) >= 2 or int(fetch_depth) == 0,
                "checkout fetch-depth must be >= 2 (or 0 for full history) so "
                "the detection step can diff HEAD vs HEAD~1 to find added artifacts",
            )

    def test_detection_step_matches_canonical_planning_path(self) -> None:
        """The detection step must grep for the canonical .fleet/<date>/issue_tasks.json
        path pattern. If a future change broadens this (e.g., to issue_tasks.md),
        non-planning artifacts could trigger dispatch."""
        blocks = _collect_run_blocks(self.workflow)
        detection_blocks = [b for b in blocks if "diff-filter=A" in b]
        self.assertTrue(
            detection_blocks,
            "Phase 2b must have a detection step using git diff --diff-filter=A",
        )
        for block in detection_blocks:
            # The regex pattern in the workflow shell uses an escaped dot
            # (issue_tasks\.json), so match against the filename root.
            self.assertIn(
                "issue_tasks",
                block,
                "Detection step must match against the canonical issue_tasks filename",
            )
            self.assertIn(
                "json",
                block,
                "Detection step must match against the .json extension specifically "
                "(not .md or other variants) to keep dispatch scoped to the machine-"
                "readable planning artifact",
            )

    def test_cross_check_against_fleet_state_pending_date(self) -> None:
        """The detection logic must cross-check the detected artifact date against
        fleet-state's pending_date. Without this, a manual import or replay of an
        old artifact could spuriously trigger dispatch."""
        # We look for the string 'pending_date' AND a fleet-state read
        self.assertIn(
            "fleet-state",
            self.workflow_text,
            "Phase 2b must read pending session info from fleet-state",
        )
        self.assertIn(
            ".pending_session",
            self.workflow_text,
            "Phase 2b must read .pending_session from fleet-state",
        )

    def test_workflow_dispatch_detection_uses_fleet_state_not_diff(self) -> None:
        """For workflow_dispatch (the Layer 6 escape hatch), detection must
        branch on github.event_name and resolve the artifact via fleet-state's
        pending_date rather than the HEAD~1 diff.

        Reason: when an operator triggers this workflow manually after Phase 2a's
        GITHUB_TOKEN-authored auto-merge, intervening commits may have landed on
        main between the planning PR merge and the manual trigger. HEAD~1 would
        then point at an unrelated commit and the diff-based detection would
        skip silently. The fleet-state-derived path is the correct primitive.

        Security: the fleet-state-derived path validates the pending_date shape
        (YYYY_MM_DD) before constructing the artifact path, and confirms the
        artifact file exists on main before proceeding — that replaces the
        diff-based filter as the safety guard for this code path.
        """
        blocks = _collect_run_blocks(self.workflow)
        dispatch_blocks = [b for b in blocks if "workflow_dispatch" in b and "github.event_name" in b]
        self.assertTrue(
            dispatch_blocks,
            "Phase 2b must branch detection on github.event_name = "
            "workflow_dispatch so the manual escape hatch does not rely on "
            "the HEAD~1 diff (which can miss the artifact after intervening "
            "commits land on main).",
        )
        for block in dispatch_blocks:
            self.assertIn(
                "pending_session",
                block,
                "workflow_dispatch detection must resolve the artifact path "
                "via fleet-state's pending_session, not via HEAD~1 diff",
            )
            self.assertIn(
                "is_planning_merge=false",
                block,
                "workflow_dispatch detection must fail closed (exit with "
                "is_planning_merge=false) when fleet-state is missing or "
                "the artifact is not present on main",
            )

    def test_workflow_dispatch_detection_validates_date_shape(self) -> None:
        """workflow_dispatch detection constructs a filesystem path from the
        fleet-state pending_date. The date must be validated against the
        YYYY_MM_DD shape before path construction to prevent fleet-state
        mutation from steering reads outside .fleet/<date>/.

        fleet-state is an unprotected branch; treat its contents as untrusted
        input even for read-only path construction.
        """
        blocks = _collect_run_blocks(self.workflow)
        dispatch_blocks = [b for b in blocks if "workflow_dispatch" in b and "github.event_name" in b]
        self.assertTrue(dispatch_blocks)
        for block in dispatch_blocks:
            self.assertIn(
                "[0-9]{4}_[0-9]{2}_[0-9]{2}",
                block,
                "workflow_dispatch detection must validate pending_date "
                "against the YYYY_MM_DD shape before constructing a "
                ".fleet/<date>/issue_tasks.json path",
            )


class TestFleetDispatchAfterMergeInjectionGuard(_AssertMixin):
    """Injection guards inherited from Phase 2a's pre-split contract.

    Phase 2b inherits the same fleet-state-derived data path that Phase 2a
    previously protected. pending_date, pending_base, and FLEET_BASE_BRANCH
    all originate from the unprotected fleet-state branch and must be routed
    through env vars (not inlined into run: blocks via ${{ ... }} expansion).
    """

    def setup_method(self) -> None:
        self.assertTrue(
            DISPATCH_AFTER_MERGE_PATH.exists(),
            f"Missing: {DISPATCH_AFTER_MERGE_PATH}",
        )
        self.workflow_text = DISPATCH_AFTER_MERGE_PATH.read_text(encoding="utf-8")
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
                "${{ steps.session.outputs.pending_date }}",
                block,
                "pending_date from fleet-state (unprotected) must not be inline in run: blocks",
            )
            self.assertNotIn(
                "${{steps.session.outputs.pending_date}}",
                block,
                "pending_date (no-space form) from fleet-state must not be inline in run: blocks",
            )

    def test_pending_date_routed_through_env_var(self) -> None:
        """FLEET_PENDING_DATE env var must carry pending_date to the shell safely.

        The env var must be declared in an env: block (not inlined in the run: block),
        and the bun call must NOT pass it as a positional argument — the script reads
        it exclusively from process.env.FLEET_PENDING_DATE (issue #134 fix carried
        over from the pre-split Phase 2a contract).
        """
        self.assertIn(
            "FLEET_PENDING_DATE: ${{ steps.session.outputs.pending_date }}",
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
        git_pull_blocks = [b for b in self._run_blocks() if "git pull" in b and "FLEET_BASE_BRANCH" in b]
        self.assertTrue(
            git_pull_blocks,
            "Phase 2b must contain at least one git pull step using FLEET_BASE_BRANCH",
        )
        for block in git_pull_blocks:
            self.assertIn(
                "git pull --ff-only origin -- ",
                block,
                "git pull with FLEET_BASE_BRANCH must use -- refspec terminator",
            )

    def test_base_branch_routed_through_env_var(self) -> None:
        """FLEET_BASE_BRANCH must be declared as an env var (not inlined in run:).

        Same shell-injection risk as pending_date — the source is unprotected
        fleet-state.
        """
        self.assertIn(
            "FLEET_BASE_BRANCH: ${{ steps.session.outputs.pending_base }}",
            self.workflow_text,
        )
        for block in self._run_blocks():
            self.assertNotIn(
                "${{ steps.session.outputs.pending_base }}",
                block,
                "pending_base from fleet-state must not be inline in run: blocks",
            )
