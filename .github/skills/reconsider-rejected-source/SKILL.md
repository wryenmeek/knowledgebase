---
name: reconsider-rejected-source
description: "Reconsiders a previously rejected source by appending reconsidered_date and re-entering the intake pipeline. Use when an operator believes a prior rejection should be revisited because circumstances have changed."
---

# reconsider-rejected-source

## Overview

Operator-initiated workflow to reconsider a previously rejected source.
The `reconsidered_date` field is appended to the existing record's frontmatter;
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
4. Append `reconsidered_date: <ISO-8601>` to the rejection record's
   frontmatter (replacing the `null` value).
5. Release `raw/.rejection-registry.lock`.
6. If the source is not in `raw/inbox/`, instruct the operator to re-submit it.
7. The source then re-enters the full intake pipeline
   (`source-intake-steward` → `evidence-verifier` → `policy-arbiter` →
   downstream).
8. If the source is rejected again (same `sha256`), the original rejection
   record remains — a new record is NOT created (`sha256` dedupe prevents it).
   The `reconsidered_date` serves as audit trail that reconsideration was
   attempted.

## Note

The original rejection record is NEVER deleted — this preserves the audit trail.
A reconsidered source that passes intake on the second attempt has both a
rejection record (with `reconsidered_date` set) and a successful
`raw/processed/` artifact.
