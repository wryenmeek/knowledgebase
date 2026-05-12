---
name: generate-maintenance-docs
description: Generates and applies docs/ content via a two-step Copilot-agent-runtime workflow. Use when you need to create or update docs/ files (architecture docs, ADRs, references) from agent-generated content with governed write semantics.
---

# Generate Maintenance Docs

## Overview

Two-step workflow using the Copilot agent runtime:
1. **Inventory / Plan** — `scripts/maintenance/generate_docs.py --mode inventory` (or `--mode plan`) scans `.github/skills/**`, `docs/**`, `schema/**`, and `scripts/**` for documentation targets and returns what needs generating.
2. **Apply** — The agent generates the document content, stages a manifest to `docs/staged/`, then calls `apply` mode to write the files under the `wiki/.kb_write.lock`.

All writes go to `docs/**` only. `docs/staged/**` is explicitly denied as a write target.

## When to Use

- When generating or updating docs/ files that are maintained via automation (architecture docs, ADRs, script references)
- When you have agent-generated content that needs governed, rollback-safe write to `docs/**`

## Two-Step Workflow

### Step 1 — Inventory or plan (identify targets)

```bash
python3 scripts/maintenance/generate_docs.py --mode inventory --path docs --path scripts
python3 scripts/maintenance/generate_docs.py --mode plan --path .github/skills --path docs
```

Returns `items[]` describing files that need creation or update.

### Step 2 — Stage manifest and apply

The agent generates content for each target, then writes a manifest:

```json
{
  "items": [
    {
      "path": "docs/scripts-reference.md",
      "content": "# Scripts Reference\n\nAuto-generated script documentation.\n",
      "expected_before_sha256": "<sha256 of current file content, or null/omit for new files>"
    }
  ]
}
```

Save the manifest to `docs/staged/docs-<timestamp>.json`, then apply:

```bash
python3 scripts/maintenance/generate_docs.py \
  --mode apply \
  --staged-docs-path docs/staged/docs-<timestamp>.json \
  --approval approved
```

## Contract

- Inputs stay typed: `--mode`, `--staged-docs-path`, and `--approval`
- `apply` requires `--staged-docs-path` within `docs/staged/`, `--approval approved`, and `wiki/.kb_write.lock`
- Write targets must be `.md` files within `docs/**` (excluding `docs/staged/**`)
- SHA mismatch (file changed since manifest was produced) fails closed
- New files: set `expected_before_sha256` to `null` or omit the field
- All writes are atomic and rolled back on failure

## Assertions

- No `logic/` dir is introduced; if one is added, an AGENTS.md row becomes mandatory before merge
- `docs/staged/**` writes are always rejected as targets
- Writes outside `docs/**` are always rejected

## Commands

```bash
python3 scripts/maintenance/generate_docs.py --mode inventory --path docs --path scripts
python3 scripts/maintenance/generate_docs.py --mode apply --staged-docs-path docs/staged/docs-manifest.json --approval approved
```

## References

- `AGENTS.md` (narrower row for `scripts/maintenance/generate_docs.py apply`)
- `scripts/maintenance/generate_docs.py`
- `scripts/_optional_surface_common.py` (`validate_staged_manifest`, `resolve_write_target`)
- `scripts/kb/write_utils.py` (`exclusive_write_lock`, `write_text_capturing_previous_safe`, `rollback_file_state`)

