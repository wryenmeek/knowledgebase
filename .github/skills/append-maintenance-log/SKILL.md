---
name: append-maintenance-log
description: Records a deterministic maintenance-event entry in wiki/log.md after a governed maintenance action completes. Use when maintenance-auditor or change-patrol needs to produce a traceable audit record for a completed maintenance state change.
---

# Append Maintenance Log

## Overview

This skill documents the audit-logging step specific to maintenance events. It is
the maintenance-arm counterpart to `log-ingest-event` — it delegates write authority
to `append-log-entry` and `scripts/kb/write_utils.py` under `wiki/.kb_write.lock`,
and records only real state changes. No maintenance log entry is written unless a
governed maintenance action has actually completed.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Delegates write to `append-log-entry` only. No additional
  write surface is opened.

## When to Use

- A maintenance action (supersede, archive, cross-reference repair) has completed
  under `policy-arbiter` clearance
- `maintenance-auditor` or `change-patrol` requires a traceability record for a
  completed maintenance state change
- An operator needs a deterministic audit trail for maintenance operations separate
  from ingest events

## Contract

- Input: a non-empty markdown bullet entry describing the completed maintenance action,
  plus confirmation that a real state change occurred
- Write target: `wiki/log.md` only, append-only, delegated through `append-log-entry`
- Handoff: log entry is the final step in a maintenance event sequence

## Assertions

- No log entry is written if no real state change occurred
- Entries must describe a completed maintenance action, not a proposal or finding
- The lock at `wiki/.kb_write.lock` must be held by the delegated writer before append
- This skill does not write to any path other than `wiki/log.md` (via `append-log-entry`)

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/decisions/ADR-005-write-lock-and-concurrency.md`
- `raw/processed/SPEC.md`
- `schema/governed-artifact-contract.md`
- `.github/skills/append-log-entry/SKILL.md`
- `scripts/kb/write_utils.py`
- `.github/agents/maintenance-auditor.md`
