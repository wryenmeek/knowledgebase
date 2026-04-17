---
name: search-and-discovery-optimization
description: Reviews how page titles, tags, and index placement affect retrieval. Use when improving wiki discoverability, assessing navigation gaps, or preparing recommendations for index and search-related follow-up.
---

# Search and Discovery Optimization

## Overview

This skill keeps search and navigation concerns visible without expanding MVP
into a new analytics runtime. In MVP it is a recommendation and prioritization
skill: inspect discovery signals, propose structural improvements, and hand off
any deterministic execution to existing tooling later.

## Classification

- **Mode:** Deferred
- **MVP status:** Scaffolding only
- **Execution boundary:** Recommendations only. Do not add telemetry pipelines,
  crawler jobs, or broad optimization scripts in MVP.

## Authoritative Inputs

- [`schema/taxonomy-contract.md`](../../../schema/taxonomy-contract.md)
- [`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`docs/ideas/wiki-curation-agent-framework.md`](../../../docs/ideas/wiki-curation-agent-framework.md)
- [`AGENTS.md`](../../../AGENTS.md)

## When to Use

- A page is hard to find by title, tag, or browse path
- Related pages are weakly connected or buried in broad categories
- A maintainer wants recommendations before rebuilding index or search surfaces
- Query or navigation feedback suggests discovery gaps
- A topology or quality review needs a search-oriented lens

## Procedure

### Step 1: Review current discovery signals

Inspect existing page titles, tags, browse paths, namespace placement, and
index/topology context. Focus on structural causes of poor retrieval.

### Step 2: Identify the weakest discovery link

Classify the main issue as one or more of:

- title mismatch
- tag quality problem
- browse-path/category weakness
- missing cross-link or related-page path
- index/topology follow-up needed

### Step 3: Recommend the smallest structural improvement

Prefer narrow, contract-aligned recommendations such as:

- retitle for canonical clarity
- add or refine discovery tags
- improve `browse_path`
- create a related-page follow-up
- rebuild index after accepted structural changes

### Step 4: Mark execution boundaries

If the recommendation needs deterministic execution, hand it off to existing
knowledgebase tooling and future thin-wrapper skills instead of inventing new
automation here.

## Boundaries

- Do not add search telemetry systems, KPI jobs, or external-service
  integrations in MVP.
- Do not override canonical identity just to chase keyword coverage.
- Do not treat tags as a replacement for information architecture.
- Do not add a new repo-level script tree for discovery work.

## Verification

- [ ] Recommendations point back to taxonomy/metadata contracts
- [ ] Discovery issues are expressed as concrete structural gaps
- [ ] Proposed changes stay within MVP and ADR-007 boundaries
- [ ] Any execution follow-up is delegated to existing deterministic surfaces or
  later wrapper work
