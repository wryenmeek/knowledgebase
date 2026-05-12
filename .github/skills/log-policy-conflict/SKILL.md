---
name: log-policy-conflict
description: Records contradiction or policy-conflict outcomes in an append-only, governance-safe form. Use when evidence or editorial policy forces an explicit escalation record instead of a silent overwrite.
---

# Log Policy Conflict

## Overview

Use this skill when policy review finds a contradiction that must remain visible.
In MVP it is a doc-only workflow that prepares append-only conflict records and
routes escalation cleanly instead of allowing silent content replacement or lost
history.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Conflict documentation and handoff only. Do not edit
  history destructively, collapse conflicting evidence silently, or create a new
  logging runtime.

## When to Use

- Policy review identifies contradictory evidence that cannot be resolved safely
- A merge or update would erase important disagreement or ambiguity
- A durable state change needs an append-only conflict record
- Human stewardship must review a high-impact contradiction
- Another governance lane needs a stable escalation artifact

## Contract

- Input: a policy conflict with affected pages, evidence summary, and blocking
  reason
- Output: an append-only conflict record proposal plus the downstream escalation
  target
- Persistence rule: conflict history belongs in the existing append-only
  knowledgebase log and governed artifacts
- Handoff rule: unresolved conflicts route back through governance or human
  stewardship before any durable write follow-up continues

## Assertions

- Conflict records preserve both the issue and why it blocks safe progress
- Append-only discipline is maintained for `wiki/log.md`
- Contradictions are not downgraded to advisory noise when they change meaning or
  policy outcome
- The skill does not authorize direct page rewrites to "fix" the conflict
- Missing evidence or unclear ownership remains escalated

## Procedure

### Step 1: Identify the policy conflict

Capture the affected pages or proposals, the contradictory evidence or policy
rule, and why the contradiction matters.

### Step 2: Decide whether logging is required

If the conflict changes meaning, blocks publication, or requires human review,
prepare an append-only record instead of forcing the change through.

### Step 3: Draft the record

Write the smallest useful conflict summary, including what is blocked, what
remains unresolved, and who must review it next.

### Step 4: Route the escalation

Send the conflict record to the appropriate governance lane or human steward and
keep downstream wiki-writing work closed until the conflict is resolved.

## Boundaries

- Do not rewrite existing log history in place
- Do not remove contradiction context to make automation appear successful
- Do not create a second policy-conflict ledger in MVP
- Do not reopen downstream wiki-writing lanes before governance resolves the
  conflict

## Verification

- [ ] The conflict record explains what is contradictory and why it blocks work
- [ ] Append-only treatment of `wiki/log.md` is preserved
- [ ] Escalation ownership is named
- [ ] No silent overwrite or destructive history edit is introduced
- [ ] Downstream durable follow-up remains gated on governance resolution

## References

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`docs/ideas/wiki-curation-agent-framework.md`](../../../docs/ideas/wiki-curation-agent-framework.md)
- [`raw/processed/SPEC.md`](../../../raw/processed/SPEC.md)
- [`wiki/log.md`](../../../wiki/log.md)
