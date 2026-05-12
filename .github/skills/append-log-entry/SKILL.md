---
name: append-log-entry
description: Appends deterministic state-change entries to wiki/log.md. Use when a write-capable flow needs the append-only provenance log after a real state change.
---

# Append Log Entry

## Overview

Use this skill to append a single deterministic entry to `wiki/log.md` while preserving the append-only and state-change-only contract. The helper delegates to the repo's write lock and log append utility instead of reimplementing write behavior.

## When to Use

- After a governed write actually changes durable wiki state
- When a workflow needs to record a state transition in `wiki/log.md`
- When proving the append-only log path stays inside the allowlisted write surface

## Contract

- Input: one non-empty markdown bullet entry and a typed `state_changed` flag
- Write target is fixed to `wiki/log.md`
- A write lock is required before append mode runs
- Output: deterministic result showing whether a log entry was appended

## Assertions

- Rejects empty or non-bullet log entries
- Does not write anything when `state_changed` is false
- Uses the shared write lock and append-only helper from `scripts/kb/write_utils.py`
- Uses no shell, no `eval`, and no dynamic dispatch

## Commands

```bash
python3 .github/skills/append-log-entry/logic/append_log_entry.py --entry "- source ingested" --state-changed
```

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `schema/page-template.md`
- `scripts/kb/write_utils.py`
