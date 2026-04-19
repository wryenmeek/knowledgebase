---
name: manage-redirects-and-anchors
description: Documents the redirect and anchor management contract for the topology-librarian persona. Use when a page rename, merge, or supersede action requires redirect records or anchor updates to preserve incoming links.
---

# Manage Redirects and Anchors

## Overview

This skill documents the redirect and anchor management contract for the
`topology-librarian` persona. Redirects and anchor updates preserve link integrity
when pages are renamed, merged, or superseded. In the current MVP, this skill is
**doc-only**: redirect automation is deferred until an ADR for canonical identity
and durable anchor management is approved (see Phase 3 in the framework gap plan).

**Doc-only workflow — approval-gated for any automation.** No `logic/` dir is
introduced. Any future automation of redirect creation or anchor management requires
explicit maintainer approval and an AGENTS.md row before a `logic/` dir is added.

## Classification

- **Mode:** Doc-only workflow — approval-gated for any automation
- **MVP status:** Active (doc-only); automation deferred to Phase 3
- **Execution boundary:** Documentation of redirect/anchor contract only. No
  automated redirect creation until an ADR approves the redirect-management surface.

## When to Use

- A page is renamed or merged and existing inbound links need to stay resolvable
- A supersede action needs a redirect record so that readers following old links
  reach the replacement page
- `topology-librarian` must produce a redirect plan for human steward review before
  any structural change
- An operator needs to understand the current redirect contract before requesting
  automation

## Contract

- Input: the old page path, the new canonical page path or superseding page, and
  the reason for the redirect (rename, merge, supersede)
- Output: a proposed redirect record for human or governed-topology review
- Handoff: the redirect proposal routes to human steward or `knowledgebase-orchestrator`
  for approval before implementation

## Assertions

- No redirect is created automatically without explicit maintainer approval and
  an AGENTS.md row for the automation surface
- Redirect proposals are documentation artifacts, not executable actions, in MVP
- Any `logic/` addition to this skill requires an ADR plus an AGENTS.md row first
- Broken incoming links without a redirect plan must be flagged, not silently ignored

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `schema/taxonomy-contract.md`
- `.github/agents/topology-librarian.md`
- `docs/ideas/spec.md`
