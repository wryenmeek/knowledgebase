---
name: run-deterministic-validators
description: Runs fixed deterministic validators from the allowlisted knowledgebase execution surface. Use when you need a typed, read-only validator sequence without opening broader automation paths.
---

# Run Deterministic Validators

## Overview

Use this skill to run a named subset of the repository's deterministic knowledgebase validators. It is a thin read-only wrapper over allowlisted `scripts/kb/**` entrypoints and returns the first non-zero exit code unchanged.

## When to Use

- When a skill needs a fixed validator subset instead of broad ad hoc script execution
- Before or after boundary-sensitive wiki work that must stay read-only
- When proving validator selection stays inside the MVP allowlist

## Contract

- Inputs: zero or more typed validator names from a fixed allowlist
- Default selection runs all allowlisted validators in declared order
- Unknown validator names are rejected before any subprocess runs
- Output: deterministic JSON summary plus the first non-zero exit code on failure

## Assertions

- Uses only allowlisted `scripts/kb/qmd_preflight.py`, `scripts/kb/update_index.py`, and `scripts/kb/lint_wiki.py`
- Rejects unknown validator names and fails closed
- Uses no shell, no `eval`, and no dynamic dispatch
- Never writes repository state

## Commands

```bash
python3 .github/skills/run-deterministic-validators/logic/run_deterministic_validators.py --validator qmd-preflight --validator lint-strict
```

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/decisions/ADR-007-control-plane-layering-and-packaging.md`
- `schema/page-template.md`
- `schema/ingest-checklist.md`
- `scripts/kb/qmd_preflight.py`
- `scripts/kb/update_index.py`
- `scripts/kb/lint_wiki.py`
