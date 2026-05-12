---
name: synthesize-cited-answer
description: Produces a cited answer from curated retrieval results while preserving governance boundaries. Use when a query workflow has the relevant wiki scope and needs an answer plus a durable-follow-up recommendation.
---

# Synthesize Cited Answer

## Overview

Use this skill to turn a retrieval brief into a cited answer without opening a
durable write path. In MVP it is a doc-only workflow: compose the answer from
curated pages, capture remaining gaps, and classify whether durable follow-up
should be considered.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Answer synthesis and handoff only. Do not persist query
  results or write under `wiki/` from this skill.

## When to Use

- `retrieve-from-index` has produced the consulted page set
- A query needs a cited answer grounded in curated wiki pages
- The workflow must distinguish non-durable answers from durable candidates
- A retrieval gap or conflict needs to be preserved alongside the answer
- Query synthesis should remain separate from persistence review

## Contract

- Input: a retrieval brief with consulted pages, scope note, and relevant
  citations
- Output: a cited answer, gap note if needed, and a persistence recommendation
- Handoff artifact: an answer bundle containing the cited response, consulted
  pages, unresolved gaps, and non-durable-versus-durable recommendation
- Escalation artifact: a synthesis gap note describing why the answer needs new
  evidence, policy review, or Human Steward judgment
- Handoff rule: non-durable answers may return to the caller; durable candidates
  route to `prepare-high-value-synthesis-handoff` rather than writing directly

## Assertions

- Answers stay grounded in consulted wiki pages and citations
- Unsupported inference or raw-source supplementation is blocking
- Durable follow-up is a recommendation, not a side effect
- Gaps and conflicts remain visible to downstream governance
- No direct wiki write or persistence side effect occurs here

## Procedure

### Step 1: Read the retrieval brief

Confirm the consulted page set, scope limits, and cited support before drafting
the answer.

### Step 2: Compose the cited answer

Answer from the curated wiki with citations and explicit attribution to the
consulted material.

### Step 3: Classify follow-up value

Decide whether the result is purely non-durable, needs gap escalation, or looks
worthy of governed durable review.

### Step 4: Route the next step

Return non-durable answers to the caller, or send durable candidates to
`prepare-high-value-synthesis-handoff`.

## Boundaries

- Do not answer from uncited memory when the retrieval brief is incomplete
- Do not persist a query result directly from this skill
- Do not bypass `prepare-high-value-synthesis-handoff` for durable candidates
- Do not conceal scope limits or retrieval gaps

## Verification

- [ ] The answer is cited and grounded in the retrieval brief
- [ ] The output distinguishes non-durable results from durable candidates
- [ ] Gaps or conflicts are captured when present
- [ ] Durable candidates route to `prepare-high-value-synthesis-handoff`
- [ ] No direct write or persistence side effect occurs

## References

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`docs/ideas/wiki-curation-agent-framework.md`](../../../docs/ideas/wiki-curation-agent-framework.md)
- [`schema/page-template.md`](../../../schema/page-template.md)
- [`wiki/index.md`](../../../wiki/index.md)
