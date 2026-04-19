---
name: claim-inventory
description: Enumerates and attributes factual claims from a source intake package without opening a write path. Use when evidence-verifier needs a structured claim list before policy review, or when an operator needs to assess claim coverage before synthesis begins.
---

# Claim Inventory

## Overview

This skill documents the claim-enumeration step for the `evidence-verifier` persona.
A claim inventory is a read-only, structured list of factual assertions extracted from
a source package — each with its SourceRef citation and confidence indicator. The
inventory feeds evidence review and policy arbitration, but does not itself open a
synthesis or write path.

**Doc-only workflow — read-only only.** No `logic/` dir is introduced.

Any future extension that would enable automated claim extraction, claim writeback,
or durable claim storage would constitute new automation and requires explicit
maintainer approval per spec.md before any `logic/` dir is created.

## Classification

- **Mode:** Doc-only workflow — read-only only
- **MVP status:** Active
- **Execution boundary:** Read-only assessment only. No write path is opened by
  claim inventory.

## When to Use

- An intake manifest has been sealed and `evidence-verifier` needs a structured
  evidence surface before policy review
- An operator needs to assess which factual claims a source supports before
  assigning them to entity or concept pages
- A `policy-arbiter` review requires an explicit claim list to evaluate scope and
  policy risk
- A synthesis step has ambiguous source coverage and the claim inventory is needed
  to determine scope boundaries

## Contract

- Input: a sealed intake manifest (or equivalent source reference) and the source
  text or summary
- Output: a structured list of claims, each with its SourceRef citation, subject,
  predicate, and confidence indicator
- Handoff: the claim inventory is passed to `evidence-verifier` and then
  `policy-arbiter`; no synthesis begins without policy clearance

## Assertions

- No write path is opened by this skill
- Claim inventory is produced from source evidence only — no synthesis, interpolation,
  or original research is permitted
- Any unsupported claim, missing SourceRef, or ambiguous attribution must be flagged
  for escalation, not silently omitted
- Automated claim extraction or writeback requires explicit approval before any
  `logic/` dir is added here

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `schema/ingest-checklist.md`
- `schema/metadata-schema-contract.md`
- `.github/agents/evidence-verifier.md`
