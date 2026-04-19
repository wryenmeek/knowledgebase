---
name: jules-session-triage
description: Triages Jules sessions, sends feedback to stuck sessions before a PR is submitted, and reviews Jules PRs. Use when a Jules session is not making progress, is waiting for input, has failed, or when a Jules-authored PR needs review feedback routed back to the session.
---

# Jules Session Triage

## Overview

Structured workflow for inspecting live Jules sessions, unblocking stuck sessions with targeted feedback, and closing the feedback loop on Jules-authored PRs. Jules operates in an async cloud environment — sessions can stall without visible errors. This skill provides the diagnostic and intervention patterns needed to keep sessions moving.

## When to Use

- A Jules session is in `awaitingPlanApproval` or `awaitingUserFeedback` state and has been waiting more than a few minutes
- A session has been `inProgress` for more than 90 minutes without a PR
- Fleet Dispatch ran but no PRs appeared in the repository
- A Jules PR is open and needs code review feedback sent back to the session
- CI signals a session ID that never produced a PR
- You want a sweep of active sessions to catch anything needing attention

---

## SDK Usage

This repository uses the `jules` singleton exported by `@google/jules-sdk`. It reads `JULES_API_KEY` from the environment automatically.

```typescript
import { jules } from '@google/jules-sdk';
// jules is ready to use — no constructor call needed.
// All scripts set JULES_API_KEY in the environment before running.
```

---

## Session States Reference

Every session has a `state` field and a separate `archived` boolean. These are independent.

| State | Meaning | Appropriate action |
|-------|---------|-------------------|
| `queued` | Waiting for a worker slot | Wait; resolves in seconds. Only escalate if stuck > 10 minutes. |
| `planning` | Generating a plan | Wait; can take 5–20 minutes. |
| `awaitingPlanApproval` | Plan ready, paused for review | This is **expected**, not a stall. Approve or give plan feedback. |
| `awaitingUserFeedback` | Blocked, needs human input | Send targeted feedback to unblock. |
| `inProgress` | Actively working | Wait. Inspect snapshot only if `inProgress` for > 90 minutes. |
| `paused` | Manually paused | Inspect why before acting. If appropriate, try `session.send()`. |
| `failed` | Terminal failure | Inspect the `sessionFailed` activity for the reason; consider redispatch. |
| `completed` | Done | Check `outputs` for the PR URL. Nothing to do unless the PR needs review. |

> **Do not treat `awaitingPlanApproval` or `awaitingUserFeedback` as stalls** — they are designed waiting states. A session in these states for less than 24 hours is normal for fleet workflows.

---

## Phase 1: List and Identify Sessions Needing Attention

```typescript
import { jules } from '@google/jules-sdk';

const ACTIVE_STATES = ['queued', 'planning', 'awaitingPlanApproval', 'awaitingUserFeedback', 'inProgress', 'paused'];
const STALL_MINUTES: Partial<Record<string, number>> = {
  queued: 10,
  planning: 30,
  inProgress: 90,
  paused: 60,
};

for await (const session of jules.sessions()) {
  if (session.archived || !ACTIVE_STATES.includes(session.state)) continue;

  const staleMs = Date.now() - new Date(session.updateTime).getTime();
  const staleMinutes = Math.round(staleMs / 60000);
  const threshold = STALL_MINUTES[session.state];

  if (threshold === undefined || staleMinutes < threshold) {
    // awaitingPlanApproval / awaitingUserFeedback: always show, not time-gated
    if (!['awaitingPlanApproval', 'awaitingUserFeedback'].includes(session.state)) continue;
  }

  console.log(`[${session.state}] ${session.id} (${staleMinutes}m ago) — ${session.title}`);
  console.log(`  ${session.url}`);
}
```

### REST API fallback (no SDK available)

```bash
curl "https://jules.googleapis.com/v1alpha/sessions" \
  -H "X-Goog-Api-Key: $JULES_API_KEY" \
  | jq '.sessions[] | select(.archived != true) | {id, state, title, updateTime}'
```

