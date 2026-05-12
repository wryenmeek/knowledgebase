---
name: entity-resolution-and-canonicalization
description: Assesses duplicate subjects, aliases, and canonical naming conflicts. Use when comparing pages or source mentions that may refer to the same durable subject and when you need a merge, split, or escalation recommendation.
---

# Entity Resolution and Canonicalization

## Overview

Use this skill to operationalize canonical identity review without introducing a
new merge runtime. In MVP it is an active, doc-only contract consumer: compare
evidence, classify the identity outcome, and route any durable change back
through governed follow-up.

## Classification

- **Mode:** Doc-only contract consumer
- **MVP status:** Active
- **Execution boundary:** Read-only assessment and handoff only. Do not add
  automated merge, redirect, alias-rewrite, or batch canonicalization logic in
  MVP.

## When to Use

- Two pages may represent the same durable subject
- One alias appears to map to multiple active subjects
- A source introduces a new name that may already belong to an existing entity
- A reviewer needs a keep, merge, split, or escalate recommendation
- Canonical naming would materially affect page placement, linking, or meaning

## Contract

- Input: candidate page paths, titles, aliases, and source-backed surface forms
- Decision model: classify the case as `keep`, `merge`, `split`, or `escalate`
- Output: a canonicalization recommendation with surviving title candidates,
  aliases to preserve, affected paths, and unresolved evidence notes
- Handoff rule: any durable merge, redirect, or topology follow-up routes back
  through governed wiki planning and downstream personas instead of executing
  here

## Assertions

- Compare durable referents, not string similarity alone
- Treat alias collisions and ambiguous acronyms as blocking until evidence
  resolves them
- Preserve ontology and taxonomy contract boundaries when recommending canonical
  titles
- Fail closed on ambiguity that would change legal, policy, or public meaning
- Keep the skill read-only in MVP

## Procedure

### Step 1: Gather candidate identities

List the candidate pages, titles, aliases, and cited source-backed names. Treat
each candidate as provisional until the evidence shows the same durable
referent.

### Step 2: Compare referents, not strings

Use
[`schema/ontology-entity-contract.md`](../../../schema/ontology-entity-contract.md)
to determine whether the candidates refer to one stable subject, multiple stable
subjects, or a mixed page that needs separation.

### Step 3: Classify the outcome

Choose exactly one of:

- **keep**: distinct canonical subjects
- **merge**: duplicate canonical pages for the same subject
- **split**: one page contains multiple durable subjects
- **escalate**: ambiguity, contradiction, or public-meaning risk remains

### Step 4: Prepare the governed handoff

Document the proposed surviving canonical title or titles, aliases to retain,
affected page paths, and any evidence gaps that block deterministic execution.

### Step 5: Stop before automation

If the recommendation would require redirects, bulk edits, or merge mechanics,
route the proposal to `review-wiki-plan` and governed downstream follow-up
rather than implementing it here.

## Boundaries

- Do not create a second runtime for identity resolution
- Do not auto-merge pages based on fuzzy title similarity alone
- Do not accept ambiguous acronyms without evidence
- Do not bypass human escalation when meaning would materially change

## Verification

- [ ] Candidate comparison is based on durable referent evidence
- [ ] Outcome is one of `keep`, `merge`, `split`, or `escalate`
- [ ] Aliases and surviving titles follow the ontology contract
- [ ] Ambiguous or high-impact cases are escalated
- [ ] No automated rewrite behavior is introduced in MVP

## References

- [`schema/ontology-entity-contract.md`](../../../schema/ontology-entity-contract.md)
- [`schema/taxonomy-contract.md`](../../../schema/taxonomy-contract.md)
- [`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`AGENTS.md`](../../../AGENTS.md)
