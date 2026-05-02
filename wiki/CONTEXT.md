---
scope: directory
last_updated: 2026-04-29
type: context
title: Wiki CONTEXT
status: active
updated_at: 2026-04-29
---

# CONTEXT — wiki/

Vocabulary for the curated wiki content layer. `AGENTS.md` takes precedence on any conflict.

## Terms

| Term | Definition |
|------|------------|
| governed artifact | A wiki file managed through the write-surface matrix in `AGENTS.md`. Mutations require `wiki/.kb_write.lock` and a `wiki/log.md` entry. |
| page status | Lifecycle state of a wiki page: `stub`, `draft`, `active`, `superseded`, `archived`. Set via frontmatter `status` field. |
| namespace | Top-level content category under `wiki/`: `sources`, `entities`, `concepts`, `analyses`. Governed by `schema/taxonomy-contract.md`. |
| append-only log | `wiki/log.md` — records state-change events. Never rewritten or truncated; new entries appended at the end. |
| cross-reference | A markdown link between wiki pages. Must be symmetric: if page A links to page B, page B should link back to page A. |
| confidence score | Integer 1–5 in page frontmatter rating source reliability: 1 = unverified, 5 = primary source with full provenance. |
| sensitivity | Frontmatter field (`public` or `internal`) controlling content distribution scope. |
| browse path | The namespace + slug path by which a page is discoverable in the index (e.g., `sources/SPEC`). Governed by taxonomy contract. |

## Invariants

| Invariant | Description |
|-----------|-------------|
| Log is append-only | `wiki/log.md` must never be rewritten, truncated, or have entries removed. |
| Index is deterministic | `wiki/index.md` is regenerated from wiki content by `scripts/kb/update_index.py`. Manual edits are overwritten. |
| Lock before write | All wiki mutations require acquiring `wiki/.kb_write.lock` per ADR-005 before any file write. |
| Frontmatter required | Every wiki page must have YAML frontmatter conforming to `schema/page-template.md`. |
| Namespace placement | Pages must reside under an allowed namespace directory. Governed by `schema/taxonomy-contract.md`. |

## File Roles

| File | Role |
|------|------|
| `index.md` | Auto-generated catalog of all wiki pages. Deterministic output of `update_index.py`. |
| `log.md` | Append-only provenance log recording every governed state change. |
| `sources/` | Namespace for source-material summary pages (e.g., `sources/SPEC.md`). |
| `entities/` | Namespace for entity pages (people, organizations, systems). |
| `concepts/` | Namespace for concept and topic pages. |
| `analyses/` | Namespace for analytical and synthesis pages. |
