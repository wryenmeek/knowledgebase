# Fleet Orchestration (`scripts/fleet/`)

Parallel Jules-based issue dispatch for the knowledgebase framework. Four scripts implement a three-phase Plan → Dispatch → Merge pipeline.

See ADR-019 for the full architectural rationale.

## Prerequisites

- [Bun](https://bun.sh) runtime (not Node/npm)
- `JULES_API_KEY` — Jules API key
- `GITHUB_TOKEN` — GitHub personal access token with repo scope

## Install

```bash
bun install
```

Do not use `npm install`. This project requires Bun.

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `JULES_API_KEY` | Yes | Jules API key. Read automatically by the SDK. |
| `GITHUB_TOKEN` | Yes | GitHub token for Octokit calls. |
| `FLEET_MAX_PARALLEL` | No | Maximum concurrent Jules sessions during dispatch (default: unbounded). |
| `FLEET_BASE_BRANCH` | No | Base branch for fleet PRs (defaults to current branch). |

## Scripts

### `bun analyze` — inspect open issues (read-only)

```bash
bun analyze
```

Fetches open issues from the repository and prints a structured analysis without starting any Jules sessions. Use this locally before committing to a plan run to understand issue volume and distribution.

No API keys required beyond `GITHUB_TOKEN`. No sessions are created. Safe to run at any time.

### `bun plan` — Phase 1: create task manifest

```bash
bun plan
```

Starts a Jules planning session (`jules.session()`, `requirePlanApproval: true`), then creates a PR containing a task manifest at `.fleet/<date>/issue_tasks.json`. The manifest maps issues to Jules tasks and documents file ownership.

**Human review required before proceeding to dispatch.** Review the manifest PR, validate task assignments, then approve and merge before running `bun dispatch`.

### `bun dispatch` — Phase 2: parallel Jules sessions

```bash
bun dispatch
```

Reads the merged planning PR manifest. Validates file ownership: tasks that would touch the same files are routed to the same Jules session to prevent conflicts. Dispatches remaining tasks as parallel Jules sessions using `jules.run()` (AutomatedSession — auto-approve, auto-PR).

Concurrency is controlled by `FLEET_MAX_PARALLEL`. Each session produces its own PR.

### `bun merge` — Phase 3: ordered merge

```bash
bun merge
```

Merges dispatch PRs in dependency order. On merge conflict, re-dispatches the affected session (up to a configurable retry limit). Conflict-free PRs are merged in sequence.

## Three-phase workflow

```
bun analyze        # inspect — no side effects
bun plan           # Phase 1 — creates manifest PR, waits for human review
# (review and merge manifest PR)
bun dispatch       # Phase 2 — parallel Jules sessions, one PR per task
bun merge          # Phase 3 — ordered merge with conflict re-dispatch
```

## Jules SDK usage

This project uses the `@google/jules-sdk` singleton. Never use a constructor.

```typescript
import { jules } from '@google/jules-sdk';

// For CI dispatch (auto-approve, auto-PR):
const session = await jules.run({ ... });

// For planning (requirePlanApproval: true by default):
const session = await jules.session({ ... });

// Iterate all sessions:
for await (const s of jules.sessions()) { ... }
```

`JULES_API_KEY` is read from the environment automatically. Do not pass it explicitly.

## CI integration

Fleet is orthogonal to the Python write-surface matrix. Fleet-produced PRs re-enter the repository as normal PRs and go through the standard CI review pipeline (CI-1 through CI-5). The fleet scripts themselves are not covered by `pytest` — run `bun build` separately after any TypeScript changes.

## Build verification

```bash
bun build fleet-plan.ts fleet-dispatch.ts fleet-merge.ts
```

Run this after every TypeScript edit. `pytest` passing does **not** mean TypeScript is clean.

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `@google/jules-sdk` | `^0.1.0` | Jules session management |
| `octokit` | `^4.1.0` | GitHub API |

## Files

| File | Package script | Phase | Description |
|---|---|---|---|
| `fleet-analyze.ts` | `bun analyze` | — | Read-only issue inspection |
| `fleet-plan.ts` | `bun plan` | 1 | Planning session, manifest PR |
| `fleet-dispatch.ts` | `bun dispatch` | 2 | Parallel Jules dispatch |
| `fleet-merge.ts` | `bun merge` | 3 | Ordered merge with re-dispatch |
