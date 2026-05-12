---
name: manage-redirects-and-anchors
description: Records redirect entries in wiki/redirects.md when pages are renamed, merged, or superseded, preserving incoming link integrity per ADR-009. Use when a page rename, merge, or supersede action requires redirect records or anchor updates.
---

# Manage Redirects and Anchors

## Overview

This skill manages the redirect and anchor record-keeping contract for the
`topology-librarian` persona per ADR-009. Redirects are recorded in
`wiki/redirects.md` as an append-only Markdown table. The `logic/` directory
provides the `manage_redirects.py` executable surface.

**Approval-gated write surface.** `apply` mode requires `--approval approved` and
acquires `wiki/.kb_write.lock` before appending. `propose` mode is read-only.

## Classification

- **Mode:** `propose` — read-only preview; `apply` — approval-gated write
- **MVP status:** Active
- **Execution boundary:** Append-only writes to `wiki/redirects.md`.
  No other wiki files are mutated.

## When to Use

- A page is renamed and existing inbound links need to stay resolvable
- A supersede action creates a redirect from the old slug to the replacement page
- A page is removed with no replacement (`REMOVED` as new_slug)
- `topology-librarian` must record a redirect after a maintainer-approved slug change

## Contract

- **Input:** `--old-slug`, `--new-slug` (or `REMOVED`), `--reason`, `--mode`,
  `--approval approved`
- **Output (propose):** a structured preview of the row that would be appended
- **Output (apply):** the row appended to `wiki/redirects.md`; summary contains
  `old_slug`, `new_slug`, `redirected_at`
- **Handoff:** apply result feeds into topology review; `knowledgebase-orchestrator`
  may trigger `check-link-topology` after a redirect is recorded

## Assertions

- `apply` mode is fail-closed on: missing approval, lock unavailable, duplicate
  redirect entry, or slug normalization failure
- `wiki/redirects.md` is append-only; existing rows must not be modified or deleted
- Slug normalization follows ADR-009 rules (lowercase, hyphens only, no leading/trailing hyphens)
- If `wiki/redirects.md` does not exist, `apply` mode creates it with the table header

## References

- `AGENTS.md`
- `ADR-009-canonical-identity-and-anchor-management.md`
- `ADR-005-write-concurrency-guards.md`
- `schema/governed-artifact-contract.md`
- `.github/skills/manage-redirects-and-anchors/logic/manage_redirects.py`
- `.github/agents/topology-librarian.md`
