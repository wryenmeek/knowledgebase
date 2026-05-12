---
name: synthesize-concept-page
description: Drafts a policy-cleared concept wiki page from a verified evidence package. Use when evidence-verifier and policy-arbiter have cleared a source intake for concept synthesis, and the synthesis-curator persona must produce a schema-aligned page draft.
---

# Synthesize Concept Page

## Overview

This skill documents the concept-page synthesis step for the `synthesis-curator` persona.
It takes a policy-cleared evidence package and produces a draft concept page that conforms
to `schema/page-template.md` and `schema/taxonomy-contract.md`. Concepts describe
recurring ideas, policies, or patterns — not unique real-world entities. The draft is
not published directly; it routes back through `knowledgebase-orchestrator` before any
write gate opens.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Drafting only. No direct wiki write; draft routes back through
  `knowledgebase-orchestrator` before publication.

## When to Use

- `evidence-verifier` has confirmed provenance completeness for the source package
- `policy-arbiter` has cleared the package for concept synthesis
- A recurring idea, category, or definition needs a canonical wiki page
- The `synthesis-curator` lane needs a stable workflow reference for concept drafting

## Contract

- Input: sealed intake manifest, policy-arbiter clearance, identified concept subject,
  and any relevant SourceRef citations
- Output: a draft concept page following `schema/page-template.md` with required
  frontmatter (`type: concept`, `status`, `sources`, `confidence`, `sensitivity`,
  `updated_at`, `tags`)
- Handoff: the draft is handed back to `knowledgebase-orchestrator` for topology
  review and then `sync-knowledgebase-state` for governed publication

## Assertions

- No concept page is drafted without confirmed policy-arbiter clearance
- The page type must be `concept` — do not use this skill for entity pages
- Draft frontmatter must satisfy all required keys from `schema/page-template.md`
- No direct write to `wiki/**` is opened by this step
- Synthesis is limited to the cleared scope; out-of-scope claims must be escalated

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `schema/page-template.md`
- `schema/taxonomy-contract.md`
- `schema/metadata-schema-contract.md`
- `.github/agents/synthesis-curator.md`
