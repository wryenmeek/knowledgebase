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
| `FLEET_MUTATION_MAX_ATTEMPTS` | No | Bounded Jules mutation attempts before terminal hard-fail (default: `3`, max: `5`). |
| `FLEET_MAX_RETRIES` | No | Merge conflict re-dispatch retries in `bun merge` (default: `2`; integer `0`–`10`). |
| `FLEET_ALLOW_NO_CHECKS` | No | Allow merge to proceed when PR has zero check runs (`false` by default; fail-closed). |
| `FLEET_PENDING_DATE` | No | Fleet date override (`YYYY_MM_DD`) so dispatch/merge can target a prior planning day. Invalid format fails preflight. |

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

Starts a Jules planning run (`jules.run()`) and creates a PR containing a task manifest at `.fleet/<date>/issue_tasks.json`. The manifest maps issues to Jules tasks and documents file ownership.

Review the manifest PR, validate task assignments, then merge before running `bun dispatch`.

### `bun dispatch` — Phase 2: parallel Jules sessions

```bash
bun dispatch
```

Reads the merged planning PR manifest. Validates file ownership and task-id uniqueness. If multiple tasks claim the same file, dispatch fails closed and requires manifest correction before continuing. Dispatches remaining tasks as parallel Jules sessions using `jules.run()` (AutomatedSession — auto-approve, auto-PR).

Concurrency is controlled by `FLEET_MAX_PARALLEL`. Each session produces its own PR.

### `bun merge` — Phase 3: ordered merge

```bash
bun merge
```

Merges dispatch PRs in manifest order (the planning phase is expected to output risk/dependency-safe ordering). On merge conflict, re-dispatches the affected session (up to a configurable retry limit). Conflict-free PRs are merged in sequence.

By default, merge fails closed when no check runs are reported for a PR. Set `FLEET_ALLOW_NO_CHECKS=true` only for repositories that intentionally run without CI checks.

If merge runs on a later day than plan/dispatch, set `FLEET_PENDING_DATE` to the planning date so it loads the correct `.fleet/<date>/` manifest and sessions mapping.
Both dispatch and merge validate this date strictly (`YYYY_MM_DD`) and fail closed if it would resolve outside the `.fleet/` root.

## Jules mutation failure diagnostics

Fleet mutation calls (`jules.run`) now use a deterministic contract:

- **first-pass target:** `diagnose_and_unblock`
- **post-retry behavior:** `retry_then_hard_fail_with_diagnostics`
- **diagnostic detail:** `sanitized_error_envelope`

Each failed attempt logs a sanitized JSON envelope with:

- `contract` (`first_pass_target`, `post_retry_behavior`, `diagnostic_detail`)
- `operation`
- `attempt` / `max_attempts`
- `classification` (`failed_precondition`, `auth`, `permission`, `rate_limit`, `network`, `unknown`)
- `retryable`, `retrying`, and `retry_delay_ms`
- `status_code`, `error_code`
- `message`, `hint`, and `root_cause_path`

### FAILED_PRECONDITION root-cause path

When Jules returns `FAILED_PRECONDITION` (HTTP 400):

1. Fleet preflight validates local configuration (`JULES_API_KEY`, `GITHUB_TOKEN`, repo format, base-branch format, base-branch visibility in local/origin refs, bounded retry config) before mutation attempts.
2. Retryable mutation failures run with deterministic bounded backoff (2s, 4s, 6s, capped at 8s) up to `FLEET_MUTATION_MAX_ATTEMPTS`; non-retryable classes fail immediately.
3. If retries are exhausted, Fleet exits fail-closed with a terminal `sanitized_error_envelope` for operator escalation (without secrets or raw auth payloads).
4. Use `hint` and `root_cause_path` from the terminal envelope as the canonical troubleshooting checklist before escalation.

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

// For CI dispatch and fleet planning (auto-approve, auto-PR):
const session = await jules.run({ ... });

