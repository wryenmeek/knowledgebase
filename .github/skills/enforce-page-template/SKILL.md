---
name: enforce-page-template
description: Enforces the deterministic wiki page template for governed pages. Use when validating that a wiki page matches the required frontmatter and section structure.
---

# Enforce Page Template

## Overview

Use this skill to validate a single wiki markdown page against the blocking baseline from `schema/page-template.md`. The validator is intentionally narrow: it checks the page path, required frontmatter keys, the canonical H1, and required body sections for governed page types.

## When to Use

- Before durable wiki writes are proposed or applied
- When a new page is being drafted under `wiki/sources/`, `wiki/entities/`, `wiki/concepts/`, or `wiki/analyses/`
- When proving page structure still matches the MVP schema contract

## Contract

- Input: one repo-relative markdown path under `wiki/**`
- Required frontmatter keys come from the current blocking template baseline
- `entity`, `concept`, `source`, and `analysis` pages must include `## Summary`, `## Evidence`, and `## Open Questions`
- Output: deterministic validation report with stable violation codes

## Assertions

- Rejects non-markdown or out-of-bound wiki paths
- Fails closed when frontmatter is missing or required keys are absent
- Requires the H1 title to match frontmatter `title`
- Uses no shell, no `eval`, and no dynamic dispatch

## Commands

```bash
python3 .github/skills/enforce-page-template/logic/enforce_page_template.py --page wiki/sources/example.md
```

## References

- `AGENTS.md`
- `schema/page-template.md`
- `schema/metadata-schema-contract.md`
- `schema/taxonomy-contract.md`
- `schema/ontology-entity-contract.md`
