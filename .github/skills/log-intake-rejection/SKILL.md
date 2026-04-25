---
name: log-intake-rejection
description: "Persists a rejection record in raw/rejected/ when source intake fails. Use when source-intake-steward or evidence-verifier rejects a source and the rejection must be recorded for organizational memory. Write-once, sha256-keyed, locked."
---

# log-intake-rejection

## Overview

Creates a write-once rejection record in `raw/rejected/` after a source fails
intake validation. Provides persistent organizational memory to prevent
re-evaluation churn.

## When to Use

- When source-intake-steward or evidence-verifier rejects a source
- When the rejection must be recorded for organizational memory
- When preventing re-evaluation churn for previously rejected sources

## Runtime mode

`blocking-only` with narrow write capability.

## Writable paths

- `raw/rejected/<slug>--<sha256-prefix-8>.rejection.md` (write-once).
- `wiki/log.md` (append-only rejection event via `append-log-entry`).

## Lock

`raw/.rejection-registry.lock` — acquired before rejection record write, released after.
Then `wiki/.kb_write.lock` — acquired for `wiki/log.md` append, released after.
The two locks are never held simultaneously (sequential acquisition).

## Prerequisites

- Source has been evaluated and rejected by `source-intake-steward` or
  `evidence-verifier`.
- Rejection metadata provided: `slug`, `sha256`, `source_path`,
  `rejection_reason`, `rejection_category`, `reviewed_by`.

## Procedure

1. Acquire `raw/.rejection-registry.lock`.
2. Compute filename: `<slug>--<sha256[:8]>.rejection.md`.
3. Check for existing record by `sha256` (scan `raw/rejected/` frontmatter).
   If duplicate found → fail closed.
4. Write rejection record per `schema/rejection-registry-contract.md`.
5. Release `raw/.rejection-registry.lock`.
6. Acquire `wiki/.kb_write.lock` and append rejection event to `wiki/log.md`
   (via `append-log-entry` skill). Release
   `wiki/.kb_write.lock`. If log append fails → fail closed (the rejection
   record is already written; log the failure for operator remediation).

## Hard-fail conditions

- Path outside `raw/rejected/`.
- Record already exists for this `sha256`.
- Lock unavailable (`raw/.rejection-registry.lock` or `wiki/.kb_write.lock`).
- Missing rejection metadata.
- `wiki/log.md` append failure (rejection record is already persisted; fail-closed
  means exit with error for operator remediation, not rollback).

## References

- `docs/decisions/ADR-013-rejected-source-registry.md`
- `schema/rejection-registry-contract.md`
