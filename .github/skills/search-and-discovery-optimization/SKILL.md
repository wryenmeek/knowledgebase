---
name: search-and-discovery-optimization
description: Reviews how page titles, tags, and index placement affect retrieval. Use when improving wiki discoverability, assessing navigation gaps, or preparing recommendations for index and search-related follow-up.
---

# Search and Discovery Optimization

## Overview

Use this skill to operationalize discoverability review without dragging MVP into
a telemetry or KPI runtime. It is an active, doc-only contract consumer: inspect
existing discovery signals, isolate structural retrieval gaps, and route any
approved execution back through existing deterministic surfaces.

## Classification

- **Mode:** Doc-only contract consumer
- **MVP status:** Active
- **Execution boundary:** Recommendation and handoff only. Do not add telemetry
  pipelines, crawler jobs, external services, or broad optimization scripts in
  MVP.

## When to Use

- A page is hard to find by title, tag, alias, or browse path
- Related pages are weakly connected or buried in broad categories
- A maintainer wants discovery recommendations before rebuilding index surfaces
- Query or navigation feedback suggests a retrieval gap
- A topology or quality review needs a search-oriented lens

## Contract

- Input: one or more pages plus their current titles, tags, browse paths,
  namespace placement, and local topology context
- Decision model: identify the weakest discovery link and recommend the smallest
  contract-aligned structural improvement
- Output: a discovery review that names the issue category, proposed structural
  fix, and any governed follow-up required
- Handoff rule: deterministic refreshes or topology changes route to existing
  wrappers and governance review rather than executing here

## Assertions

- Discovery recommendations stay subordinate to canonical identity and taxonomy
- Prefer the smallest structural improvement over new runtime behavior
- Treat titles, tags, browse paths, and related links as distinct signals rather
  than interchangeable fixes
- Fail closed on changes that would require unsupported redirects, analytics, or
  external telemetry
- Keep the skill recommendation-only in MVP

## Procedure

### Step 1: Review current discovery signals

Inspect titles, aliases, tags, browse paths, namespace placement, and nearby
index or related-page context. Focus on structural causes of poor retrieval.

### Step 2: Identify the weakest discovery link

Classify the primary issue as one or more of:

- title mismatch
- tag quality problem
- browse-path or category weakness
- missing cross-link or related-page path
- index/topology follow-up needed

### Step 3: Recommend the smallest structural improvement

Prefer narrow, contract-aligned actions such as retitling for canonical clarity,
refining tags, improving `browse_path`, or requesting a governed index refresh
after structural changes are accepted.

### Step 4: Mark execution boundaries

If the recommendation needs deterministic execution, route it through
`sync-knowledgebase-state`, `review-wiki-plan`, or other existing governance
surfaces instead of inventing new automation here.

## Boundaries

- Do not add search telemetry systems, KPI jobs, or external-service
  integrations in MVP
- Do not override canonical identity just to chase keyword coverage
- Do not treat tags as a replacement for information architecture
- Do not add a new repo-level script tree for discovery work

## Verification

- [ ] Recommendations point back to taxonomy and metadata contracts
- [ ] Discovery issues are expressed as concrete structural gaps
- [ ] Proposed changes stay within MVP and ADR-007 boundaries
- [ ] Any execution follow-up is delegated to existing deterministic surfaces
- [ ] No unsupported freshness, KPI, or crawler runtime is introduced

## References

- [`schema/taxonomy-contract.md`](../../../schema/taxonomy-contract.md)
- [`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`docs/ideas/wiki-curation-agent-framework.md`](../../../docs/ideas/wiki-curation-agent-framework.md)
- [`AGENTS.md`](../../../AGENTS.md)
