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
  --source-filter sources/github/wryenmeek/knowledgebase
```

This prints a JSON envelope with `candidates` (what would be archived) but
makes no actual changes.

### Step 4: Apply the archive

Once the dry-run output looks correct, add `--apply`:

```bash
bun run archive-stale-sessions.ts \
  --older-than-days 3 \
  --state inProgress \
  --source-filter sources/github/wryenmeek/knowledgebase \
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
Filter by source to avoid accidentally archiving sessions from other repos:

```bash
--source-filter sources/github/wryenmeek/knowledgebase
```

Or in code:
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
| `source_filter` | `""` | no | Source scope (e.g. `sources/github/wryenmeek/knowledgebase`) |
| `apply` | `false` | no | Set to `true` to archive; default is dry-run |

All inputs are routed through `env:` blocks before use in `run:` steps to
prevent shell injection (per the GitHub Actions shell injection guard in
`.github/copilot-instructions.md`).

---

## Escalation path

If archiving zombie sessions does not free quota or fleet dispatch continues
to fail:

1. Check the Jules web UI for account-level quota information.
2. Check if `JULES_API_KEY` is valid and has not expired.
3. See issue **wryenmeek/knowledgebase#82** for the full root-cause analysis
   of the original saturation event.
