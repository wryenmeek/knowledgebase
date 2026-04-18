---
name: extract-entities-and-claims
description: Extracts candidate entities, concepts, claims, and chronology from a policy-cleared evidence package without opening a write path. Use when a governed synthesis workflow needs a deterministic extraction bundle before drafting or escalation.
---

# Extract Entities and Claims

## Overview

Use this skill to turn a policy-cleared package into a compact extraction bundle
that downstream synthesis can review deterministically. In MVP it is a doc-only
workflow: inventory candidate entities, concepts, claims, and temporal context,
then route the result through governed handoff artifacts instead of writing
pages.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Extraction, packaging, and handoff only. Do not create
  pages, mutate `wiki/`, or invent claim-verification runtime here.

## When to Use

- `policy-arbiter` has cleared a source-backed package for controlled drafting
- `synthesis-curator` needs a normalized claim and entity inventory before
  deciding on create-versus-update planning
- A reviewer needs chronology, concepts, and candidate entities separated from
  raw package prose
- The package contains ambiguity that must be surfaced as open questions instead
  of being guessed away
- Drafting should stay deterministic and scoped before any durable follow-up

## Contract

- Input: a policy-cleared package, cited evidence set, and any scope memo from
  `policy-arbiter`
- Output: an extraction bundle naming candidate entities, concepts, claim units,
  chronology notes, cited support, and unresolved gaps
- Handoff artifact: an extraction bundle containing candidate page targets,
  SourceRef-backed claim inventory, chronology notes, and open-question flags
- Escalation artifact: an extraction ambiguity note describing unresolved
  identity, claim-boundary, or source-scope conflicts
- Handoff rule: extraction results go to `synthesis-curator` or back to
  `knowledgebase-orchestrator` for governance follow-up; they do not become
  direct page writes

## Assertions

- Only policy-cleared, evidence-backed inputs may be processed
- Claims stay attributable to cited evidence rather than blended into
  unsupported narrative
- Extraction remains separate from page identity, publication, or persistence
  decisions
- Ambiguity is preserved as an open question or escalation, not collapsed
- No direct durable write path opens from this skill

## Procedure

### Step 1: Confirm governed scope

Read the `policy-arbiter` scope memo and the cited evidence package so the
extraction stays inside the cleared boundary.

### Step 2: Inventory entities, concepts, and claims

List candidate entities, concepts, claim units, and relevant chronology markers
with their cited support.

### Step 3: Separate structure from draft prose

Record what appears supported without deciding final page wording, merge
behavior, or publication status.

### Step 4: Capture unresolved questions

Flag identity ambiguity, unsupported comparisons, or claim-boundary conflicts so
`record-open-questions` or Human Steward review can pick them up deterministically.

### Step 5: Route the bundle

Hand the extraction bundle to `synthesis-curator` for controlled drafting, or
return to `knowledgebase-orchestrator` when scope, evidence, or policy status is
no longer sufficient.

## Boundaries

- Do not read unadmitted `raw/inbox/**` material directly from this skill
- Do not decide final page identity outside the named ontology and taxonomy
  contracts
- Do not convert extraction notes into a direct write under `wiki/`
- Do not bypass `knowledgebase-orchestrator`, `evidence-verifier`, or
  `policy-arbiter` when durable follow-up is requested

## Verification

- [ ] Input package is explicitly policy-cleared and scope-bound
- [ ] Entities, concepts, claims, and chronology are recorded with citations
- [ ] Ambiguity is preserved in handoff or escalation artifacts
- [ ] The result routes to `synthesis-curator` or back through governance
- [ ] No direct write or persistence side effect is introduced

## References

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`docs/decisions/ADR-007-control-plane-layering-and-packaging.md`](../../../docs/decisions/ADR-007-control-plane-layering-and-packaging.md)
- [`docs/ideas/wiki-curation-agent-framework.md`](../../../docs/ideas/wiki-curation-agent-framework.md)
- [`schema/ontology-entity-contract.md`](../../../schema/ontology-entity-contract.md)
- [`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md)
- [`schema/page-template.md`](../../../schema/page-template.md)
- [`raw/processed/SPEC.md`](../../../raw/processed/SPEC.md)
