---
name: retrieve-from-index
description: Retrieves relevant curated wiki pages and index entries before synthesis begins. Use when a query workflow must consult `wiki/index.md` and scoped page evidence before answering or escalating.
---

# Retrieve From Index

## Overview

Use this skill to make query synthesis start from the curated wiki rather than
from raw-source improvisation. In MVP it is a doc-only workflow: consult
`wiki/index.md`, gather the relevant page set, and produce a retrieval brief for
the next step.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Retrieval and packaging only. Do not create new index
  state, mutate wiki pages, or read unadmitted raw material here.

## When to Use

- `query-synthesist` receives a new question
- A query needs the relevant wiki pages and their scope gathered first
- The workflow must prove it read curated pages before synthesizing an answer
- Gaps in the curated wiki need to be surfaced before any durable follow-up
- Retrieval scope must be captured for later governance review

## Contract

- Input: a user or orchestrator query plus current curated wiki scope
- Output: a retrieval brief listing consulted index entries, relevant pages, and
  known gaps
- Handoff artifact: a retrieval brief containing the query, consulted pages,
  relevant citations, and explicit scope limits
- Escalation artifact: a retrieval gap note naming missing pages, unresolved
  scope, or blocked retrieval conditions
- Handoff rule: retrieval output feeds `synthesize-cited-answer` or returns to
  `knowledgebase-orchestrator`; it never becomes persistence on its own

## Assertions

- Retrieval starts with `wiki/index.md` and curated wiki pages
- Scope is explicit enough for downstream citation and policy review
- Missing coverage is surfaced rather than hidden
- Retrieval does not reopen raw-source intake outside governed lanes
- No direct write or persistence action happens here

## Procedure

### Step 1: Read the curated index

Start from `wiki/index.md` and identify the relevant browse paths or page names.

### Step 2: Gather the consulted page set

Collect the pages needed to answer the query safely and note their scope.

### Step 3: Record retrieval gaps

Capture what the current wiki cannot answer or where new evidence would be
required.

### Step 4: Pass the retrieval brief forward

Send the retrieval brief to `synthesize-cited-answer` or return it to
`knowledgebase-orchestrator` if the query cannot proceed safely.

## Boundaries

- Do not answer from memory or uncited inference before retrieval completes
- Do not pull from `raw/inbox/**` or other ungated sources
- Do not mutate `wiki/index.md` or create discovery artifacts from this skill
- Do not bypass governance when retrieval shows the answer needs new evidence

## Verification

- [ ] `wiki/index.md` is consulted first
- [ ] Relevant pages and scope limits are named
- [ ] Coverage gaps are explicit
- [ ] Output routes to `synthesize-cited-answer` or back through governance
- [ ] No direct persistence or content mutation occurs

## References

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`docs/ideas/wiki-curation-agent-framework.md`](../../../docs/ideas/wiki-curation-agent-framework.md)
- [`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md)
- [`wiki/index.md`](../../../wiki/index.md)