// For manual human-in-the-loop planning:
const sessionClient = await jules.session({ ... });

// Iterate all sessions:
for await (const s of jules.sessions()) { ... }
```

`JULES_API_KEY` is read from the environment automatically. Do not pass it explicitly.

## CI integration

Fleet is orthogonal to the Python write-surface matrix. Fleet-produced PRs re-enter the repository as normal PRs and are evaluated by the repository's required PR checks (primarily CI-2 diagnostics plus branch-protection gates; other CI lanes are trigger-dependent). The fleet scripts themselves are not covered by `pytest` — run `bun build` separately after any TypeScript changes.

## Build verification

```bash
bun build fleet-analyze.ts fleet-plan.ts fleet-dispatch.ts fleet-merge.ts --target bun --outdir dist
```

Run this after every TypeScript edit. `pytest` passing does **not** mean TypeScript is clean.

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `@google/jules-sdk` | `^0.1.0` | Jules session management |
| `octokit` | `^4.1.0` | GitHub API |
| `find-up` | `^7.0.0` | Repository root discovery |

## Files

| File | Package script | Phase | Description |
|---|---|---|---|
| `fleet-analyze.ts` | `bun analyze` | — | Read-only issue inspection |
| `fleet-plan.ts` | `bun plan` | 1 | Planning session, manifest PR |
| `fleet-dispatch.ts` | `bun dispatch` | 2 | Parallel Jules dispatch |
| `fleet-merge.ts` | `bun merge` | 3 | Ordered merge with re-dispatch |
| `jules-account-probe.ts` | — | ops | Read-only Jules account health diagnostic |
| `archive-stale-sessions.ts` | — | ops | Bulk-archive stale/zombie sessions |

### Operational scripts

See `.github/instructions/fleet-operations.instructions.md` for the full
operations runbook, including step-by-step diagnosis for session-cap saturation
events.

#### `jules-account-probe.ts` — account health snapshot (read-only)

```bash
bun run jules-account-probe.ts
```

Surfaces source/session/quota state for the Jules account. Outputs a structured
JSON envelope with: registered sources, active/inProgress session counts per
source, ages of `inProgress` sessions, and account totals. No side effects.

Requires `JULES_API_KEY`. Also available as a GitHub Actions workflow:
**Actions → Jules Account Probe**.

#### `archive-stale-sessions.ts` — bulk archive zombie sessions

```bash
# Dry-run (default): shows what would be archived, no side effects
bun run archive-stale-sessions.ts --older-than-days 7 --state inProgress

# Apply: actually archive
bun run archive-stale-sessions.ts --older-than-days 7 --apply

# Scope to a specific repo source
bun run archive-stale-sessions.ts \
  --older-than-days 3 \
  --state inProgress \
  --source-filter sources/github/wryenmeek/knowledgebase \
  --apply
```

Flags:
- `--older-than-days N` — **required**; minimum age in days (no default to prevent mass-archive)
- `--state <state>` — session state filter (default: `inProgress`)
- `--source-filter <source-id>` — optional; scope to one source
- `--apply` — perform real archive calls; omit for dry-run

Uses `jules.session(id).archive()` per SDK pattern (SDK over REST for mutations).
NOTE: Jules has no cancel endpoint; archive is the correct removal mechanism.

Also available as a GitHub Actions workflow: **Actions → Jules Archive Stale Sessions**.

### Fleet helper modules (`scripts/fleet/github/`)

- `mutation-diagnostics.ts` — fail-closed preflight, bounded retry classification, sanitized terminal envelopes.
- `retry-config.ts` — bounded re-dispatch retry parsing/validation.
- `ci-checks.ts` and `merge-ci.ts` — check-run evaluation plus CI polling behavior used by merge.
- `session-matching.ts` and `merge-runtime.ts` — deterministic PR/session matching and redispatch state transitions.
- `fleet-paths.ts` — `.fleet/<date>` path resolver with strict `YYYY_MM_DD` validation and boundary enforcement.
