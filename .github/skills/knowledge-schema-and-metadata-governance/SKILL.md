---
name: knowledge-schema-and-metadata-governance
description: Governs wiki frontmatter and shared schema meaning. Use when validating required metadata, proposing optional fields, or deciding whether a schema change is advisory, blocking, or ADR-worthy.
---

# Knowledge Schema and Metadata Governance

## Overview

Use this skill to keep wiki metadata deterministic. It applies the repository's
schema governance contract rather than letting each page, agent, or script
reinterpret frontmatter independently.

## Classification

- **Mode:** Doc-only contract consumer
- **MVP status:** Active
- **Execution boundary:** Enforce the documented schema contract; do not add
  competing shared metadata rules or new script trees.

## Authoritative Inputs

- [`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md)
- [`schema/page-template.md`](../../../schema/page-template.md)
- [`schema/taxonomy-contract.md`](../../../schema/taxonomy-contract.md)
- [`schema/ontology-entity-contract.md`](../../../schema/ontology-entity-contract.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`AGENTS.md`](../../../AGENTS.md)

## When to Use

- Validating required frontmatter on wiki pages
- Deciding whether an optional field is acceptable
- Interpreting the semantics of `Summary`, `Aliases`, `Relationships`,
  `Evidence`, or `Open Questions`
- Proposing a new shared field or schema evolution step
- Determining whether a metadata issue is blocking or advisory

## Procedure

### Step 1: Check the baseline schema

Verify that the page or proposal respects the required baseline fields defined
in
[`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md).

### Step 2: Evaluate optional extensions

Only use reserved optional fields when their documented semantics are actually
needed. Treat undocumented shared fields as out of bounds until the contract is
updated.

### Step 3: Confirm cross-contract alignment

Metadata meaning must remain consistent with:

- page-template requirements
- taxonomy placement rules
- ontology/identity rules
- repository guardrails in `AGENTS.md`

### Step 4: Classify severity

Decide whether the issue is:

- **blocking** for write-capable automation
- **advisory** guidance that can be improved later
- **breaking** enough to require an ADR and migration plan

### Step 5: Hand off the governance outcome

Return:

- missing or invalid fields
- allowed optional fields in use
- blocking vs advisory findings
- schema-change follow-up, if any

## Boundaries

- Do not silently reinterpret existing field names.
- Do not make optional fields required without an ADR-backed change.
- Do not rely on undocumented fields as shared agent/script contracts.
- Do not mutate historical meaning in `wiki/log.md`; record new state instead.

## Verification

- [ ] Baseline required fields are present and valid
- [ ] Optional fields used are documented in the metadata contract
- [ ] Metadata does not conflict with taxonomy or ontology rules
- [ ] Blocking vs advisory findings are explicitly separated
- [ ] Breaking schema changes are routed to ADR/migration work
