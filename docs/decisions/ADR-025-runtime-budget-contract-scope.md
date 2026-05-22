# ADR-025: Runtime-budget contract scope and CI parity

## Status
Accepted — amended in-place: expanded runtime-budget contract scope to CI-5/CI-6 parity (see § Amendment)

## Date
2026-05-21

## Context

`schema/runtime-budgets.json` is consumed by `scripts/validation/_runtime_budget.py`
in CI workflows that emit runtime-metrics artifacts and evaluate stage thresholds.

The initial ADR-025 decision constrained schema scope to CI-2/CI-3 only to avoid
placeholder drift. CI-5 and CI-6 now execute runtime-budget evaluation stages
with machine-readable reports, warn gates, fail gates, and step-summary output.
Leaving CI-5/CI-6 outside the schema contract would recreate drift between
runtime wiring and declared budget governance.

The issue-19 alignment lock also freezes the budget-entry contract and severity
policy for this lane.

## Decision

`schema/runtime-budgets.json` remains the canonical in-repo runtime budget
registry and now covers **all currently wired runtime-budget workflow IDs**:

- `ci-2-analyst-diagnostics`
- `ci-3-pr-producer`
- `ci-5-check-drift`
- `ci-5-fetch-and-update`
- `ci-5-classify-drift`
- `ci-5-synthesize`
- `ci-6-check-drift`
- `ci-6-fetch-and-update`
- `ci-6-classify-drift`
- `ci-6-synthesize`
- `ci-6-advance-cursor`

Each stage entry in the registry must define exactly:

- `target_seconds`
- `warn_pct`
- `fail_pct`

Deterministic classification policy:

- `ok` when `duration_seconds <= target_seconds`
- `warn` when `target_seconds < duration_seconds < fail_seconds`
- `fail` when `duration_seconds >= fail_seconds`

where `fail_seconds = ceil(target_seconds * (100 + fail_pct) / 100)`.

Runtime telemetry persistence remains CI artifact + `$GITHUB_STEP_SUMMARY` only.
No external telemetry dependency is introduced.

## Alternatives considered

### Keep CI-5/CI-6 out of schema scope (rejected)

- **Pros:** smaller schema surface.
- **Cons:** invalid once CI-5/CI-6 runtime-budget gates are wired; creates
  contract drift and weakens parity testing.

### Split runtime budgets across multiple schema files (rejected)

- **Pros:** per-workflow-family files are smaller.
- **Cons:** violates single-source requirement and complicates deterministic
  parity checks.

## Consequences

- Runtime-budget governance is now contract-aligned across CI-2/CI-3/CI-5/CI-6.
- Contract tests must keep schema workflow IDs and stage IDs in lockstep with
  all runtime-budget workflow literals and emitted stage-duration blocks.
- Adding/removing any budgeted workflow stage now requires same-PR updates to:
  schema, tests, and runtime-budget runbook documentation.

## Amendment

- **Date:** 2026-05-22
- **What changed:** Expanded scope from CI-2/CI-3-only to include wired CI-5 and
  CI-6 runtime-budget evaluators; replaced per-stage `warn_seconds`/`fail_seconds`
  entries with `target_seconds`/`warn_pct`/`fail_pct` entries; updated parity
  tests and runbook outputs accordingly.
- **Why:** CI-5/CI-6 already emitted and evaluated runtime budgets, so excluding
  them from the canonical registry created immediate contract drift.
- **What did not change:** `schema/runtime-budgets.json` remains canonical;
  severe breaches remain fail-closed; telemetry remains artifact + step summary
  only.

## References

- [ADR-004](ADR-004-split-ci-workflow-governance.md)
- [ADR-015](ADR-015-extended-ci-trust-model.md)
- [docs/mvp-runbook.md](../mvp-runbook.md)
- [schema/runtime-budgets.json](../../schema/runtime-budgets.json)
