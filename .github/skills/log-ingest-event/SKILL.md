---
name: log-ingest-event
description: Records a deterministic state-change entry in wiki/log.md after a governed ingest operation completes. Use when an ingest or write step has produced a real state change that must be traceable in the append-only audit log.
---

# Log Ingest Event

## Overview

This skill documents the audit-logging step that must follow any state-changing ingest
or write operation. It delegates to `append-log-entry` and `wiki/log.md` — which is
the append-only, commit-visible audit trail for governed state changes. No log entry
should be written unless a real state change occurred.

**Doc-only workflow.** No `logic/` dir is introduced. The underlying write is always
delegated to the `append-log-entry` skill and `scripts/kb/write_utils.py`.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Delegates write to `append-log-entry`/`scripts/kb/write_utils.py`
  under `wiki/.kb_write.lock`. Does not open any additional write surface.

## When to Use

- A `run-ingest` step successfully writes an artifact to `raw/processed/**` or `wiki/**`
- A governed wiki write completes and the state change must be recorded
- The `knowledgebase-orchestrator` or `policy-arbiter` requires a log entry for traceability
- An audit review needs a deterministic record of what ingest operations have occurred

## Contract

- Input: a non-empty markdown bullet entry describing the state change, plus confirmation
  that a real state change occurred (`state_changed: true`)
- Write target: `wiki/log.md` only, append-only
- Execution: delegates to `append-log-entry` skill
- Handoff: log entry is the final step in an ingest event; no further write is opened

## Assertions

- No log entry is written if `state_changed` is false
- An empty or non-bullet entry fails closed
- The lock at `wiki/.kb_write.lock` must be held by the delegated writer before append
- This skill does not write to any path other than `wiki/log.md`
- Log entries are never deleted or modified; only appended

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/decisions/ADR-005-write-lock-and-concurrency.md`
- `raw/processed/SPEC.md`
- `schema/governed-artifact-contract.md`
- `.github/skills/append-log-entry/SKILL.md`
- `scripts/kb/write_utils.py`
