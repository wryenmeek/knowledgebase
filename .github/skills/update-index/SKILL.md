---
name: update-index
description: Prepares governed `wiki/index.md` follow-up after approved structural changes. Use when taxonomy-safe page edits need an explicit index-refresh handoff instead of silent automation.
---

# Update Index

## Overview

Use this skill to package an index-refresh request after policy-cleared structural
changes. In MVP it is a doc-only workflow: identify why `wiki/index.md` needs
follow-up, confirm the governing contracts, and route the approved refresh to an
existing deterministic surface instead of editing the index here.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Handoff only. No direct `wiki/index.md` write occurs
  here; deterministic refreshes route to `sync-knowledgebase-state`.

## When to Use

- A policy-cleared page add, move, rename, or retirement changes browse
  structure
- Approved taxonomy placement changes require the curated index to catch up
- A topology review identifies stale or missing `wiki/index.md` entries
- A merge, split, or supersede decision has already been governed and now needs
  index follow-up
- Editorial lanes need an explicit graph-safe handoff instead of silent index
  mutation

## Contract

- Input: approved structural change scope, affected page paths, and current
  `wiki/index.md` coverage
- Decision model: determine whether the index needs add, remove, reorder, or
  descriptive follow-up based on existing contracts
- Output: an index-update handoff listing affected pages, governing rule, and
  deterministic follow-up required
- Handoff rule: route the approved refresh to `sync-knowledgebase-state`; if
  redirect or alias semantics are implicated, return to
  `entity-resolution-and-canonicalization` and `review-wiki-plan` before any
  index mutation is attempted

## Assertions

- `wiki/index.md` remains a governed artifact, not an editorial scratchpad
- Index follow-up must reflect canonical taxonomy and identity decisions already
  made elsewhere
- Prefer the narrowest deterministic refresh compatible with the cleared scope
- Redirect or alias-changing behavior remains explicitly governed rather than
  silently automated
- No new crawler, graph runtime, or bulk rewrite path is introduced in MVP

## Procedure

### Step 1: Confirm cleared structural scope

Start only after the affected material has already cleared the intake,
verification, and policy sequence. Record the page paths and structural reason
the index needs follow-up.

### Step 2: Check governing contracts

Review the affected namespace, `browse_path`, status, and canonical identity
using the taxonomy, metadata, ontology, and page-template contracts before
recommending any index change.

### Step 3: Package the index delta

Describe the smallest necessary follow-up:

- new entry needed
- stale entry removal
- ordering or placement adjustment
- descriptive entry text refresh tied to a cleared canonical change

### Step 4: Route deterministic execution

Send the handoff to `sync-knowledgebase-state` for the actual deterministic
refresh. If the change pressure depends on redirects, aliases, or unresolved
canonical identity, stop and return to governance instead of forcing the index.

## Boundaries

- Do not edit `wiki/index.md` directly from this skill
- Do not treat index cleanup as permission to rename pages or aliases
- Do not bypass `entity-resolution-and-canonicalization` for identity-sensitive
  topology work
- Do not add runtime crawl, diff, or graph-maintenance systems in MVP

## Verification

- [ ] The handoff names the affected pages and why the index changed
- [ ] Taxonomy, metadata, ontology, and page-template rules are cited
- [ ] Redirect or alias-sensitive cases are escalated instead of auto-applied
- [ ] Deterministic execution routes to `sync-knowledgebase-state`
- [ ] No direct `wiki/index.md` write or heavyweight runtime is introduced

## References

- [`schema/taxonomy-contract.md`](../../../schema/taxonomy-contract.md)
- [`schema/ontology-entity-contract.md`](../../../schema/ontology-entity-contract.md)
- [`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md)
- [`schema/page-template.md`](../../../schema/page-template.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`AGENTS.md`](../../../AGENTS.md)
- [`wiki/index.md`](../../../wiki/index.md)
