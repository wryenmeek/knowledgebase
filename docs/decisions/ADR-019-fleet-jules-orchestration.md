# ADR-019: Jules-based fleet orchestration for parallel issue-to-PR dispatch

## Status
Accepted — amended in-place: Phase 3 merge trigger changed to event-driven and security hardened (see § Amendment)

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

## References

- `scripts/fleet/` — TypeScript/Bun fleet orchestration scripts
- `.github/workflows/fleet-plan.yml` — Phase 1 scheduled planning pipeline
- `.github/workflows/fleet-dispatch.yml` — Phase 2 dispatch pipeline (triggered by plan PR merge)
- `.github/workflows/fleet-merge.yml` — sequential PR merge pipeline
- `docs/decisions/ADR-004-split-ci-workflow-governance.md` — CI trust model that fleet PRs enter
- `docs/decisions/ADR-015-extended-ci-trust-model.md` — CI-4/CI-5 context
- `@google/jules-sdk` — Jules API client
