---
name: sync-knowledgebase-state
description: Synchronizes deterministic knowledgebase state through narrow allowlisted wrappers. Use when checking or refreshing wiki/index.md without expanding beyond MVP script boundaries.
---

# Sync Knowledgebase State

## Overview

Use this skill to reconcile deterministic governed wiki state while staying inside the MVP control-plane boundary. The wrapper is intentionally narrow: it validates first, then only routes over approved governed artifacts.

## When to Use

- After valid wiki content changes need an index refresh
- When a governed state artifact staged in-repo is ready to publish under ADR-005
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

Append-only log mode:

```bash
python3 .github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py --append-log-entry "- state changed" --state-changed
```

Atomic publish modes for approved mutable governed artifacts:

```bash
python3 .github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py --write-open-questions-from wiki/open-questions.next.md
python3 .github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py --write-backlog-from wiki/backlog.next.md
python3 .github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py --write-status-from wiki/status.next.md
```

The wrapper uses fixed repo-root execution and only these allowlisted entrypoints or governed helpers:

- `scripts/kb/qmd_preflight.py`
- `scripts/kb/update_index.py`
- `scripts/kb/lint_wiki.py`
- `scripts/kb/write_utils.py`

Read-only prechecks use `python3 scripts/kb/update_index.py --wiki-root wiki --check`
so stale `wiki/index.md` fails closed in `--check-only` mode.

Write mode treats stale `wiki/index.md` as the condition it is meant to repair:
it runs `qmd_preflight.py`, then `lint_wiki.py --strict --skip-orphan-check`,
then `update_index.py --write`, then a final strict lint to prove the synced
state is clean.

Other write-capable modes are fixed to governed artifacts only:

- `wiki/log.md` append-only entry append under `wiki/.kb_write.lock`
- `wiki/open-questions.md` atomic replace under `wiki/.kb_write.lock`
- `wiki/backlog.md` atomic replace under `wiki/.kb_write.lock`
- `wiki/status.md` atomic replace under `wiki/.kb_write.lock`
- unsupported artifact targets are rejected

## Execution boundaries

- No shell, `eval`, or dynamic dispatch
- No free-form command forwarding
- Typed flags only: `--check-only`, `--write-index`, `--append-log-entry`,
  `--write-open-questions-from`, `--write-backlog-from`, or
  `--write-status-from`
- Read-only prechecks always run before any write
- Default mode is read-only
- No network behavior
- No-write-on-failure: governed artifacts mutate only after their mode-specific
  prechecks, lock rules, and contract checks pass
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
