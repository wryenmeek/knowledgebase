---
name: check-link-topology
description: Reviews link topology impacts of cleared wiki changes. Use when a governed editorial change needs deterministic graph-focused follow-up without introducing crawl-heavy automation.
---

# Check Link Topology

## Overview

Use this skill to review local link structure after policy-cleared structural
changes. In MVP it remains a workflow contract first: inspect the affected page
neighborhood, classify topology risks, and package governed follow-up rather
than mutating the graph directly. The attached helper stays read-only and
validates bounded topology expectations for a supplied wiki scope.

## Classification

- **Mode:** Workflow contract with attached deterministic helper
- **MVP status:** Active
- **Execution boundary:** Review, handoff, and read-only topology validation
  only. No direct topology mutation occurs here.

## When to Use

- A cleared page add, move, merge, split, or retirement may leave stale links
- A proposed index or backlink change needs local topology review first
- Editorial follow-up needs a bounded check of incoming and outgoing link impact
- A topology bundle needs graph-focused risk notes before execution
- Discoverability issues appear structural, but runtime crawling would be
  overkill

## Contract

- Input: cleared change scope, affected page set, current links, and relevant
  `wiki/index.md` context
- Decision model: classify local topology follow-up as additive, stale-link,
  missing-backlink, or escalate
- Output: a topology review bundle listing affected pages, issue category,
  governing rule, and next step
- Handoff rule: approved follow-up routes to `suggest-backlinks`,
  `update-index`, or `topology-librarian`; changes that depend on redirect or
  alias semantics must return to governance first

## Assertions

- Review the smallest affected page neighborhood, not the whole repository
- Topology recommendations stay subordinate to taxonomy placement and canonical
  identity
- Stale-link detection is local, deterministic, and evidence-backed
- Redirect or alias-changing behavior remains explicitly governed rather than
  silently automated
- Do not run a crawler, graph database, or broad runtime scan in MVP

## Commands

```bash
python3 .github/skills/check-link-topology/logic/validate_wiki_topology.py --page wiki/sources/example.md
```

## Procedure

### Step 1: Define the bounded topology scope

List the affected pages, their nearby linked pages, and the relevant index
entries. Keep the scope narrow and explicit.

### Step 2: Classify the local topology impact

Determine whether the cleared change creates:

- a missing additive link
- a stale or superseded link
- a missing backlink opportunity
- an ambiguous identity/topology case that must escalate

### Step 3: Package governed follow-up

Name the affected pages, the issue type, and the recommended downstream step.
Use `suggest-backlinks` for additive reciprocal links and `update-index` for
curated index follow-up.

### Step 4: Stop before graph mutation

If the topology issue would require alias rewrites, redirect behavior, or
identity reinterpretation, return to `knowledgebase-orchestrator`,
`review-wiki-plan`, or `entity-resolution-and-canonicalization` instead of
forcing a graph fix here.

## Boundaries

- Do not rewrite page links directly from this skill
- Do not treat local link counts as a substitute for taxonomy review
- Do not scan the whole repo or build a persistent graph runtime in MVP
- Do not bypass governance for redirect, alias, or identity-sensitive changes

## Verification

- [ ] Scope is bounded to the affected page neighborhood
- [ ] Output classifies the issue as additive, stale-link, missing-backlink, or escalate
- [ ] Follow-up routes to governed topology skills instead of direct mutation
- [ ] Redirect or alias-sensitive cases return to governance
- [ ] No crawler or heavyweight runtime is introduced

## References

- [`schema/taxonomy-contract.md`](../../../schema/taxonomy-contract.md)
- [`schema/ontology-entity-contract.md`](../../../schema/ontology-entity-contract.md)
- [`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md)
- [`schema/page-template.md`](../../../schema/page-template.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`AGENTS.md`](../../../AGENTS.md)
- [`wiki/index.md`](../../../wiki/index.md)
