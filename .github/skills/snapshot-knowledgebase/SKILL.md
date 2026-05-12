---
name: snapshot-knowledgebase
description: Captures deterministic knowledgebase snapshots through the repo-level validation surface. Use when you need a read-only baseline or comparison over wiki, schema, or processed raw artifacts before higher-risk changes.
---

# Snapshot Knowledgebase

## Overview

Use this thin skill as a wrapper over `scripts/validation/snapshot_knowledgebase.py`. The heavy snapshot hashing and comparison logic stays in the repo-level validation surface and remains read-only.

## When to Use

- When you need a deterministic baseline of `wiki/**`, `schema/**`, or `raw/processed/**`
- When you want to compare a staged snapshot JSON against current repo state
- When a higher-risk maintenance or migration flow needs read-only regression evidence

## Contract

- Inputs stay typed: `--mode`, repeated `--path`, and optional `--snapshot`
- The skill routes directly to `scripts/validation/snapshot_knowledgebase.py`
- Both `capture` and `compare` remain repo-local and read-only
- Missing snapshots, path escapes, or invalid repo roots fail closed

## Assertions

- No `.github/skills/snapshot-knowledgebase/logic/**` helper is introduced
- No write or persistence side effect is added to the validation surface
- Snapshot hashing remains deterministic and repo-local only
- Comparison reads staged JSON instead of reaching for network state

## Commands

```bash
python3 scripts/validation/snapshot_knowledgebase.py --mode capture --path wiki --path schema
python3 scripts/validation/snapshot_knowledgebase.py --mode compare --path wiki --snapshot docs/staged/knowledgebase-snapshot.json
```

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/ideas/wiki-curation-agent-framework.md`
- `scripts/validation/snapshot_knowledgebase.py`