---

## Phase 2: Inspect a Session

Before intervening, take a read-only snapshot to understand what has happened.

```typescript
const client = jules.session(SESSION_ID);    // rehydrate by ID
const snapshot = await client.snapshot({ activities: true });

// Timeline
for (const entry of snapshot.timeline) {
  console.log(`[${entry.time}] ${entry.type}: ${entry.summary}`);
}

// Health signals
console.log('Completion attempts:', snapshot.insights.completionAttempts);
console.log('Plan regenerations:', snapshot.insights.planRegenerations);
console.log('Failed commands:', snapshot.insights.failedCommands.length);

// What Jules last said
const lastAgentMsg = snapshot.activities.filter(a => a.type === 'agentMessaged').at(-1);
console.log('Last agent message:', lastAgentMsg?.message);
```

### Diagnosis table

| Signal | Likely cause | Intervention |
|--------|-------------|-------------|
| State `awaitingPlanApproval` | Intentional pause | Approve, or send plan feedback |
| State `awaitingUserFeedback` | Jules asked a question | Read last `agentMessaged`; answer it |
| `failedCommands.length > 3` | Jules stuck in a retry loop | Send a different approach |
| `completionAttempts > 2` | Repeated finish failures | Inspect failing step; send targeted fix |
| `planRegenerations > 1` | Original approach failed | Send revised scope/strategy |
| `inProgress` > 90 min, low activity | Silent hang | Try `session.ask()` for a status probe |

---

## Phase 3: Intervene in a Stuck Session

### Unblock `awaitingUserFeedback`

```typescript
const client = jules.session(SESSION_ID);
const info = await client.info();

if (info.state !== 'awaitingUserFeedback') {
  console.log('Session is not awaiting feedback, current state:', info.state);
} else {
  const snapshot = await client.snapshot({ activities: true });
  const question = snapshot.activities.filter(a => a.type === 'agentMessaged').at(-1)?.message;
  console.log('Jules asks:', question);

  await client.send(`
    Here is the clarification you need: [your answer].
    If still uncertain, take the simplest approach and document assumptions in code comments.
    Do not pause for further confirmation.
  `);
}
```

### Approve or redirect a pending plan (`awaitingPlanApproval`)

```typescript
const client = jules.session(SESSION_ID);
// waitFor() returns on any terminal state too, so always check actual state after
await client.waitFor('awaitingPlanApproval');
const info = await client.info();

if (info.state !== 'awaitingPlanApproval') {
  console.log('Session moved to:', info.state, '— check outputs or handle terminal state');
} else {
  // Option A: approve
  await client.approve();

  // Option B: request plan revision before approving
  await client.send(`
    Please revise the plan before I approve:
    - [specific constraint or change]
    Regenerate and I will review again.
  `);
}
```

### Redirect a looping session

When `failedCommands.length` is high or `completionAttempts > 2`:

```typescript
await client.send(`
  You appear to be stuck on [describe the specific blocker].
  Try a different approach:
  1. [Alternative strategy]
  2. If that doesn't work: [simpler fallback]
  If you cannot complete this task, open a PR with your best partial attempt
  and leave a comment explaining exactly what is blocked and why.
`);
```

### Check in on a long `inProgress` session

```typescript
const reply = await client.ask('What are you currently working on? Are you blocked on anything?');
console.log(reply.message);
```

### Handle a `paused` session

`paused` is a manual state. Do not blindly resume it — first read the last agent message to understand why it was paused. If the session needs input to continue, use `send()`. If it was paused by a human for a deliberate reason, escalate rather than resuming automatically.

---

## Phase 4: Giving Feedback on Jules PRs

