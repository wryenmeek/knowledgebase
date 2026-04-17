---
name: sync-knowledgebase-state
description: Synchronizes deterministic knowledgebase state through narrow allowlisted wrappers. Use when checking or refreshing wiki/index.md without expanding beyond MVP script boundaries.
---

# Sync Knowledgebase State

## Overview

Use this skill to reconcile deterministic wiki state while staying inside the MVP control-plane boundary. The wrapper is intentionally narrow: it validates first, then optionally writes `wiki/index.md`.

## When to Use

- After valid wiki content changes need an index refresh
- When confirming state can be synchronized without unsafe side effects
- Before or after deterministic ingest flows that should leave index state clean

## Commands

Read-only precheck mode:

```bash
python3 .github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py --check-only
```

Write mode for index synchronization only:

```bash
python3 .github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py --write-index
```

The wrapper uses fixed repo-root execution and only these allowlisted entrypoints:

- `scripts/kb/qmd_preflight.py`
- `scripts/kb/update_index.py`
- `scripts/kb/lint_wiki.py`

Read-only prechecks use `python3 scripts/kb/update_index.py --wiki-root wiki --check`
so stale `wiki/index.md` fails closed in `--check-only` mode.

Write mode treats stale `wiki/index.md` as the condition it is meant to repair:
it runs `qmd_preflight.py`, then `lint_wiki.py --strict --skip-orphan-check`,
then `update_index.py --write`, then a final strict lint to prove the synced
state is clean.

## Execution boundaries

- No shell, `eval`, or dynamic dispatch
- No free-form command forwarding
- Typed flags only: `--check-only` or `--write-index`
- Read-only prechecks always run before any write
- Default mode is read-only
- No network behavior
- No-write-on-failure: `wiki/index.md` is written only after prechecks pass
- This skill does **not** wrap new repo-level maintenance/reporting/context trees

## Out of scope in MVP

- Broad stateful automation
- Batch reporting or repo crawlers
- New `scripts/validation/*`, `scripts/reporting/*`, `scripts/context/*`, or `scripts/maintenance/*`
- Replacing `scripts/kb/ingest.py` or `scripts/kb/persist_query.py`

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/decisions/ADR-007-control-plane-layering-and-packaging.md`
- `docs/mvp-runbook.md`
