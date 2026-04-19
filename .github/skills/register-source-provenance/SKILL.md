---
name: register-source-provenance
description: Records canonical provenance metadata for a source artifact entering the intake boundary. Use when a new source is ready to transition from raw/inbox/ to the governed intake lane and provenance registration is the next required step.
---

# Register Source Provenance

## Overview

This skill documents the provenance-registration step that must precede any synthesis
or ingest activity. Registering provenance means assigning a stable canonical SourceRef,
confirming placement under `raw/inbox/`, recording checksums, and producing the intake
manifest entry that downstream steps depend on.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Assessment and provenance handoff only. Provenance registration
  does not move or modify the source artifact.

## When to Use

- A new artifact arrives under `raw/inbox/` and a stable SourceRef does not yet exist
- The `source-intake-steward` intake decision is `accept` and provenance is the next step
- A `validate-inbox-source` check has passed and a canonical identity is needed
- An operator needs to confirm that provenance is fully recorded before evidence review

## Contract

- Input: candidate source artifact path under `raw/inbox/`, available metadata fields
- Output: a canonical SourceRef in the form
  `repo://<owner>/<repo>/<path>@<git_sha>#<anchor>?sha256=<64-hex>`
- Handoff: the registered SourceRef becomes the mandatory citation anchor for all
  downstream synthesis steps

## Assertions

- Only artifacts staged under `raw/inbox/` are eligible for provenance registration
- The SourceRef `git_sha` must resolve to a real commit once the artifact is processed
  and becomes immutable in `raw/processed/**`
- Missing checksum, missing path, or invalid SourceRef shape fails closed
- This step does not open a write path to `wiki/**` or `raw/processed/**`

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/decisions/ADR-006-authoritative-source-boundary.md`
- `raw/processed/SPEC.md`
- `schema/ingest-checklist.md`
- `schema/metadata-schema-contract.md`
