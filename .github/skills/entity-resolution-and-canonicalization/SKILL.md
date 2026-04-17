---
name: entity-resolution-and-canonicalization
description: Assesses duplicate subjects, aliases, and canonical naming conflicts. Use when comparing pages or source mentions that may refer to the same durable subject and when you need a merge, split, or escalation recommendation.
---

# Entity Resolution and Canonicalization

## Overview

This skill is the repository's scaffolding for duplicate detection and canonical
identity review. In MVP it remains assessment-first: compare evidence, recommend
an outcome, and escalate ambiguity instead of automating page rewrites.

## Classification

- **Mode:** Deferred
- **MVP status:** Scaffolding only
- **Execution boundary:** Read-only assessment and escalation. No automated
  merge, redirect, alias-rewrite, or batch canonicalization logic in MVP.

## Authoritative Inputs

- [`schema/ontology-entity-contract.md`](../../../schema/ontology-entity-contract.md)
- [`schema/taxonomy-contract.md`](../../../schema/taxonomy-contract.md)
- [`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`AGENTS.md`](../../../AGENTS.md)

## When to Use

- Two pages may represent the same subject
- One alias appears to map to multiple active subjects
- A source introduces a new name that may be an existing entity
- A reviewer needs a merge, split, or keep-separate recommendation
- Canonical naming would materially affect page placement or interpretation

## Procedure

### Step 1: Gather candidate identities

List the candidate pages, titles, aliases, and source-backed surface forms.
Treat every candidate as provisional until evidence shows the same durable
referent.

### Step 2: Compare referents, not strings

Check whether the candidates share the same stable subject rather than merely
similar wording. Use the ontology contract's identity and alias rules.

### Step 3: Recommend one of four outcomes

- **keep**: distinct canonical subjects
- **merge**: same subject, duplicate canonical pages
- **split**: one page contains multiple durable subjects
- **escalate**: ambiguity or public-meaning risk remains

### Step 4: Prepare the canonicalization handoff

Document:

- recommended surviving canonical title or titles
- aliases to preserve
- affected page paths
- evidence gaps or contradiction notes

### Step 5: Stop before automation

If the recommendation would require redirects, bulk edits, or merge mechanics,
record the proposal and defer implementation to later MVP phases with explicit
tests and wrappers.

## Boundaries

- Do not create a second runtime for identity resolution.
- Do not auto-merge pages based on fuzzy title similarity alone.
- Do not accept ambiguous acronyms without evidence.
- Do not bypass human escalation when meaning or legal interpretation would
  change materially.

## Verification

- [ ] Candidate comparison is based on durable referent evidence
- [ ] Outcome is one of keep, merge, split, or escalate
- [ ] Aliases and surviving titles follow the ontology contract
- [ ] Ambiguous or high-impact cases are escalated
- [ ] No automated rewrite behavior is introduced in MVP
