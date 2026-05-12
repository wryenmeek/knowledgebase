---
name: persist-query-result
description: Thin wrapper over scripts/kb/persist_query.py for governed query persistence. Use when a query-synthesist or policy-arbiter handoff has cleared a query result for durable storage and explicit persistence approval is in scope.
---

# Persist Query Result

## Overview

This skill is a thin operator-facing wrapper over `scripts/kb/persist_query.py`. It
documents the typed CLI contract for the query-persistence entrypoint so that
downstream persona workflows (`query-synthesist`, `knowledgebase-orchestrator`) can
reference a stable surface without embedding persistence-specific logic in each persona.

**Doc-only workflow.** No `logic/` dir is introduced here. All persistence logic stays
in `scripts/kb/persist_query.py` per the MVP boundary rule. If a `logic/` dir is ever
added to this skill in the future, an AGENTS.md write-surface matrix row becomes
mandatory before that change can merge.

**Policy-arbiter clearance is required before invoking this skill in any automated
or governed write flow.** Query persistence is a downstream synthesis step that follows
the full `knowledgebase-orchestrator` → `source-intake-steward` → `evidence-verifier`
→ `policy-arbiter` sequence. Invocation without this clearance violates the governing
lane order and must fail closed.

## Classification

- **Mode:** Doc-only workflow wrapper
- **MVP status:** Active
- **Execution boundary:** All persistence execution runs through
  `scripts/kb/persist_query.py` from the repository root. This skill is a navigation
  and procedure aid only.

## When to Use

- A `query-synthesist` result has been cleared by `policy-arbiter` for durable storage
- The `knowledgebase-orchestrator` has authorized the persistence step in a governed
  lane sequence
- An operator needs a reference for the `persist_query.py` CLI contract
- A handoff document needs a stable wrapper name for the persistence surface

## Contract

- Input: a query result payload (JSON or structured markdown) plus a typed destination
  path under the governed persistence target
- Prerequisite: explicit policy-arbiter clearance for this result and destination
- Execution: `python3 scripts/kb/persist_query.py <args>` from the repository root
- Output: durable artifact written to the governed destination under ADR-005 locking
- Handoff: after persistence, topology and index follow-up returns to
  `knowledgebase-orchestrator` for review before any downstream synthesis opens

## Assertions

- Policy-arbiter clearance is required before any write path is opened
- Write target must be inside the governed write allowlist (`wiki/**` only)
- Any partial result, missing clearance, missing lock, or out-of-scope path fails closed
- No `logic/` dir is introduced by this skill; adding one requires an AGENTS.md row first
- No score writeback, KPI computation, or durable report artifact may be produced
  from this surface without a separate schema declaration in `schema/**`

## Commands

Run from the repository root:

```bash
python3 scripts/kb/persist_query.py --query-path <path-to-query-result> --destination <wiki/path>
```

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/decisions/ADR-005-write-lock-and-concurrency.md`
- `docs/decisions/ADR-007-control-plane-layering-and-packaging.md`
- `raw/processed/SPEC.md`
- `scripts/kb/persist_query.py`
