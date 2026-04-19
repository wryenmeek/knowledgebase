---
name: run-ingest
description: Thin wrapper over scripts/kb/ingest.py for governed source ingestion. Use when a source-intake-steward or evidence-verifier handoff is ready and an operator needs to run the deterministic ingest pipeline without invoking repo-wide automation.
---

# Run Ingest

## Overview

This skill is a thin operator-facing wrapper over `scripts/kb/ingest.py`. It documents
the typed CLI contract for the ingest entrypoint so that persona workflows
(`source-intake-steward`, `evidence-verifier`) can reference a stable interface
without embedding ingest-specific knowledge in each persona.

**Doc-only workflow.** No `logic/` dir is introduced here. All ingest logic stays
in `scripts/kb/ingest.py` per the MVP boundary rule. If a `logic/` dir is ever
added to this skill in the future, an AGENTS.md write-surface matrix row becomes
mandatory before that change can merge.

## Classification

- **Mode:** Doc-only workflow wrapper
- **MVP status:** Active
- **Execution boundary:** All ingest execution runs through `scripts/kb/ingest.py`
  from the repository root. This skill is a navigation and procedure aid only.

## When to Use

- A source has passed `source-intake-steward` provenance checks and is ready to ingest
- A `evidence-verifier` handoff explicitly authorizes the ingest step
- An operator needs a reference for the `ingest.py` CLI contract and output behavior
- The governed intake lane needs a stable wrapper name in persona handoff documents

## Contract

- Input: a repo-relative path to the source file under `raw/inbox/`
- Execution: `python3 scripts/kb/ingest.py <source-path>` from the repository root
- Output: structured ingest result written to `raw/processed/**` and wiki artifacts
  updated according to the ingest contract
- Handoff: ingest results must be verified by the evidence layer before any wiki
  synthesis step begins

## Assertions

- Only intake-ready artifacts from `raw/inbox/` may be passed as ingest inputs
- ADR-006 authoritative source boundary always applies: `raw/inbox/**` and checksummed
  `raw/assets/**` are the only allowed input roots
- Write output lands in `raw/processed/**` and `wiki/**` only, under ADR-005 locking
- Any missing provenance, unsupported source type, or partial ingest result fails closed
- No `logic/` dir is introduced by this skill; adding one requires an AGENTS.md row first

## Commands

Run from the repository root:

```bash
python3 scripts/kb/ingest.py raw/inbox/<source-file>
```

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/decisions/ADR-005-write-lock-and-concurrency.md`
- `docs/decisions/ADR-006-authoritative-source-boundary.md`
- `docs/decisions/ADR-007-control-plane-layering-and-packaging.md`
- `raw/processed/SPEC.md`
- `schema/ingest-checklist.md`
- `scripts/kb/ingest.py`
