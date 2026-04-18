---
name: fill-context-pages
description: Previews approval-gated context fill work through the repo-level context fill surface. Use when you need deterministic placeholder detection and explicit fail-closed signaling before any future narrower write contract exists.
---

# Fill Context Pages

## Overview

This skill is a thin operator-facing wrapper over `scripts/context/fill_context_pages.py`. The script computes placeholder-driven fill previews while keeping direct context-page writes blocked until a narrower contract is declared.

## When to Use

- When you need a read-only preview of context pages that still contain fill markers
- When you want explicit approval-gated signaling for later-phase context fill work
- When you need the heavy repo scan to stay in `scripts/context/**` instead of wrapper-local logic

## Contract

- Inputs stay typed: `--mode`, repeated `--path`, and optional `--approval`
- The skill routes directly to `scripts/context/fill_context_pages.py`
- `preview` is read-only; `apply` is explicit, approval-gated, and fail-closed until a narrower write row exists
- The lock requirement for `apply` stays declared as `wiki/.kb_write.lock` even though direct writes remain disabled

## Assertions

- No `.github/skills/fill-context-pages/logic/**` helper is introduced
- No undeclared wiki/docs/context write path opens from the skill
- Placeholder detection stays deterministic and repo-local
- The script remains the single heavy implementation surface

## Commands

```bash
python3 scripts/context/fill_context_pages.py --mode preview --path docs
python3 scripts/context/fill_context_pages.py --mode apply --path docs --approval approved
```

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/ideas/wiki-curation-agent-framework.md`
- `scripts/context/fill_context_pages.py`
