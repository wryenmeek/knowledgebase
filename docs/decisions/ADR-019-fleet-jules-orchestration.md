# ADR-019: Jules-based fleet orchestration for parallel issue-to-PR dispatch

## Status
Accepted

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

### Phase 1 — Plan (`fleet-plan.ts`, triggered by `fleet-dispatch.yml`)

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

### Phase 3 — Merge (`fleet-merge.ts`, triggered after dispatch completes)

PRs are merged sequentially in dependency order. If a merge fails (conflict
with a previously merged PR), the task is re-dispatched as a new Jules session
with the updated base branch. This re-dispatch loop runs up to a configurable
limit before the task is flagged for human review.

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

## References

- `scripts/fleet/` — TypeScript/Bun fleet orchestration scripts
- `.github/workflows/fleet-dispatch.yml` — plan + dispatch pipeline
- `.github/workflows/fleet-merge.yml` — sequential PR merge pipeline
- `docs/decisions/ADR-004-split-ci-workflow-governance.md` — CI trust model that fleet PRs enter
- `docs/decisions/ADR-015-extended-ci-trust-model.md` — CI-4/CI-5 context
- `@google/jules-sdk` — Jules API client
