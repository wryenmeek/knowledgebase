---
name: checksum-asset
description: Computes and records a deterministic SHA-256 checksum for a raw asset entering the intake boundary. Use when an asset in raw/assets/ needs its checksum verified or recorded before it can be referenced in a canonical SourceRef.
---

# Checksum Asset

## Overview

This skill documents the asset-checksumming step required before any `raw/assets/**`
artifact can be used as an authoritative source reference. The checksum provides the
`sha256=<64-hex>` component of a canonical SourceRef and ensures byte-level integrity
is verifiable after ingest.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Read-only integrity check. This step does not move or modify
  the asset.

## When to Use

- A binary or media asset arrives under `raw/assets/` and no checksum has been recorded
- A SourceRef for a `raw/assets/**` artifact is being constructed and needs the `sha256`
  field populated
- An existing checksum needs re-verification after a suspected corruption event
- A `validate-inbox-source` check has flagged a missing or unverifiable checksum

## Contract

- Input: repo-relative path to an asset under `raw/assets/`
- Output: a 64-hex SHA-256 digest verified against the file at the given path
- Handoff: the verified checksum is recorded in the intake manifest for this asset

## Assertions

- Only assets under `raw/assets/**` are eligible for this step
- Checksum mismatch, file-not-found, or symlink asset fails closed
- The checksum is computed deterministically and does not depend on external services
- This step does not write to `wiki/**`, `raw/processed/**`, or any governed artifact

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/decisions/ADR-006-authoritative-source-boundary.md`
- `raw/processed/SPEC.md`
- `schema/ingest-checklist.md`
- `schema/metadata-schema-contract.md`