Jules PRs are opened by `google-labs-jules[bot]` (or similar bot-suffix accounts matching the workflow's author filter). The PR body contains the Jules session URL, which includes the session ID.

### Step 1: Find Jules PRs

```bash
# By author (use the same filter as the fleet-dispatch workflow)
gh pr list --author "google-labs-jules[bot]" --state open --json number,title,headRefName,url

# Or search by session ID if you have it
gh pr list --search "in:body SESSION_ID" --json number,title,url
```

### Step 2: Extract the session ID from the PR

The PR body contains a Jules session URL in the format `https://jules.google.com/task/SESSION_ID`. Extract it:

```bash
SESSION_URL=$(gh pr view PR_NUMBER --json body -q '.body' | grep -oE 'https://jules\.google\.com/task/[A-Za-z0-9_-]+')
SESSION_ID=$(echo "$SESSION_URL" | sed 's|.*/||')
echo "Session ID: $SESSION_ID"
```

If the URL isn't in the body, check `.fleet/<date>/sessions.json` — see the fleet lookup section below.

### Step 3: Review the PR diff

```bash
gh pr diff PR_NUMBER
```

Apply the same review criteria as any other PR:
- Does the implementation match the task requirements in the PR description?
- Are files changed outside the task's expected scope?
- Are tests present, or is existing test coverage broken?
- Does the code follow repository conventions?

### Step 4: Route feedback back to the session

**Always send feedback to the Jules session, not only the GitHub PR.** Jules monitors its session, not the GitHub review thread.

First verify the session is still actionable before sending:

```typescript
import { jules } from '@google/jules-sdk';

const ACTIONABLE_STATES = ['awaitingUserFeedback', 'inProgress', 'awaitingPlanApproval', 'paused'];

const client = jules.session(SESSION_ID);
const info = await client.info();

if (!ACTIONABLE_STATES.includes(info.state)) {
  console.log(`Session ${SESSION_ID} is ${info.state} — cannot receive feedback. Consider redispatch.`);
} else {
  await client.send(`
    I reviewed PR #PR_NUMBER. Here is my feedback:

    REQUIRED before merge:
    - [file:line — what is wrong and why — what to do instead]

    Optional:
    - [suggestion and rationale]

    Please address required items and push an updated commit to the same branch.
  `);
}
```

### Step 5: Post a GitHub review for visibility

```bash
# Informational comment
gh pr review PR_NUMBER --comment \
  --body "Feedback sent to Jules session $SESSION_ID. Required changes: [summary]."

# Or block merge until Jules addresses it
gh pr review PR_NUMBER --request-changes \
  --body "[Summary — Jules has been notified via session $SESSION_ID]"
```

### Step 6: Merge when ready

```bash
gh pr merge PR_NUMBER --squash --auto
```

Or wait for Jules to push a revision before merging:

```typescript
// Only wait if the session is still active
const info = await client.info();
if (['inProgress', 'awaitingUserFeedback'].includes(info.state)) {
  const outcome = await client.result();
  console.log('Session finished:', outcome.state, outcome.pullRequest?.url);
}
```

---

## Fleet Pipeline Integration

In this repository, fleet sessions are tracked in `.fleet/<date>/sessions.json` (entries: `{ taskId, sessionId }`). Task metadata lives in `.fleet/<date>/issue_tasks.json` (tasks: `{ id, title, issues, prompt, ... }`). Join them on `taskId === id` to get full context.

### Find the latest fleet run date

```bash
ls -d .fleet/*/  | sort | tail -1
```

### Audit all sessions from a fleet run

```typescript
import { jules } from '@google/jules-sdk';
import sessionsData from './.fleet/2026_04_19/sessions.json' with { type: 'json' };
import tasksFile from './.fleet/2026_04_19/issue_tasks.json' with { type: 'json' };

const taskMap = new Map(tasksFile.tasks.map(t => [t.id, t]));

for (const entry of sessionsData) {
  const task = taskMap.get(entry.taskId);
  const client = jules.session(entry.sessionId);
  const info = await client.info();
  const prUrl = info.outputs.find(o => o.type === 'pullRequest')?.pullRequest.url ?? 'no PR yet';
  console.log(`[${info.state}] ${task?.title ?? entry.taskId} → ${prUrl}`);
}
```

### Go from a GitHub issue number to its session ID

```typescript
const issueNumber = 42;
const task = tasksFile.tasks.find(t => t.issues.includes(issueNumber));
const sessionEntry = sessionsData.find(s => s.taskId === task?.id);
const sessionId = sessionEntry?.sessionId;
```

### Handle a failed session: inspect and redispatch

```typescript
const client = jules.session(SESSION_ID);
const info = await client.info();

if (info.state === 'failed') {
  const snapshot = await client.snapshot({ activities: true });
  const failReason = snapshot.activities
    .filter(a => a.type === 'sessionFailed')
    .at(-1)?.reason ?? 'unknown';

  console.log(`Failed: ${failReason}`);
  await client.archive();  // remove from active list

  // To redispatch a single failed task, manually call jules.run() with the original
  // task prompt from issue_tasks.json (see the Escalation section for the full flow).
  // Do not rerun fleet-dispatch.ts — it redispatches all tasks, not just the failed one.
}
```

---

## Rate Limiting

- **Page session listings** — use `jules.sessions({ pageSize: 20 })` and process incrementally rather than loading all sessions at once.
- **Avoid per-session PR queries in a loop** — batch `gh pr list` calls or filter by known session IDs rather than querying GitHub for each session individually.
- **Back off on errors** — Jules API returns `429` on rate limit. Add a wait before retrying:

```typescript
async function withBackoff<T>(fn: () => Promise<T>, maxAttempts = 3): Promise<T> {
  for (let i = 0; i < maxAttempts; i++) {
    try { return await fn(); }
    catch (e: any) {
      if (e?.status !== 429 || i === maxAttempts - 1) throw e;
      await new Promise(r => setTimeout(r, 2000 * (i + 1)));
    }
  }
  throw new Error('unreachable');
}
```

---

## Feedback Quality Guidelines

Feedback sent to a session is Jules' only source of context correction. Make it actionable.

**Effective feedback:**
- Points to specific files and line numbers
- Explains *why* something is wrong, not just *what*
- Offers an alternative or a direction to explore
- Sets a clear success criterion ("the test `test_xyz` should pass")

**Ineffective feedback:**
- "This doesn't look right" (no specifics)
- "Try harder" (no direction)
- Instructions that require resources outside the repository (env vars, secrets, external APIs)

**Template for stuck sessions:**
```
Context: You are working on [task]. You are currently [state].

What I see: [last known activity / error / question Jules asked]

What I need: [specific answer OR revised direction]

Constraint: [what Jules must not touch]

Success: [concrete outcome — e.g., "tests pass", "PR opens against main with only X changed"]
```

---

## Escalation

If a session cannot be unblocked after two feedback rounds:

1. Archive the session: `await client.archive()`
2. Document the failure in `.fleet/<date>/sessions.json` (add `status: "abandoned"` and `failReason: "..."` fields)
3. Re-examine the original task prompt in `issue_tasks.json` — the prompt may be too ambiguous or too broad
4. Rewrite the task prompt and redispatch the **single task** manually:
   ```typescript
   import { jules } from '@google/jules-sdk';
   // Load the updated prompt from issue_tasks.json
   const run = await jules.run({
     prompt: updatedTaskPrompt,
     source: { github: 'owner/repo', baseBranch: 'main' },
   });
   console.log('New session:', run.id);
   ```
   Do not rerun `fleet-dispatch.ts` — it redispatches **all** tasks in `issue_tasks.json`, which would create duplicate sessions for unrelated tasks.

---

## Verification

After intervening in a session:

- [ ] Session state changed from the stuck state within 5 minutes of sending feedback
- [ ] Jules responded with an `agentMessaged` activity acknowledging the feedback
- [ ] If a PR was expected, it appears under `gh pr list --author "google-labs-jules[bot]"`
- [ ] PR diff is within the expected scope for the task
- [ ] Required review feedback has been addressed before merge
