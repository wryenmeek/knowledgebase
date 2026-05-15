# ADR-023: Batch query persistence — single-lock, partial-failure, and size-limit design

## Status
Accepted — extends ADR-003

## Date
2026-05-15

## Context

`scripts/kb/persist_query.py` (ADR-003) persists one high-value query result per
invocation. Phase 3 introduced `scripts/kb/batch_persist_query.py` to handle N
queries in a single governed operation. Four design decisions were not obvious
from ADR-003 alone and needed explicit recording.

**Decision 1 — lock acquisition strategy.** The wiki write lock
(`wiki/.kb_write.lock`, ADR-005) can be acquired once for the whole batch or
once per entry. Per-entry lock-cycling keeps each critical section short but
multiplies lock-contention risk and inter-entry delay at scale; it also means a
mid-batch lock failure leaves the wiki in a partially-written state with no
clean abort point. Single-lock-for-batch bounds the worst-case wait to one
acquisition and makes the batch's atomicity boundary explicit: either the batch
starts writing or it does not.

**Decision 2 — hard batch size cap.** Without a size limit an operator error
(wrong file path, recursive glob) could cause a single run to hold the write
lock and consume memory for an unbounded number of entries.

**Decision 3 — per-entry OSError handling.** `persist_query.py` aborts the
entire run on any unexpected write error. For a batch that is acceptable for
a single-entry run but defeats the purpose of batch processing — one transient
I/O error would discard all remaining entries. Rollback-and-continue preserves
the entries already written while giving the operator a clear per-entry failure
report for re-submission.

**Decision 4 — sensitivity allowlist in `_validate_request`.** The `sensitivity`
field was previously constrained only through argparse `choices=`. That is
insufficient for the batch path where entries arrive as free-form JSON objects,
not CLI arguments. An explicit `_VALID_SENSITIVITY_VALUES` check inside
`_validate_request` closes the validation gap for all callers, including the
batch path.

## Decision

### Lock strategy: single acquisition for the whole batch

Acquire `wiki/.kb_write.lock` exactly once before writing any entry. If the
lock is unavailable, all pre-validated entries are marked `failed` and the
top-level result status is `fail`. No entry is written until the lock is held.
This gives a clean, well-defined abort boundary that is observable in the
structured JSON envelope.

### MAX_BATCH_SIZE = 100

Reject any batch file whose top-level array length exceeds 100 entries before
acquiring the lock or performing any write. The limit is a hard-coded module
constant (`MAX_BATCH_SIZE`) so it can be verified in tests and cited in error
messages.

### Per-entry OSError: rollback + continue

When a write error occurs for a single entry:
1. Roll back that entry's file using `rollback_file_state` from `write_utils`.
2. Mark the entry `failed` in the per-entry result.
3. Continue processing remaining entries.

Index regeneration and log append run after all entries are processed; an
index update failure at that stage is logged as a warning rather than causing
a rollback of already-written entries (intentional divergence from
`persist_query.py` — a batch that wrote successfully is not retroactively
invalidated by an index regeneration hiccup).

### Sensitivity allowlist in `_validate_request`

`_VALID_SENSITIVITY_VALUES` is declared as a module-level constant in
`persist_query.py` and checked inside `_validate_request`. The argparse
`choices=` guard on the single-entry CLI path is kept for user-facing error
messaging but is no longer the sole enforcement point.

## Alternatives considered

### Per-entry lock acquire/release

- **Pros:** shorter individual critical sections; other writers can interleave
  between entries.
- **Cons:** lock-contention probability grows linearly with batch size;
  mid-batch lock failure leaves partial writes without a clean abort point;
  total wall time increases due to repeated OS lock operations.
- **Rejected:** single-lock-for-batch provides cleaner failure semantics and
  equivalent concurrency guarantees for the operator workflows that use batch
  persistence (no concurrent batches are expected; each CI run serializes via
  ADR-005 workflow group concurrency).

### Abort-entire-batch on first OSError (matching persist_query.py)

- **Pros:** consistent failure model across single and batch paths.
- **Cons:** a single transient I/O error (e.g., a filesystem hiccup for one
  entry) forces the operator to resubmit every entry in the batch; already-
  written entries are rolled back even though they succeeded.
- **Rejected:** rollback-and-continue produces a more useful result for the
  operator and preserves the entries that were successfully written.

### No MAX_BATCH_SIZE limit

- **Pros:** no artificial ceiling on batch operations.
- **Cons:** a runaway batch (malformed file reference, operator error) could
  hold the write lock for an unbounded time and exhaust memory; no budget for
  reasoning about worst-case lock-hold duration in CI.
- **Rejected:** 100 entries is ample for expected Phase 3/4 usage patterns and
  keeps lock-hold time predictable.

### Sensitivity validation in argparse only

- **Pros:** fewer code paths to maintain.
- **Cons:** batch entries arrive as JSON objects, bypassing argparse validation
  entirely; an invalid `sensitivity` value would reach a write call.
- **Rejected:** defence-in-depth requires the validation to live in the
  shared `_validate_request` helper, which is called by both the single and
  batch paths.

## Consequences

- `batch_persist_query.py` acquires `wiki/.kb_write.lock` exactly once per
  batch run. Operators must not submit batches that exceed `MAX_BATCH_SIZE`;
  oversized submissions fail before any I/O occurs.
- Per-entry failures produce a rollback for that entry and a `failed` entry in
  the result envelope but do not abort remaining entries — operators should
  inspect the `entries[]` array for per-entry `status` and resubmit failed
  entries individually or in a reduced batch.
- `_validate_request` is now the canonical enforcement point for
  `sensitivity` validation across both the single-entry and batch surfaces.
- ADR-003 policy gate (confidence, source count, contradiction flag) and
  ADR-005 lock model remain in force; this ADR records only the design
  decisions specific to the batch surface.

## References

- [`ADR-003`](ADR-003-policy-gated-query-persistence.md) — policy gate that
  batch persistence inherits for each entry.
- [`ADR-005`](ADR-005-write-concurrency-guards.md) — write concurrency model;
  `wiki/.kb_write.lock` is the same lock used by the batch surface.
- `scripts/kb/batch_persist_query.py` — implementation of the decisions above.
- `scripts/kb/persist_query.py` — single-entry surface; `_validate_request` and
  `_VALID_SENSITIVITY_VALUES` shared with the batch path.
- `tests/kb/test_batch_persist_query.py` — verification suite for this surface.
