---
name: fill-context-pages
description: Fills placeholder markers in context pages via a two-step Copilot-agent-runtime workflow. Use when you need to replace {{fill}}, TODO, TBD, or [context-needed] markers in .github/skills/** or docs/** files with agent-generated content.
---

# Fill Context Pages

## Overview

Two-step workflow using the Copilot agent runtime:
1. **Preview** — `scripts/context/fill_context_pages.py --mode preview` scans `.github/skills/**`, `docs/**`, and `schema/**` for placeholder markers and returns a list of candidates.
2. **Apply** — The agent reads each candidate file, generates filled content (no placeholders remaining), stages a manifest to `docs/staged/`, then calls `apply` mode to write the files under the `wiki/.kb_write.lock`.

`schema/**` is read-scanned for placeholder detection but is **never written** — schema files are authoritative contracts.

## When to Use

- When context pages in `.github/skills/**` or `docs/**` contain `{{fill}}`, `TODO`, `TBD`, or `[context-needed]` markers
- When you want a governed, rollback-safe write of agent-generated content into the framework or docs trees

## Two-Step Workflow

### Step 1 — Preview (identify candidates)

```bash
python3 scripts/context/fill_context_pages.py --mode preview --path .github/skills --path docs
```

Returns `items[]` with `path` and `placeholder_count` for each file needing fills.

### Step 2 — Stage manifest and apply

The agent reads each candidate file, generates filled content, then writes a manifest:

```json
{
  "items": [
    {
      "path": "docs/some-context-page.md",
      "content": "# Some Context Page\n\nFully filled content with no placeholders.\n",
      "expected_before_sha256": "<sha256 of current file content, or omit for new files>"
    }
  ]
}
```

Save the manifest to `docs/staged/fills-<timestamp>.json`, then apply:

```bash
python3 scripts/context/fill_context_pages.py \
  --mode apply \
  --staged-fills-path docs/staged/fills-<timestamp>.json \
  --approval approved
```

## Contract

- Inputs stay typed: `--mode`, `--staged-fills-path`, and `--approval`
- `apply` requires `--staged-fills-path` within `docs/staged/`, `--approval approved`, and `wiki/.kb_write.lock`
- Write targets must be `.md` files within `.github/skills/**` or `docs/**` (excluding `docs/staged/**`)
- `schema/**` is explicitly denied as a write target
- Content with remaining placeholder markers is rejected at apply time
- SHA mismatch (file changed since manifest was produced) fails closed
- All writes are atomic and rolled back on failure

## Assertions

- No `logic/` dir is introduced; if one is added, an AGENTS.md row becomes mandatory before merge
- `schema/**` writes are always rejected
- `docs/staged/**` writes are always rejected as targets
- Placeholder detection stays deterministic and repo-local

## Commands

```bash
python3 scripts/context/fill_context_pages.py --mode preview --path .github/skills --path docs
python3 scripts/context/fill_context_pages.py --mode apply --staged-fills-path docs/staged/fills.json --approval approved
```

## References

- `AGENTS.md` (narrower row for `scripts/context/fill_context_pages.py apply`)
- `scripts/context/fill_context_pages.py`
- `scripts/_optional_surface_common.py` (`validate_staged_manifest`, `resolve_write_target`)
- `scripts/kb/write_utils.py` (`exclusive_write_lock`, `write_text_capturing_previous_safe`, `rollback_file_state`)

