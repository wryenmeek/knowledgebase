---
name: reconsider-rejected-source
description: "Reconsiders a previously rejected source by setting reconsidered_date and re-entering the intake pipeline. Use when an operator believes a prior rejection should be revisited because circumstances have changed."
---

# reconsider-rejected-source

## Overview

Operator-initiated workflow to reconsider a previously rejected source.
The `reconsidered_date` field is set in the existing record's frontmatter;
the original rejection record is never modified or deleted.

## Runtime mode

Doc-only workflow. No `logic/` directory. The operator follows this procedure
manually or via orchestrator guidance.

## When to Use

- When a previously rejected source should be re-evaluated due to changed
  circumstances or new information

## Prerequisites

Operator has identified a specific rejection record in `raw/rejected/` and has
justification for reconsideration.

## Procedure

1. Locate the rejection record by `sha256` or slug.
2. Verify the source material is still available (in `raw/inbox/` or
   re-submitted). If the source is unavailable, stop — the operator must
   re-submit before reconsideration can proceed.
3. Acquire `raw/.rejection-registry.lock`.
4. Set `reconsidered_date: <ISO-8601>` in the rejection record's frontmatter
   (updating from `null` or from a prior reconsideration timestamp).
   **Do not modify any other field or body section.** The rejection reason,
   category, body sections, and all other fields are immutable.
5. Release `raw/.rejection-registry.lock`.
6. Acquire `wiki/.kb_write.lock` and append a reconsideration event to
   `wiki/log.md` (via `append-log-entry`). Release `wiki/.kb_write.lock`.
   If log append fails, the `reconsidered_date` update is already persisted;
   log the failure for operator remediation.
7. If the source is not in `raw/inbox/`, instruct the operator to re-submit it.
8. The source then re-enters the full intake pipeline
   (`source-intake-steward` → `evidence-verifier` → `policy-arbiter` →
   downstream).
9. If the source is rejected again (same `sha256`), `log-intake-rejection`
   will fail closed on the sha256 dedupe check — this is expected behavior.
   The original rejection record (with `reconsidered_date` set) serves as
   the complete audit trail. No new record is needed.

## Note

The original rejection record is NEVER deleted — this preserves the audit trail.
A reconsidered source that passes intake on the second attempt has both a
rejection record (with `reconsidered_date` set) and a successful
`raw/processed/` artifact.

## Hard-fail conditions

- Lock unavailable (`raw/.rejection-registry.lock` or `wiki/.kb_write.lock`).
- Source unavailable and operator cannot re-submit.
- `wiki/log.md` append failure (reconsidered_date update is already persisted;
  exit with error for operator remediation, not rollback).

## References

- `docs/decisions/ADR-013-rejected-source-registry.md`
- `schema/rejection-registry-contract.md`
- `.github/skills/log-intake-rejection/SKILL.md`
