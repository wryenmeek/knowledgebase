---
name: suggest-backlinks
description: Recommends governed backlink opportunities between already-cleared pages. Use when editorial follow-up needs contract-aligned related-link suggestions without silently editing the graph.
---

# Suggest Backlinks

## Overview

Use this skill to propose narrow backlink improvements between curated pages
without turning MVP into a link-rewriter. It is an active, read-only logic
skill: the scanner inspects cleared pages, identifies structurally justified
backlink opportunities, and hands the recommendation back through governed
follow-up.

## Classification

- **Mode:** Read-only logic skill
- **MVP status:** Active
- **Execution boundary:** Recommendation only. No direct page edit or
  persistence side effect occurs here.

## When to Use

- A new or revised page should likely be discoverable from an existing sibling
  or parent page
- A topology review finds one-way relationships that deserve a reciprocal link
- Editorial review needs specific backlink suggestions before making manual page
  edits
- Discoverability can improve through related-link structure rather than alias
  churn
- A cleared topology bundle needs candidate backlinks packaged for follow-up

## Contract

- Input: current page set, relationship context, and a cleared topology scope
- Decision model: identify the smallest backlink recommendations justified by
  taxonomy, identity, and metadata evidence
- Output: a backlink suggestion bundle naming source page, target page, link
  rationale, and any blocking questions
- Handoff rule: route accepted suggestions back to `topology-librarian` or
  `knowledgebase-orchestrator`; alias- or redirect-changing backlink proposals
  are escalation items, not automatic fixes

## Assertions

- Backlink suggestions must reinforce canonical discovery, not create parallel
  identity paths
- Prefer relationship- or taxonomy-backed links over speculative “see also”
  sprawl
- Suggestions stay narrow, human-reviewable, and page-scoped
- Redirect or alias-changing behavior remains explicitly governed rather than
  silently automated
- No graph crawler, ranking engine, or mass backlink generator is introduced in
  MVP

## Scanner

The `logic/suggest_backlinks.py` scanner automates Steps 1–2 for the
neighborhood-scoped case. Run from the repository root:

```bash
python3 .github/skills/suggest-backlinks/logic/suggest_backlinks.py <page> [--wiki-root wiki]
```

The scanner returns a JSON list of `BacklinkProposal` objects
(`source_file`, `source_line`, `surface_text`, `suggested_link`, `rationale`).
Neighborhood is bounded to the candidate's namespace plus pages it already
links to — no repo-wide crawl.

## Procedure

### Step 1: Gather the cleared page neighborhood

Read the candidate page, nearby siblings, existing related links, and relevant
index context. Stay inside already-cleared curated material.

### Step 2: Check structural justification

Confirm the suggested backlink is supported by taxonomy placement, canonical
identity, or an explicit relationship vocabulary rather than keyword overlap
alone.

### Step 3: Package backlink recommendations

For each suggestion, capture:

- source page
- target page
- relationship or taxonomy reason
- whether the link is additive or blocked by an identity question

### Step 4: Escalate identity-sensitive cases

If a backlink would only make sense after alias normalization, redirect
behavior, or canonical merge/split work, return to
`entity-resolution-and-canonicalization` and governed review instead of forcing
the link.

## Boundaries

- Do not auto-edit page bodies, aliases, or redirects from this skill
- Do not infer canonical identity from anchor text alone
- Do not suggest backlinks that contradict taxonomy placement
- Do not introduce repo-wide crawl or scoring automation in MVP

## Verification

- [ ] Each suggestion cites a taxonomy, identity, or metadata rationale
- [ ] Recommendations stay additive and page-scoped
- [ ] Alias- or redirect-sensitive cases are escalated instead of auto-fixed
- [ ] Output returns through `topology-librarian` or `knowledgebase-orchestrator`
- [ ] No direct page mutation or heavyweight topology runtime is introduced

## References

- [`schema/taxonomy-contract.md`](../../../schema/taxonomy-contract.md)
- [`schema/ontology-entity-contract.md`](../../../schema/ontology-entity-contract.md)
- [`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md)
- [`schema/page-template.md`](../../../schema/page-template.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`AGENTS.md`](../../../AGENTS.md)
- [`wiki/index.md`](../../../wiki/index.md)
