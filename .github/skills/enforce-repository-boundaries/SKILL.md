---
name: enforce-repository-boundaries
description: Enforces deterministic repository path boundaries for knowledgebase work. Use when validating whether a read or write path stays inside the allowlisted MVP surface.
---

# Enforce Repository Boundaries

## Overview

Use this skill to classify repository-relative paths against the knowledgebase boundary before a helper reads or writes anything. The logic is deny-by-default, typed, and deterministic.

## When to Use

- Before a helper reads repo-local evidence from a boundary-sensitive path
- Before any write-capable helper touches `wiki/**` or `raw/processed/**`
- When proving a path stays inside the MVP allowlist from `AGENTS.md` and `scripts/kb/contracts.py`

## Contract

- Input: one repository-relative POSIX path plus a typed mode of `read` or `write`
- Read allowlist: fixed knowledgebase zones and boundary docs only
- Write allowlist: fixed contract paths from `scripts/kb/contracts.py`
- Output: deterministic JSON/report with `allowed`, normalized `path`, and a stable `reason_code`

## Assertions

- Rejects absolute paths, backslashes, empty segments, and traversal
- Fails closed on paths outside the fixed allowlist
- Uses no shell, no `eval`, and no dynamic dispatch
- Keeps write permission narrower than read permission

## Commands

```bash
python3 .github/skills/enforce-repository-boundaries/logic/enforce_repository_boundaries.py --mode write --path wiki/index.md
```

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/decisions/ADR-007-control-plane-layering-and-packaging.md`
- `schema/page-template.md`
- `scripts/kb/contracts.py`
