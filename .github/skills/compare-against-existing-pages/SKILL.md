---
name: compare-against-existing-pages
description: Compares a proposed new or updated wiki page against existing pages to identify duplicates, conflicts, and required merge or disambiguation decisions. Use when policy-arbiter or entity-resolution-and-canonicalization needs evidence that the proposed page does not duplicate existing content.
---

# Compare Against Existing Pages

## Overview

This skill documents the duplicate-detection and conflict-comparison step for the
`policy-arbiter` persona. Before a new page is cleared for publication, this step
checks whether substantially similar pages exist, whether claims conflict with
established content, and whether an entity-resolution or canonicalization decision
is needed. Findings block or route the draft without modifying it.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Read-only comparison. No merge, delete, or content
  modification is performed.

## When to Use

- A new entity or concept page draft needs duplicate-check before publication clearance
- `policy-arbiter` must confirm a proposed page does not conflict with established
  wiki content
- An `entity-resolution-and-canonicalization` review is needed to decide whether
  to merge or disambiguate two subjects
- `synthesis-curator` has produced a draft that may overlap with an existing page

## Contract

- Input: the proposed draft page and the current `wiki/**` scope (or a subset)
- Output: a structured comparison result listing matching or conflicting pages and
  the recommended action (approve, merge, disambiguate, or escalate)
- Handoff: conflicts or duplicates route to `entity-resolution-and-canonicalization`
  or human steward; clean drafts proceed to publication clearance

## Assertions

- No existing page is modified or deleted directly by this skill
- Significant overlap with an existing page produces a merge or disambiguation
  recommendation, not a silent pass
- Factual conflicts with established wiki content are flagged explicitly
- This skill does not make final publication decisions unilaterally

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `schema/page-template.md`
- `schema/ontology-entity-contract.md`
- `.github/skills/entity-resolution-and-canonicalization/SKILL.md`
- `.github/agents/policy-arbiter.md`
