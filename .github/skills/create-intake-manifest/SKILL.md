---
name: create-intake-manifest
description: Assembles the deterministic intake manifest that evidence-verifier and policy-arbiter require before any governed wiki write can open. Use when all provenance, checksum, and source-type prerequisites have been collected and the intake package must be sealed for downstream review.
---

# Create Intake Manifest

## Overview

This skill documents the intake-manifest assembly step that seals a source package
for evidence review. An intake manifest is an immutable structured record that
captures: the canonical SourceRef, the source type, any checksums, the `raw/inbox/`
path, intake decision, and the set of prerequisites verified by
`validate-inbox-source` and `register-source-provenance`.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Intake-safe gate only. Manifest creation does not open a
  write path to `wiki/**` or `raw/processed/**`.

## When to Use

- A source has passed provenance registration and checksum verification
- A `validate-inbox-source` check has returned `accept` for this artifact
- The `evidence-verifier` step requires a sealed intake package to review
- The `source-intake-steward` handoff must route a complete, immutable evidence record

## Contract

- Input: canonical SourceRef, source type, checksum record, intake decision, and any
  missing-prerequisite flags from prior intake steps
- Output: an immutable intake manifest JSON (or structured YAML) that references all
  prior intake step results
- Handoff: the sealed manifest is the required input for `evidence-verifier`; no
  downstream lane may open without it

## Assertions

- Manifest assembly fails closed if any required prerequisite (provenance, checksum,
  source type) is missing or invalid
- The manifest is immutable once sealed; no downstream step may modify it in place
- Manifest does not contain synthesized content — only intake facts and status fields
- Write to `wiki/**` or `raw/processed/**` is not opened by this step

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/decisions/ADR-006-authoritative-source-boundary.md`
- `raw/processed/SPEC.md`
- `schema/ingest-checklist.md`
- `schema/metadata-schema-contract.md`
