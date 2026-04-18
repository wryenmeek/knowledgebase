---
name: generate-maintenance-docs
description: Plans approval-gated maintenance documentation batches through the repo-level maintenance script surface. Use when you need deterministic inventory or planning across docs, schema, skills, and scripts without opening undeclared writes.
---

# Generate Maintenance Docs

## Overview

Use this thin skill to route maintenance documentation inventory and planning to `scripts/maintenance/generate_docs.py`. The heavy repo scan stays in the repo-level script, while any apply mode remains explicitly blocked until a narrower maintenance write contract exists.

## When to Use

- When you need a repo-local inventory of documentation and script targets for a maintenance batch
- When you want deterministic planning over `.github/skills/**`, `docs/**`, `schema/**`, and `scripts/**`
- When an operator needs an explicit approval-gated no-write boundary for future doc generation work

## Contract

- Inputs stay typed: `--mode`, repeated `--path`, and optional `--approval`
- The skill routes directly to `scripts/maintenance/generate_docs.py`
- `inventory` and `plan` remain repo-local and read-only; `apply` fails closed until a narrower row exists
- Lock and write posture stay explicit rather than inferred

## Assertions

- No `.github/skills/generate-maintenance-docs/logic/**` helper is introduced
- No undeclared maintenance write path opens from the skill
- Repo walking and target classification stay in `scripts/maintenance/generate_docs.py`
- Approval gating remains explicit and default-off

## Commands

```bash
python3 scripts/maintenance/generate_docs.py --mode inventory --path docs --path scripts
python3 scripts/maintenance/generate_docs.py --mode apply --path docs --approval approved
```

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/ideas/wiki-curation-agent-framework.md`
- `scripts/maintenance/generate_docs.py`
