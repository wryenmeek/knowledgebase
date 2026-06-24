# ADR-019: Jules-based fleet orchestration for parallel issue-to-PR dispatch

## Status
Accepted — amended in-place: Phase 3 merge trigger changed to event-driven and security hardened (see § Amendment); amended in-place: Phase 2/3 pre-merge sanity checks added (see § Amendment 4); extended by Amendment 3 (Phase 2a/2b auto-merge split; see § Amendment 3); extended by ADR-033 (label-driven dispatch adoption); extended by ADR-036 (fleet-orchestrator GitHub App identity supersedes the Layer 6 row's `GH_APP_ID`/`GH_APP_PRIVATE_KEY` reference)

## Date
2026-04-27

## Context

Large batches of related issues (feature requests, documentation gaps,
maintenance tasks) require coordinated parallel implementation. Doing this
sequentially in a single agent context is slow and context-limited. Doing it
ad hoc across uncoordinated manual PRs produces merge conflicts and duplicated
work.

The repository uses Jules (Google's AI coding agent) via the `@google/jules-sdk`
for autonomous coding sessions. Jules can operate in either interactive
(`session()`) or fully automated (`run()`) modes, and produces pull requests as
its primary output artifact. This enables a fleet pattern: spawn multiple Jules
sessions in parallel, each owning one task, then merge their PRs sequentially.

The key design challenge is **task isolation**: two parallel Jules sessions must
not produce conflicting changes. This requires upfront task analysis to detect
file-level ownership conflicts before dispatch.

## Decision

Adopt a **three-phase fleet orchestration pattern** implemented in
`scripts/fleet/` (TypeScript/Bun) with corresponding CI workflows:

### Phase 1 — Plan (`fleet-plan.ts`, triggered by `fleet-plan.yml`)

A Jules planning session analyzes open GitHub issues and produces a structured
task manifest at `.fleet/<date>/issue_tasks.json`. The manifest assigns each
task to a set of files it is expected to touch. The planning session is
interactive (`jules.session()`, `requirePlanApproval: true`) — a human reviews
the task breakdown before dispatch.

The planning PR is polled for up to 60 minutes. If it does not appear, the
workflow fails closed and no dispatch occurs.

### Phase 2 — Dispatch (`fleet-dispatch.ts`, triggered after plan approval)

After the planning PR is merged:

1. **Ownership validation** — detect any two tasks claiming the same file.
   Conflicting tasks are assigned to the same Jules session (sequential
   within-session) rather than separate parallel sessions.
2. **Parallel dispatch** — each non-conflicting task spawns an independent
   Jules session (`jules.run()`, fully automated). Sessions run in parallel,
   each producing a PR.
3. **Concurrency limit** — a maximum of N sessions run at once (configurable
   via `FLEET_MAX_PARALLEL`) to stay within Jules API rate limits.

### Phase 3 — Merge (`fleet-merge.yml`, event-driven via `workflow_run`)

~~*Original: triggered after dispatch completes, polling loop up to configurable retry limit.*~~
*See § Amendment for the current implementation.*

PRs are merged sequentially in arrival order. `fleet-merge.yml` fires when
**CI-2 completes** (`workflow_run` trigger, `conclusion == success`) on a head
SHA that belongs to a Jules-authored fleet PR. This ensures exactly one trigger
fires per PR CI cycle — no concurrency queue overflow. A `workflow_dispatch`
manual sweep is also available to process all currently-passing open fleet PRs.

If branch update produces a conflict, the PR is closed and the task is
re-dispatched as a new `jules.run()` session (single retry, not a loop). The
new PR re-triggers this workflow when its own CI passes.

### Technology choice: TypeScript + Bun

The fleet scripts are TypeScript/Bun rather than Python because:
- The Jules SDK (`@google/jules-sdk`) is a JavaScript/TypeScript package.
- Bun provides fast TypeScript execution without a separate build step.
- The fleet scripts are a standalone orchestration layer, not part of the
  knowledgebase's Python execution surface (`scripts/kb/**`).

The fleet scripts have their own `package.json` and `tsconfig.json`; they are
built with `bun build` and are independent of `pytest`.

### Jules SDK usage contract

```typescript
import { jules } from '@google/jules-sdk';
// jules is a pre-built singleton — never use a constructor
// jules.run()      → AutomatedSession (auto-approve, auto-PR) — use for CI dispatch
// jules.session()  → SessionClient (requirePlanApproval: true) — use for planning
// jules.sessions() → async iterator over all sessions
```

`new Jules()`, `Jules({ apiKey })`, and `jules.createSession()` do not exist.

## Alternatives Considered

### Sequential single-session implementation

- **Pros:** No merge conflicts; simpler orchestration; no Jules SDK dependency.
- **Cons:** Rate-limited by context window and session time; large batches
  take hours rather than minutes; one blocked task stalls all subsequent tasks.
- **Rejected:** Parallelism is the primary value proposition for large issue
  batches.

### GitHub Actions matrix jobs (without Jules)

- **Pros:** Native CI parallelism; no external API dependency.
- **Cons:** Each matrix job runs a static script, not an autonomous agent;
  cannot handle dynamic task decomposition or adapt to implementation
  complexity discovered mid-task.
- **Rejected:** Does not provide the autonomous implementation capability
  that Jules sessions provide.

### Single Jules session with multi-task prompt

- **Pros:** No orchestration layer needed; single PR.
- **Cons:** Single context window limits the number of tasks; serial within
  the session; no isolation between tasks.
- **Rejected:** Does not scale to batches of 10+ tasks.

### Python-based orchestration

- **Pros:** Consistent with the repository's Python execution surface.
- **Cons:** The Jules SDK is TypeScript-only; wrapping it in Python requires
  a subprocess bridge or unofficial binding.
- **Rejected:** TypeScript is the natural language for the Jules SDK; the
  fleet layer is explicitly not part of `scripts/kb/**` or any Python surface.

## Consequences

- `scripts/fleet/` is a standalone TypeScript/Bun project, not covered by
  `pytest`. After editing fleet scripts, run `cd scripts/fleet && bun build
  fleet-plan.ts fleet-dispatch.ts fleet-merge.ts` to verify TypeScript is clean.
- The fleet pattern requires `JULES_API_KEY` and `GITHUB_TOKEN` secrets in CI.
- Task manifests in `.fleet/` are ephemeral artifacts; they are not committed
  to the repository's knowledge surfaces.
- The merge re-dispatch loop prevents infinite loops via a configurable retry
  limit; exhausted retries produce a labeled issue for human review.
- Fleet orchestration is orthogonal to the knowledgebase write-surface matrix —
  Jules sessions produce PRs that go through normal CI gates (CI-1 → CI-2 →
  CI-3 or CI-4) like any human-authored PR.

## Amendment

**Date:** 2026-05-18
**Commits:** `614cc6f`, `f7ecf96`, `afb1035`, `d515efb`

### What changed

**Phase 3 trigger — polling → event-driven (`workflow_run`)**

The original design described Phase 3 as "triggered after dispatch completes"
with a polling/loop model and a "configurable retry limit". The implementation
diverged significantly: `fleet-merge.yml` now uses `workflow_run` on
**CI-2 completion** rather than polling. Key consequences:
- Exactly one trigger fires per PR CI cycle (CI-2, not every check suite),
  eliminating the concurrency queue overflow that silently dropped merge events
  when `check_suite: completed` fired multiple times per PR.
- The retry loop is replaced by a single re-dispatch via `jules.run()`. The new
  PR re-triggers the workflow when its own CI passes — naturally bounded.
- A `workflow_dispatch` manual-sweep path merges all currently-passing open
  fleet PRs, useful after outages.

**Security hardening of fleet-merge.yml and fleet-dispatch.yml**

Several security decisions were made that are not reflected in the original ADR:

1. **Expression injection guard** — GitHub Actions expressions (`${{ inputs.* }}`,
   `${{ steps.*.outputs.* }}`) are never interpolated directly into `run:` shell
   blocks. All external values route through an `env:` block and are referenced
   as shell variables (`$VAR`). This prevents command injection when values
   originate from unprotected branches or user-controlled inputs.

2. **Git flag injection guard** — Branch values sourced from the unprotected
   `fleet-state` branch (e.g., `FLEET_BASE_BRANCH`) are passed to git commands
   with a `--` refspec terminator (`git pull --ff-only origin -- "$BRANCH"`).
   Without `--`, a crafted branch name like `--upload-pack=/tmp/evil` would be
   parsed by git as an option, executing arbitrary code on the runner.

3. **Step-scoped secrets** — `JULES_API_KEY` is declared only in the `env:` block
   of the specific step that calls the Jules SDK, not at job level. Job-level
   placement exposes the secret to checkout, bun install, and every other step
   unnecessarily.

4. **Author filter — exact login equality** — The fleet-dispatch job-level `if:`
   condition uses `user.login == 'google-labs-jules'` exclusively. Branch-prefix
   conditions (`startsWith('jules/')`, `startsWith('fleet/')`) were removed because
   any collaborator with push access could name a branch `jules/anything` to
   trigger dispatch. The `user.login` check is sufficient and not bypassable.

5. **Re-dispatch before close** — In conflict paths, the Jules SDK re-dispatch
   call executes *before* `gh pr close`. If `bun` or the SDK fails, `set -euo
   pipefail` stops the script and the original PR remains open (no task loss).
   Inverting this order (close first, then re-dispatch) would permanently lose
   the task if the re-dispatch step fails.

6. **Fork-PR runner guard** — The `merge-on-ci-pass` job `if:` condition checks
   `github.event.workflow_run.repository.full_name == github.repository` to
   prevent runner allocation for CI-2 runs originating from fork PRs.

### What did not change

- Phases 1 and 2 (plan, dispatch) are unchanged.
- The TypeScript/Bun technology choice for fleet scripts is unchanged.
- The Jules SDK usage contract (`jules.run()` for automation, `jules.session()`
  for interactive planning) is unchanged.
- Fleet PRs continue to enter the normal CI review gate (CI-2 → fleet-merge)
  like any other PR.

## Amendment 2

**Date:** 2026-06-19

### What changed

**Ops tooling added: account probe and stale-session archive**

Two operator scripts were ported into `scripts/fleet/` from `wryenmeek/hot-springs-island`
(see issue #82) to remove the cross-repo dependency for session-cap saturation diagnosis:

- **`jules-account-probe.ts`** — read-only snapshot of sources, session counts per source,
  and `inProgress` session ages. No side effects. Outputs structured JSON to stdout.
- **`archive-stale-sessions.ts`** — bulk-archive with dry-run default. `--older-than-days N`
  is required. `--apply` performs real archive calls.

**Source-scoping safety contract (deny-by-default)**

`jules.sessions()` returns sessions across **all** repositories on the Jules account.
The archive tool enforces source scoping for `--apply` mode to prevent accidental
cross-account archive:

- `--apply` without any source scope fails closed with a non-zero exit.
- `--repo current` — shorthand for `sources/github/wryenmeek/knowledgebase`.
- `--source-filter <source-id>` — explicit source ID.
- `--repo all` — explicit opt-in for account-wide archive.
- Dry-run (default, no `--apply`) allows any scope, including no scope, because it
  has no side effects.

**Approval model:** `--apply` flag on the CLI or `apply=true` in the workflow is the
operator confirmation. No additional interactive prompt is required; the explicit flag
is the acknowledgment. `--repo all` serves as the second confirmation for account-wide
archive.

**Rollback / verification path:** Archive is not deletion. Archived sessions remain
accessible by ID and can be unarchived via `jules.session(id).unarchive()`. After
archiving, re-run the account probe (`jules-account-probe.ts`) to confirm
`totals.activeSessions` dropped.

**Corresponding CI workflows:**
- `jules-account-probe.yml` — `workflow_dispatch` only; attaches JSON artifact; no secret required beyond `JULES_API_KEY` (step-scoped).
- `jules-archive-stale.yml` — `workflow_dispatch` only; `source_filter` defaults to `sources/github/wryenmeek/knowledgebase` (surrounding whitespace trimmed, whitespace-only rejected per PR #315); `JULES_API_KEY` step-scoped. Apply runs gate on the `jules-archive-approval` GitHub environment (PR #312 + v-sec follow-up — environment expression uses boolean-truthy `${{ inputs.apply && 'jules-archive-approval' || '' }}`, NOT the type-mismatched `inputs.apply == 'true'` which silently never engages). Concurrency partitions by `inputs.apply` with `cancel-in-progress: false`.
  All inputs routed through `env:` blocks per the shell-injection guard from Amendment 1.

### What did not change

- The three-phase fleet orchestration pattern (Plan → Dispatch → Merge) is unchanged.
- The Jules SDK usage contract is unchanged.
- Security conventions from Amendment 1 (injection guard, step-scoped secrets, etc.) are unchanged.

## Related decisions

- [`ADR-032`](ADR-032-fleet-quota-saturation-soft-warn.md) — Extends
  fleet error routing with the `quota_saturation` classification and
  exit-0 soft-warn behavior for transient Jules session quota saturation.

## Amendment 3

### Date
2026-06-20

### What changed

Phase 2 was split into two sub-phases (2a and 2b) to eliminate a race between branch protection's required CI-2 check and a synchronous merge step. The split exposed an end-to-end pipeline that depended on a `push`-event handoff between Actions runs — which GitHub Actions intentionally suppresses when the originating push is authored by `GITHUB_TOKEN`. Layers 5 through 9 of the diagnostic trail (Issue #82) capture the full sequence; layers 5 through 8 are remediated; layer 6 now has a partial code-path implementation that uses an optional GitHub App installation token when operator-provisioned credentials exist; layer 6 remains open until the App is provisioned and an end-to-end planning PR proves Phase 2b fires automatically. Layer 9 (issues:write permission) is tracked as Issue #311.

**Phase 2 sub-phases (replaces the prior single Phase 2):**

- **Phase 2a — Queue auto-merge of planning PR** (`.github/workflows/fleet-dispatch.yml`, `pull_request` opened/reopened): identifies the Jules planning PR via fleet-state's pending session ID, queues `gh pr merge --auto --squash --delete-branch`, exits. The merge is queued, not synchronous; it lands once branch-protection required checks (notably CI-2 diagnostics) finish.

- **Phase 2b — Detect, clear, and dispatch** (`.github/workflows/fleet-dispatch-after-merge.yml`, `push` to main path-filtered to `.fleet/*/issue_tasks.json`, plus `workflow_dispatch`): detects the newly-added planning artifact, cross-checks against fleet-state, clears `.fleet/.pending_session`, restores main, runs `fleet-dispatch.ts` to spawn one Jules session per task.

### Pipeline diagnostic timeline (Layers 1–9)

| Layer | Symptom | Root cause | Fix | Commit / Issue |
|---|---|---|---|---|
| 1 | `fleet-plan.ts` returned `FAILED_PRECONDITION` from Jules SDK on every cron run | Suspected cap of 1 inProgress Jules session per account (tentative — see "Status" below) | Archived the single stuck 95-day session; cron immediately succeeded | `PR #297` (account-probe + stale-archive tools); Issue #82 |
| 2 | Planning PRs opened with 0 changed files (artifact silently excluded) | `.gitignore` rule `.fleet/` excluded all dated planning subdirs (added accidentally in checkpoint commit `50e9d68`, 2026-05-23) | Tightened to `.fleet/**` with explicit allowlist for `issue_tasks.json`, `issue_tasks.md`, `sessions.json`; Bun regression test in `scripts/fleet/fleet-plan-gitignore.test.ts` | `96299ec` |
| 3 | Phase 2a dispatch step skipped every Jules-authored planning PR | Author identity filter `user.login == 'google-labs-jules'` no longer matched — Jules's auth model shifted to PAT-based posting, so PR opener is the operator (`github.repository_owner`) while commits stay `google-labs-jules[bot]` | Widened filter to allow both `google-labs-jules` (historical bot) and `github.repository_owner` (PAT-based); kept login-equality only (no branch-prefix bypass) | `37c84fa` |
| 4 | Phase 2a's synchronous `gh pr merge --squash` lost a race against branch protection's CI-2 required check (~5s after PR open vs ~90s to complete CI-2) | Single workflow tried to merge synchronously without waiting for required checks | Split Phase 2 into 2a (queue `--auto` merge, exit) + 2b (push trigger, detect + dispatch). Separate concurrency groups so phases never block each other. Contract tests in `tests/kb/test_fleet_dispatch_after_merge.py` | `f49769c` |
| 5 | Phase 2a auto-merge step failed with `GraphQL: Auto merge is not allowed for this repository (enablePullRequestAutoMerge)` | Repo setting `allow_auto_merge` was `false` | Enabled via `gh api -X PATCH repos/wryenmeek/knowledgebase -f allow_auto_merge=true` | (repo setting — no commit) |
| 6 | Planning PR auto-merged by `app/github-actions` cleanly, but zero workflow runs fired on the resulting merge commit `ce3bd0e` (Phase 2b never triggered) | GitHub Actions suppresses `push`/`pull_request`/`check_suite`/etc. workflow runs for events authored by `GITHUB_TOKEN` (documented exceptions: `workflow_dispatch`, `repository_dispatch`) | **Interim**: added `workflow_dispatch:` trigger to Phase 2b with `github.event_name` branching in the detect step. **Partial code path**: Phase 2a now detects optional `GH_APP_ID`/`GH_APP_PRIVATE_KEY` secrets, mints a pinned `actions/create-github-app-token` installation token when they are present and valid, and uses `GITHUB_TOKEN` with a warning annotation fallback otherwise. **Still open**: operator must provision/install the App and verify a real planning PR auto-merge fires Phase 2b without manual dispatch before Issue #310 can close. | `49a6d52`; tracked as Issue #310 |
| 7 | Phase 2b clear-pending step failed with `fatal: The following paths are ignored by one of your .gitignore files: .fleet` | The Layer 2 `.gitignore` tightening excluded the entire `.fleet/` tree, so `git add .fleet/.pending_session` refused the ignored path even when staging a deletion | Switched from `rm + git add` to `git rm` (operates on the index, not the working tree, so unaffected by gitignore matching). Wrapped in `git ls-files --error-unmatch` to detect tracked state idempotently | `51acc01` |
| 8 | Phase 2b dispatch step failed with `fatal: Not possible to fast-forward, aborting` | Clear-pending step started with `git checkout -B fleet-state` and never switched back to main; dispatch's `git pull --ff-only origin -- main` then tried to fast-forward fleet-state to main (divergent branches) | Appended `git checkout main` to the end of clear-pending so downstream steps start on main | `0e55f12` |
| 9 | All per-issue tracker-comment postings from `fleet-dispatch.ts` failed with `Resource not accessible by integration` | Phase 2b declares `permissions: contents: write` only; the Issues API requires `issues: write` | Deferred — adding `issues: write` while the Layer 6 architectural fix is still open compounds blast radius (security review recommendation). Functional dispatch unaffected; only operator telemetry degraded | Tracked as Issue #311 |

**Phase 2b fleet-state input handling (added in `49a6d52` and tightened in the cross-functional remediation pass):**

- `pending_date` (line 3 of `.fleet/.pending_session`): validated against `^[0-9]{4}_[0-9]{2}_[0-9]{2}$` before any path construction. CRLF stripped via `tr -d '\r'`.
- `pending_base` (line 2): pinned to exactly `main`. The `--` git option terminator on the downstream `git pull` blocks flag injection but does NOT block valid-but-hostile refspecs pointing at fast-forward-descendant attacker branches; the hard pin closes that class entirely. Documented as a HIGH-confidence security HIGH in the cross-functional review.
- `pending_session_id` (line 1): propagated as the dispatch session ID; no path construction so no shape check beyond CRLF stripping.
- `${{ steps.detect.outputs.detected_date }}`: routed through `env: DETECTED_DATE` rather than inline `${{...}}` in `run:` blocks, per the same shell-injection guard as Amendment 1's `FLEET_BASE_BRANCH` / `FLEET_PENDING_DATE` pattern.

### Cap-of-1-inProgress hypothesis (Layer 1) — status

Tentative as of 2026-04-29. The hypothesis was that Jules's API rejects new `jules.run()` calls with `FAILED_PRECONDITION` whenever ANY inProgress session exists in the account. Subsequent observations on 2026-06-20 contradicted this: planning runs at 03:24, 05:10, and 08:53 UTC all succeeded with multiple inProgress sessions present (the 18:03 dispatch alone created 6). Reclassifying as "unconfirmed, deprioritized" — no further action unless the failure recurs. If the recurrence pattern surfaces, the recommended next step is to codify a fleet-plan preflight that probes and archives any inProgress session older than 24 hours before invoking `jules.run()`.

### What did not change

- The three-phase fleet orchestration pattern (Plan → Dispatch → Merge) is unchanged at the conceptual level — Phase 2 was split into 2a and 2b internally but Plan-Dispatch-Merge is still the operator-facing model.
- The Jules SDK usage contract is unchanged.
- Phase 3 merge contract (`fleet-merge.yml` via `workflow_run`) is unchanged. `workflow_run` triggers fire from runs authored by `GITHUB_TOKEN`, so Phase 3 does not suffer the Layer 6 suppression — confirmed during the same diagnostic pass.
- Phase 1 (`fleet-plan.yml`) is unchanged.
- Security conventions from Amendment 1 (injection guard, step-scoped secrets, etc.) are unchanged and extended (PENDING_BASE pin, CRLF stripping, env-routing for the detect step's `${{ steps... }}` interpolations).
- The Phase 2b `workflow_dispatch` escape hatch remains available while Issue #310 is only partially complete; absent or invalid GitHub App credentials intentionally fall back to `GITHUB_TOKEN` and preserve the manual recovery path.

## Amendment 4

### Date
2026-06-21

### What changed

Issue #328 added fail-closed sanity checks for the Type C hallucination class
identified in Issue #325: Jules can report successful writes even when the
actual PR diff is 0 added files, 0 deleted files, and 0 changed paths. The
original observed trap was Layer 2 from Amendment 3 (`.gitignore` suppressing
`.fleet/<date>/issue_tasks.{md,json}`), but the defense is intentionally broader
than that single path.

**Prompt-level pre-push guard (defense in depth):**

- `scripts/fleet/preMergeSanityCheck.ts` is a read-only local gate that checks
  staged changes with `git diff --cached --name-status --no-renames -z`.
- `fleet-plan.ts` appends a mandatory command block to the Jules planning prompt
  requiring `.fleet/<date>/issue_tasks.md` and
  `.fleet/<date>/issue_tasks.json` to be staged, with no unexpected staged paths.
- `fleet-dispatch.ts` appends the same guard in open-scope mode for per-task
  PRs: at least one file must be staged, but the path set is not constrained
  because each task owns its own files from the manifest.

**Deterministic pre-merge enforcement:**

- Phase 2a (`fleet-dispatch.yml`) now inspects the planning PR file list through
  the GitHub API before queuing auto-merge. It fails closed when the PR file list
  is empty, when either planning artifact is missing, when any unexpected path is
  present, or when GitHub reports a `removed` / `renamed` file status.
- Phase 3 (`fleet-merge.ts`) checks each per-task PR's file list via
  `scripts/fleet/github/pr-file-sanity.ts` before waiting for CI or merging. It
  fails closed when the PR has a 0/0/0 file list or when the GitHub API response
  cannot be inspected.

### What did not change

- Jules still owns branch creation and PR creation. The prompt-level guard is
  the only point that can run before Jules pushes its branch; the workflow/API
  gates provide deterministic enforcement before merge.
- The Phase 2 split and the Phase 2b `workflow_dispatch` escape hatch from
  Amendment 3 remain unchanged.
- The per-task PR path remains open-scope: only non-empty diff is enforced,
  because task-specific expected file paths come from each task prompt rather
  than a single global path list.

## References

- `scripts/fleet/` — TypeScript/Bun fleet orchestration scripts
- `scripts/fleet/preMergeSanityCheck.ts` — staged-diff sanity helper and prompt block generator
- `scripts/fleet/github/pr-file-sanity.ts` — PR file-list sanity helper for Phase 3 merge gating
- `scripts/fleet/jules-account-probe.ts` — read-only Jules account health diagnostic
- `scripts/fleet/archive-stale-sessions.ts` — stale session archive with deny-by-default scoping
- `.github/workflows/fleet-plan.yml` — Phase 1 scheduled planning pipeline
- `.github/workflows/fleet-dispatch.yml` — Phase 2a queue-auto-merge pipeline (triggered by plan PR opened)
- `.github/workflows/fleet-dispatch-after-merge.yml` — Phase 2b detect + dispatch pipeline (triggered by push to main or workflow_dispatch)
- `.github/workflows/fleet-merge.yml` — sequential PR merge pipeline (Phase 3, via workflow_run)
- `.github/workflows/jules-account-probe.yml` — read-only account diagnostic workflow
- `.github/workflows/jules-archive-stale.yml` — archive workflow (manual dispatch)
- `.github/instructions/fleet-operations.instructions.md` — operator runbook
- `docs/decisions/ADR-004-split-ci-workflow-governance.md` — CI trust model that fleet PRs enter
- `docs/decisions/ADR-015-extended-ci-trust-model.md` — CI-4/CI-5 context
- `@google/jules-sdk` — Jules API client
