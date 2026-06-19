# ADR-032: Fleet quota-saturation soft-warn exit code for bare FAILED_PRECONDITION

## Status
Accepted

## Date
2026-06-19

## Context

`scripts/fleet/github/mutation-diagnostics.ts` classifies errors from
`POST /v1alpha/sessions` (the Jules SDK `jules.run()` entry point) into
`MutationErrorClass` values and routes them through a retry-then-hard-fail
loop in `runMutationWithDiagnostics`. Before this ADR, every response body
containing `FAILED_PRECONDITION` was classified as `failed_precondition` —
a retryable class that, after exhausting bounded attempts, produces a
`MutationFailureError` caught by `handleFleetFatalError` and terminates the
CI job with exit code 1.

### The production fault

When the per-account Jules session quota is saturated, `POST /v1alpha/sessions`
returns a bare `FAILED_PRECONDITION` with no additional account-binding
diagnostic text in the body. This body is indistinguishable from a genuine
account mis-configuration error unless the body is inspected for specific
account-binding signals (`GOOGLE ACCOUNT`, `GITHUB APP`).

Without the distinction:

- The bare body falls through to the generic `failed_precondition` path.
- Bounded retries exhaust (all fail with the same quota-saturation response).
- `handleFleetFatalError` calls `process.exit(1)`.
- The fleet CI job fails red for the entire run, blocking all ready-for-agent
  dispatch for the duration of quota saturation.
- Quota saturation is transient and self-healing — it requires no code or
  configuration change. Exiting 1 produces noise, blocks CI, and hides the
  diagnostic signal behind a generic hard-fail.

This repo's fleet dispatch was blocked for 11+ consecutive runs due to this
defect (tracked in issue #82, cross-referenced with `wryenmeek/hot-springs-island#595`).

## Decision

Introduce a `quota_saturation` sub-class of `MutationErrorClass` and a
sub-classifier in `classifyFromSignals` with the following signal-precedence
ordering (per wryenmeek/hot-springs-island#595 final implementation):

1. **Explicit quota signals** (`QUOTA`, `SESSION LIMIT/CAP`, `SATURATED` in the
   upper-cased body) → classify as `quota_saturation` (non-retryable, soft-warn).
   This wins before any account-binding check, so a message like
   "quota exceeded for this Google Account / GitHub App" is correctly treated as
   a quota event rather than a configuration fault.

2. **Mismatch-specific account-binding signals** (`NOT REGISTERED`, `UNREGISTERED`,
   `ACCOUNT ... NOT AUTHORIZED`, `ACCOUNT MISMATCH`) → classify as
   `failed_precondition` (retryable, hard-fail after retries).
   This preserves the existing behavior for genuine account mis-configuration.
   Broad noun matches (`GOOGLE ACCOUNT`, `GITHUB APP` alone) are intentionally
   excluded — they appear in quota messages and do not indicate a config fault.

3. **Default (bare body, no recognisable signal)** → classify as `quota_saturation`
   (non-retryable, soft-warn). This covers the production Jules API response shape
   `{"code":400,"message":"Precondition check failed.","status":"FAILED_PRECONDITION"}`
   which carries no additional diagnostic text during quota saturation.

The classifier constants are `QUOTA_SIGNAL_RE` and `ACCOUNT_MISMATCH_RE` in
`mutation-diagnostics.ts`. Extending either signal set is a one-line change.

### `quota_saturation` routing

In `handleFleetFatalError` (`_fleet_output.ts`), `MutationFailureError` with
a terminal `quota_saturation` classification is routed to:

```
::warning::Jules session quota saturated; Fleet run skipped this cycle. Re-run after quota resets.
<sanitized envelope JSON>
process.exit(0)
```

All other `MutationFailureError` classifications retain the existing
`process.exit(1)` hard-fail path.

## Consequences

### Positive

- Transient quota-saturation events surface as GitHub Actions annotations
  (`::warning::`) rather than red CI failures.
- Ready-for-agent dispatch falls back to `copilot-swe-agent` cleanly without
  blocking the entire fleet cycle.
- The genuine account-binding hard-fail path is preserved; operators still
  receive an actionable exit-1 when registration or GitHub App configuration
  is broken.
- The diagnostic envelope is still emitted in full, so quota events are
  observable in CI logs.

### Negative / Trade-offs

- A new `quota_saturation` test class must be carried across all consumers
  of `MutationErrorClass`. The `MUTATION_CATEGORY_DETAILS` record enforces
  exhaustiveness at compile time.
- Soft-warn means the fleet run silently skips dispatch during saturation.
  Operators must monitor `::warning::` annotations to know a cycle was skipped.

## Reversibility

One-line revert: in `classifyFromSignals`, change the `FAILED_PRECONDITION`
branch to always return `"failed_precondition"` instead of the three-step
quota/account-mismatch/default check. The `QUOTA_SIGNAL_RE`, `ACCOUNT_MISMATCH_RE`
constants, the `quota_saturation` category entry, and its routing in
`handleFleetFatalError` can then be removed independently.

## References

- Issue #82 — Jules `FAILED_PRECONDITION` blocking Fleet for 11+ consecutive runs.
- `wryenmeek/hot-springs-island#595` — canonical cross-repo fix (same fault signature).
- `scripts/fleet/github/mutation-diagnostics.ts` — classifier implementation.
- `scripts/fleet/_fleet_output.ts` — `handleFleetFatalError` routing.
