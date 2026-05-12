---
name: validate-taxonomy-placement
description: Validates proposed page placement against taxonomy and identity contracts. Use when topology or editorial follow-up needs a deterministic placement verdict before links or index entries change.
---

# Validate Taxonomy Placement

## Overview

Use this skill to pressure-test proposed wiki placement before downstream
topology work proceeds. It is an active, doc-only contract consumer: compare
path, page role, metadata, and identity signals against the canonical contracts
and return a valid, revise, or escalate recommendation.

## Classification

- **Mode:** Doc-only contract consumer
- **MVP status:** Active
- **Execution boundary:** Validation and handoff only. No direct move, rename,
  alias rewrite, or redirect creation occurs here.

## When to Use

- A new page needs namespace and browse-path confirmation before linking
- A proposed move may affect `wiki/index.md` or neighboring pages
- A merge, split, or supersede plan needs taxonomy validation before topology
  follow-up
- Editorial review needs to know whether placement is valid, advisory, or
  blocking
- A topology bundle needs explicit placement validation before graph changes

## Contract

- Input: proposed page path, frontmatter, title, aliases if present, and nearby
  structural context
- Decision model: classify the proposal as `valid`, `revise`, or `escalate`
  under the taxonomy, metadata, ontology, and page-template contracts
- Output: a placement verdict naming the governing rule, affected field or path,
  and required follow-up
- Handoff rule: approved placement may continue to `update-index` or other
  topology review; redirect, alias, or canonical-identity pressure routes to
  `entity-resolution-and-canonicalization` and `review-wiki-plan`

## Assertions

- Namespace, frontmatter `type`, and canonical role must agree
- `browse_path` and tags are supporting structure, not substitutes for identity
- Advisory taxonomy guidance must still be surfaced even when not deterministically
  blocking
- Redirect or alias-changing behavior remains explicitly governed rather than
  silently automated
- Fail closed when placement cannot be justified by the current contracts

## Procedure

### Step 1: Inspect proposed structural facts

Gather the intended path, `type`, title, status, tags, `browse_path`, and any
alias context that could affect placement.

### Step 2: Compare against canonical contracts

Validate namespace/type fit, slug stability, browse-path durability, and
identity consistency using the taxonomy, metadata, ontology, and page-template
contracts.

### Step 3: Classify the result

- **valid**: placement follows the contracts as proposed
- **revise**: the page is broadly in-bounds but needs structural adjustment
- **escalate**: identity, alias, or placement ambiguity blocks safe follow-up

### Step 4: Route the next governed step

Only after a `valid` verdict should downstream index or link follow-up proceed.
If placement depends on canonical renaming, alias treatment, or unresolved
subject identity, stop and return to governance.

## Boundaries

- Do not silently move pages or rewrite aliases from this skill
- Do not use backlink pressure as proof of correct taxonomy placement
- Do not bypass identity review when namespace choice depends on canonical
  subject resolution
- Do not add a placement linter or crawler runtime in MVP

## Verification

- [ ] The verdict is `valid`, `revise`, or `escalate`
- [ ] Taxonomy, ontology, metadata, and page-template rules are cited
- [ ] Advisory vs. blocking issues are distinguished clearly
- [ ] Alias or redirect-sensitive cases return to governance
- [ ] No direct move or runtime automation is introduced

## References

- [`schema/taxonomy-contract.md`](../../../schema/taxonomy-contract.md)
- [`schema/ontology-entity-contract.md`](../../../schema/ontology-entity-contract.md)
- [`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md)
- [`schema/page-template.md`](../../../schema/page-template.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`AGENTS.md`](../../../AGENTS.md)
- [`wiki/index.md`](../../../wiki/index.md)
