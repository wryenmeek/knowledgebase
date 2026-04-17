---
name: information-architecture-and-taxonomy
description: Governs wiki namespace placement, browse paths, and tags. Use when creating or restructuring knowledge pages so findability follows the taxonomy contract instead of ad hoc page-by-page choices.
---

# Information Architecture and Taxonomy

## Overview

Use the repository's taxonomy contract to decide where a page lives, how it is
named, and how humans should discover it. This skill is about structural
placement, not content drafting.

## Classification

- **Mode:** Doc-only contract consumer
- **MVP status:** Active
- **Execution boundary:** Read and apply contracts; do not add repo-level
  automation or alternate taxonomy logic in MVP.

## Authoritative Inputs

- [`schema/taxonomy-contract.md`](../../../schema/taxonomy-contract.md)
- [`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md)
- [`schema/page-template.md`](../../../schema/page-template.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`AGENTS.md`](../../../AGENTS.md)

## When to Use

- Placing a new page in `wiki/sources/`, `wiki/entities/`, `wiki/concepts/`, or
  `wiki/analyses/`
- Choosing or reviewing `browse_path`
- Normalizing page tags for discovery
- Checking whether a proposed category or namespace move is valid
- Preventing local page edits from drifting away from the shared taxonomy model

## Procedure

### Step 1: Read the taxonomy contract first

Do not invent namespace or category rules from memory. Start with the namespace,
slug, browse-path, and tag sections of
[`schema/taxonomy-contract.md`](../../../schema/taxonomy-contract.md).

### Step 2: Classify the page role

Determine whether the artifact is a:

- `source`
- `entity`
- `concept`
- `analysis`
- reserved `process` page

Namespace and frontmatter `type` must agree.

### Step 3: Assign structural placement

Produce the minimum structural recommendation:

1. canonical namespace
2. stable kebab-case slug
3. optional `browse_path`
4. normalized tags

Prefer the narrowest durable structure that the contract already allows.

### Step 4: Check for blocking issues

Stop and escalate when:

- namespace is ambiguous
- placement conflicts with page purpose
- the slug would duplicate an existing canonical subject
- `browse_path` depends on aliases, dates, or workflow state

### Step 5: Hand off a structural decision

Return a concise recommendation such as:

- target path
- frontmatter `type`
- proposed `browse_path`
- proposed tags
- open questions or escalation notes

## Boundaries

- Do not create nested topical trees in MVP unless a later ADR explicitly allows
  them.
- Do not duplicate contract text inside page drafts; link back to the contract.
- Do not use tags as a substitute for namespace or canonical identity.
- Do not add logic folders or wrapper scripts for this skill in MVP.

## Verification

- [ ] Namespace matches the page role defined in the taxonomy contract
- [ ] Slug is stable lowercase kebab-case
- [ ] `browse_path`, if present, uses durable normalized segments
- [ ] Tags add discovery value instead of restating namespace/title
- [ ] Any ambiguity is escalated instead of guessed
