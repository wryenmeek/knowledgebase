---
name: synthesize-entity-page
description: Drafts a policy-cleared entity wiki page from a verified evidence package. Use when evidence-verifier and policy-arbiter have cleared a source intake for entity synthesis, and the synthesis-curator persona must produce a schema-aligned page draft.
---

# Synthesize Entity Page

## Overview

This skill documents the entity-page synthesis step for the `synthesis-curator` persona.
It takes a policy-cleared evidence package (sealed intake manifest + policy-arbiter
clearance) and produces a draft entity page that conforms to `schema/page-template.md`
and `schema/ontology-entity-contract.md`. The draft is not published directly — it
routes back through `knowledgebase-orchestrator` for topology and index review before
any write gate opens.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Drafting only. No direct wiki write; draft routes back through
  `knowledgebase-orchestrator` before publication.

## When to Use

- `evidence-verifier` has confirmed provenance completeness for the source package
- `policy-arbiter` has cleared the package for entity synthesis
- The `synthesis-curator` lane needs a stable workflow reference for entity drafting
- A new real-world entity (person, organization, program, policy) needs a canonical page

## Contract

- Input: sealed intake manifest, policy-arbiter clearance, identified entity subject
  and type, and any relevant SourceRef citations
- Output: a draft entity page following `schema/page-template.md` with required
  frontmatter (`type: entity`, `status`, `sources`, `confidence`, `sensitivity`,
  `updated_at`, `tags`)
- Handoff: the draft is handed back to `knowledgebase-orchestrator` for topology
  review and then `sync-knowledgebase-state` for governed publication

## Assertions

- No entity page is drafted without a confirmed policy-arbiter clearance
- Draft frontmatter must satisfy all required keys from `schema/page-template.md`
- SourceRef citations in the draft must be syntactically valid
- No direct write to `wiki/**` is opened by this step
- Synthesis is limited to the cleared scope; out-of-scope claims must be escalated

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `schema/page-template.md`
- `schema/ontology-entity-contract.md`
- `schema/metadata-schema-contract.md`
- `.github/agents/synthesis-curator.md`
