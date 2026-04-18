---
name: refresh-context-pages
description: Refreshes repo-local context page inventories and fill plans through the approved context script surface. Use when you need deterministic context-page discovery, placeholder planning, or delegated governed status publication without embedding repo-wide logic in a skill wrapper.
---

# Refresh Context Pages

## Overview

Use this thin skill to route context-page inventory and planning work to `scripts/context/manage_context_pages.py`. Heavy repo walking, path rules, declared mode boundaries, and delegated lock-aware publication stay in the repo-level script.

## When to Use

- When you need an inventory of context pages under `.github/skills/**`, `docs/**`, or `schema/**`
- When you want a deterministic placeholder-driven fill plan from repo-local markdown
- When a later-phase approved flow needs to delegate a governed `wiki/status.md` update through the existing sync wrapper

## Contract

- Inputs stay typed: `--mode`, repeated `--path`, optional repeated `--changed-path`, `--limit`, and optional `--approval`
- The skill routes directly to `scripts/context/manage_context_pages.py`
- Direct context writes stay closed; any status publication delegates to `sync-knowledgebase-state`
- Lock behavior stays explicit: only `publish-status` is lock-requiring, and it uses the existing `wiki/.kb_write.lock` path through the governed writer surface

## Assertions

- No `.github/skills/refresh-context-pages/logic/**` helper is introduced
- Path rules remain allowlisted and repo-local only
- Unsupported or unapproved write-capable requests fail closed
- Heavy discovery and scope reduction logic remains in `scripts/context/manage_context_pages.py`

## Commands

```bash
python3 scripts/context/manage_context_pages.py --mode inventory --path docs --path schema
python3 scripts/context/manage_context_pages.py --mode plan-fill --changed-path docs/architecture.md --path docs
python3 scripts/context/manage_context_pages.py --mode publish-status --staged-status-path docs/staged/status.md --approval approved
```

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/ideas/wiki-curation-agent-framework.md`
- `scripts/context/manage_context_pages.py`
