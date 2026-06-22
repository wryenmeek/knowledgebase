---
applyTo: scripts/fleet/**
---

# Fleet Operations Runbook

This runbook covers operational diagnosis and remediation of Jules account issues,
including session-cap saturation events. Tools are in `scripts/fleet/`.

## Quick reference

| Script | Purpose |
|---|---|
| `jules-account-probe.ts` | Read-only account health snapshot |
| `archive-stale-sessions.ts` | Bulk-archive zombie/stale sessions |
| `fleet-submit-prs.ts` | Un-stick `awaitingUserFeedback` Jules sessions by submitting PRs on their behalf |

---

## Diagnosing a session-cap saturation event

When Jules fleet dispatch fails with `FAILED_PRECONDITION` or sessions stop
being created, the most common cause is session-cap saturation — the account
has too many active sessions consuming quota.

### Step 1: Run the account probe

```bash
cd scripts/fleet
export JULES_API_KEY=<your-key>
bun run jules-account-probe.ts | tee /tmp/probe.json
```

Or trigger the GitHub Actions workflow manually:
**Actions → Jules Account Probe → Run workflow**

The probe outputs a JSON envelope with:
- `sources` — all GitHub repositories connected to the account
- `sessionsBySource` — active/inProgress session counts per source
- `totals.activeSessions` — total sessions consuming quota
- `totals.inProgressSessions` — total sessions in `inProgress` state

### Step 2: Identify zombie sessions

Look for `inProgress` sessions with large `ageHuman` values in
`sessionsBySource[*].inProgressAges`. Sessions older than a few days are
likely stuck (zombie sessions).

```bash
# Find all inProgress sessions older than 3 days from the probe output:
cat /tmp/probe.json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for s in data.get('sessionsBySource', []):
    for age_entry in s.get('inProgressAges', []):
        print(age_entry['sessionId'], age_entry['ageHuman'], s['sourceName'])
"
```

### Step 3: Dry-run the archive command

**Always dry-run first** to confirm the filter selects only the sessions you
intend to archive:

```bash
bun run archive-stale-sessions.ts \
  --older-than-days 3 \
  --state inProgress \
  --repo current
```

This prints a JSON envelope with `candidates` (what would be archived) but
makes no actual changes. Dry-run does not require a source scope, but always
specify one anyway to confirm the right sessions are selected.

### Step 4: Apply the archive

Once the dry-run output looks correct, add `--apply`. Source scope is
**required** with `--apply` — omitting it exits non-zero:

```bash
# Archive sessions for this repo only (recommended):
bun run archive-stale-sessions.ts \
  --older-than-days 3 \
  --state inProgress \
  --repo current \
  --apply

# To scope to an explicit source ID instead of the shorthand:
bun run archive-stale-sessions.ts \
  --older-than-days 3 \
  --state inProgress \
  --source-filter sources/github/wryenmeek/knowledgebase \
  --apply

# To archive across all sources on the account (use with care):
bun run archive-stale-sessions.ts \
  --older-than-days 3 \
  --repo all \
  --apply
```

The output `archived` array confirms what was archived. Any per-session
errors appear in the `errors` array and do not abort the run.

### Step 5: Re-run the probe to confirm quota freed

```bash
bun run jules-account-probe.ts
```

`totals.activeSessions` should drop after archiving zombie sessions.

---

## Jules SDK gotchas

### There is no "cancel" endpoint — use archive

The Jules SDK has **no cancel endpoint**. The only way to remove a running
session from the active session list is to archive it:

```typescript
await jules.session(sessionId).archive();
```

Archived sessions are not deleted; they are still accessible by ID and can be
unarchived with `jules.session(id).unarchive()`. Archiving is the correct
remediation for zombie sessions.

### SDK singleton — never use a constructor

Per repo convention (`.github/copilot-instructions.md` §"Jules SDK and session
management"), always use the pre-built singleton:

```typescript
import { jules } from '@google/jules-sdk';
// jules is ready immediately; JULES_API_KEY is read from env automatically.
```

Never use `new Jules()`, `Jules({ apiKey })`, or `jules.createSession()`.

### Scope session iteration to the target repo

`jules.sessions()` returns sessions across **all** repositories on the account.
The archive tool enforces source scoping for `--apply` (deny-by-default):

```bash
# Shorthand for this repo:
--repo current

# Explicit source ID:
--source-filter sources/github/wryenmeek/knowledgebase

# Account-wide explicit opt-in:
--repo all
```

In code:
```typescript
for await (const session of jules.sessions()) {
  if (session.sourceContext?.source !== 'sources/github/wryenmeek/knowledgebase') continue;
  // ...
}
```

---

## GitHub Actions workflows

### Jules Account Probe (`jules-account-probe.yml`)

**Trigger:** Manual (`workflow_dispatch` only — no schedule)

Runs `jules-account-probe.ts` and uploads the JSON output as a workflow
artifact named `jules-account-probe-<run_id>`.

Uses `JULES_API_KEY` as a step-level secret binding (not job-level, per the
step-scoped secret binding rule).

### Jules Archive Stale (`jules-archive-stale.yml`)

**Trigger:** Manual (`workflow_dispatch` only)

**Inputs:**
| Input | Default | Required | Description |
|---|---|---|---|
| `state` | `inProgress` | no | State filter |
| `older_than_days` | — | **yes** | Minimum age in days (required to prevent mass-archive) |
| `source_filter` | `sources/github/wryenmeek/knowledgebase` | no (but required with `apply=true`) | Source scope. Required when `apply=true`; the script exits non-zero if apply=true and this is empty. Surrounding whitespace is trimmed; whitespace-only values are rejected with `--source-filter requires a non-empty value` (PR #315). |
| `apply` | `false` | no | Set to `true` to archive; default is dry-run |

All inputs are routed through `env:` blocks before use in `run:` steps to
prevent shell injection (per the GitHub Actions shell injection guard in
`.github/copilot-instructions.md`).

**Runtime gates (added 2026-06-20 in PR #312 + v-sec follow-up):**

- **Environment approval (apply only):** when `apply=true`, the `archive` job
  runs inside the `jules-archive-approval` GitHub environment and is blocked
  until a configured reviewer approves the deployment. Dry-runs (`apply=false`,
  the default) skip the environment entirely. The conditional expression is
  `${{ inputs.apply && 'jules-archive-approval' || '' }}` — note the
  comparison is **boolean-truthy**, NOT `inputs.apply == 'true'` (that earlier
  form silently never engaged because the GH Actions expression evaluator
  type-mismatch coerced the string `'true'` to NaN when comparing against the
  boolean input, so the ternary always picked the empty branch). Configure
  reviewers in repo Settings → Environments → `jules-archive-approval`.

- **Concurrency partitioning by input:** the job uses
  `group: jules-archive-stale-${{ inputs.apply }}` with
  `cancel-in-progress: false`. Dry-run and apply requests land in separate
  queues (`...-stale-false` and `...-stale-true`), so a long-running dry-run
  does not delay an apply. Successive runs with the same `apply` value queue
  rather than cancel each other. **Intentional asymmetry:** dry-run can run
  concurrently with an in-flight apply (the dry-run output may list sessions
  the apply has already archived — operational TOCTOU window, acceptable
  because dry-run does not mutate). If strict mutual exclusion is needed,
  drop the `${{ inputs.apply }}` suffix from the group key.

---

### Fleet Dispatch After Merge (`fleet-dispatch-after-merge.yml`) — operator escape hatch

**Trigger:** `push` to `main` (path-filtered to `.fleet/*/issue_tasks.json`) **or** `workflow_dispatch`.

The `push` trigger is **suppressed** when the planning PR is merged via
`GITHUB_TOKEN` (today's state — see Issue #310). This is documented GitHub
Actions behavior: events authored by `GITHUB_TOKEN` do not create
downstream workflow runs except for `workflow_dispatch` and
`repository_dispatch`. Since Phase 2a queues `gh pr merge --auto` using
the default `GITHUB_TOKEN`, the resulting merge commit does not fire
Phase 2b's push trigger.

**Recovery (current happy path until Issue #310 lands):**

```bash
gh workflow run fleet-dispatch-after-merge.yml --ref main
```

Run this after the planning PR auto-merges and CI-2 finishes. The
workflow's detect step branches on `github.event_name`:

- `push` event → original `git diff HEAD~1 HEAD` detection (unchanged)
- `workflow_dispatch` event → resolve the artifact via fleet-state's
  `pending_date` (since intervening commits may push the artifact outside
  the HEAD~1 diff window)

**Fail-closed guards** (in order, each emits an `is_planning_merge=false`
output and exits 0 rather than raising):

1. No `fleet-state` branch → skip
2. No `.pending_session` in `fleet-state` → skip
3. `pending_date` (line 3) is empty or doesn't match `^[0-9]{4}_[0-9]{2}_[0-9]{2}$` → refuse (anchored shape check is load-bearing)
4. `.fleet/<pending_date>/issue_tasks.json` not present on `main` → skip
5. `pending_base` (line 2) is not exactly `main` → refuse (closes the refspec-substitution class; see ADR-019 Amendment 3)

**Permanent fix:** Issue #310 — switch Phase 2a to a GitHub App
installation token (`GH_APP_ID` / `GH_APP_PRIVATE_KEY`). App-token-authored
pushes are not treated as `GITHUB_TOKEN` events, so Phase 2b's push trigger
fires normally and the manual `gh workflow run` step becomes optional
(retained as escape hatch only).

**Telemetry note (Issue #311):** the dispatch step's per-task tracker
comments fail with `Resource not accessible by integration` because
the workflow declares only `permissions: contents: write` (not
`issues: write`). Functional dispatch is unaffected — Jules sessions
spawn normally, and the session→task mapping is written to
`.fleet/<date>/sessions.json` for offline correlation. Issue #311 will
add `issues: write` after Issue #310 lands (granting it earlier would
compound the blast radius of any unfixed Layer 6 issue).

---

## Escalation path

If archiving zombie sessions does not free quota or fleet dispatch continues
to fail:

1. Check the Jules web UI for account-level quota information.
2. Check if `JULES_API_KEY` is valid and has not expired.
3. See issue **wryenmeek/knowledgebase#82** for the full root-cause analysis
   of the original saturation event.
