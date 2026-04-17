---
name: ontology-and-entity-modeling
description: Governs canonical subjects, aliases, and relationship vocabulary. Use when deciding whether knowledge belongs in an entity or concept page and when modeling durable identities across sources.
---

# Ontology and Entity Modeling

## Overview

Use the ontology contract to keep canonical subjects stable across edits,
sources, and page moves. This skill decides what the subject is, what it should
be called, and how it should relate to other canonical pages.

## Classification

- **Mode:** Doc-only contract consumer
- **MVP status:** Active
- **Execution boundary:** Apply the existing identity contract; do not add new
  ontology runtimes, merge automation, or alternate relation vocabularies.

## Authoritative Inputs

- [`schema/ontology-entity-contract.md`](../../../schema/ontology-entity-contract.md)
- [`schema/taxonomy-contract.md`](../../../schema/taxonomy-contract.md)
- [`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md)
- [`schema/page-template.md`](../../../schema/page-template.md)
- [`AGENTS.md`](../../../AGENTS.md)

## When to Use

- Deciding whether a subject deserves an entity page or concept page
- Choosing a canonical title for a durable referent
- Recording aliases supported by evidence
- Applying the controlled relationship vocabulary
- Deciding whether a case is a keep, merge, split, or escalation candidate

## Procedure

### Step 1: Resolve the durable referent

Identify the subject independent of any one source heading or temporary query.
If the subject is not durable, it may not warrant its own canonical page.

### Step 2: Choose the canonical representation

Use the contract to determine:

1. page type
2. canonical title
3. provisional identity key (`entity_id` when applicable)
4. supported aliases

Do not encode dates, workflow status, or confidence labels in the canonical
title.

### Step 3: Model relationships narrowly

Use only the current controlled vocabulary from
[`schema/ontology-entity-contract.md`](../../../schema/ontology-entity-contract.md).
Prefer the narrowest justified relation; fall back to `related_to` when needed.

### Step 4: Evaluate merge or split pressure

Check whether the case is really:

- one subject with aliases
- two distinct durable subjects
- a mixed entity/concept page that should be separated

If canonical identity cannot be chosen safely, escalate.

### Step 5: Hand off the identity decision

Return:

- page type recommendation
- canonical title
- aliases to retain
- relationships to capture
- merge/split/escalation note

## Boundaries

- Do not create competing canonical pages for aliases.
- Do not treat broader/narrower topics as aliases.
- Do not invent new relation names in MVP.
- Do not automate merges or redirects from this skill in MVP.

## Verification

- [ ] Canonical title follows the ontology contract for the page type
- [ ] Aliases are evidence-backed and not duplicates of the canonical title
- [ ] Relationships use the approved vocabulary only
- [ ] Merge/split decisions follow the contract's escalation rules
- [ ] Unresolved identity conflicts are treated as blocking
