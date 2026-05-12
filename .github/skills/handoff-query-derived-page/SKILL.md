---
name: handoff-query-derived-page
description: Converts a durable-worthy query result into a governed editorial handoff package without direct publication. Use when a query answer may justify a future page or page update but must route back through control-plane gates first.
---

# Handoff Query Derived Page

## Overview

Use this skill when a query answer looks like the seed for future editorial work
but still needs the full control plane. In MVP it is a doc-only workflow: frame
the editorial candidate, preserve citations and blockers, and return the package
to governed lanes instead of writing directly.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Packaging and routing only. Do not create or update a
  wiki page from this skill.

## When to Use

- `prepare-high-value-synthesis-handoff` has identified a durable-worthy query
  result
- A query answer may justify a future page create or page update
- Editorial follow-up needs a deterministic handoff package rather than direct
  drafting
- The workflow must show how query-derived insight re-enters governance
- A reviewer needs explicit blockers before any downstream drafting lane opens

## Contract

- Input: a high-value synthesis handoff plus cited answer bundle and scope note
- Output: a query-derived editorial handoff package naming the proposed page
  target, citations, blockers, and required governance re-entry
- Handoff artifact: a query-derived page handoff containing the candidate page
  intent, cited support, consulted scope, and re-entry path
- Escalation artifact: a query-derived editorial ambiguity note describing why a
  page candidate cannot be safely proposed yet
- Handoff rule: all outputs return to `knowledgebase-orchestrator`, which may
  reopen `evidence-verifier`, `policy-arbiter`, or `synthesis-curator` within
  cleared scope only

## Assertions

- Query-derived editorial candidates remain citation-backed and scope-bounded
- Governance re-entry is explicit for every durable candidate
- Ambiguous page identity, taxonomy, or policy status blocks direct drafting
- The skill does not create a second publication or persistence runtime
- No direct wiki write is permitted from this skill

## Procedure

### Step 1: Restate the editorial candidate

Summarize the proposed page create/update intent and the cited answer that led to
it.

### Step 2: Attach blockers and scope

Record missing evidence, policy uncertainty, identity ambiguity, or schema gaps
that still require governed review.

### Step 3: Name the re-entry path

Return the package to `knowledgebase-orchestrator` so the request can re-enter
`evidence-verifier`, `policy-arbiter`, and only then `synthesis-curator` if
appropriate.

## Boundaries

- Do not draft or publish the page directly
- Do not skip back to `synthesis-curator` without orchestrator and governance
  re-entry
- Do not drop citations, consulted scope, or blocker notes from the package
- Do not invent ad hoc editorial queues or out-of-band storage

## Verification

- [ ] The candidate remains citation-backed and scope-bounded
- [ ] Re-entry through `knowledgebase-orchestrator` is explicit
- [ ] Required governance lanes are named before drafting can resume
- [ ] Ambiguity is preserved as an escalation artifact when needed
- [ ] No direct page write occurs

## References

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`docs/ideas/wiki-curation-agent-framework.md`](../../../docs/ideas/wiki-curation-agent-framework.md)
- [`schema/page-template.md`](../../../schema/page-template.md)
- [`scripts/kb/persist_query.py`](../../../scripts/kb/persist_query.py)
