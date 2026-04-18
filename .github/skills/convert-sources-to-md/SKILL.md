---
name: convert-sources-to-md
description: Previews repo-local source conversion through the approval-gated ingest conversion surface. Use when you need deterministic inspection or Markdown previews of inbox/assets sources without opening undeclared processed-artifact writes.
---

# Convert Sources To MD

## Overview

This thin skill routes source-conversion inventory and preview work to `scripts/ingest/convert_sources_to_md.py`. Heavy file-type inspection stays in the repo-level ingest script; any processed-artifact write remains blocked until a narrower contract is declared.

## When to Use

- When you need a deterministic inventory of `raw/inbox/**` or `raw/assets/**` sources
- When you want a repo-local Markdown preview for supported text or HTML sources
- When you need explicit fail-closed behavior for unsupported formats like PDF without external converters

## Contract

- Inputs stay typed: `--mode`, repeated `--path`, and optional `--approval`
- The skill routes directly to `scripts/ingest/convert_sources_to_md.py`
- `inspect` and `preview` are read-only; `apply` remains approval-gated and blocked until a narrower ingest writer exists
- Source paths stay repo-local, allowlisted, and deny-by-default

## Assertions

- No `.github/skills/convert-sources-to-md/logic/**` helper is introduced
- Unsupported source types fail closed rather than invoking external tools or the network
- `raw/processed/**` remains immutable from this surface today
- The repo-level script remains the only heavy implementation surface

## Commands

```bash
python3 scripts/ingest/convert_sources_to_md.py --mode inspect --path raw/inbox
python3 scripts/ingest/convert_sources_to_md.py --mode preview --path raw/inbox/example.txt
python3 scripts/ingest/convert_sources_to_md.py --mode apply --path raw/inbox/example.txt --approval approved
```

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/ideas/wiki-curation-agent-framework.md`
- `scripts/ingest/convert_sources_to_md.py`
