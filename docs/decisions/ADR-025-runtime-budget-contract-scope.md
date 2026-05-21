# ADR-025: Runtime-budget contract scope and CI parity

## Status
Accepted

## Date
2026-05-21

## Context

`schema/runtime-budgets.json` is consumed by `scripts/validation/_runtime_budget.py`
in CI workflows that emit runtime-metrics artifacts and evaluate stage thresholds.
The schema had expanded to include CI-5/CI-6 workflow IDs even though those
workflows do not execute a runtime-budget evaluation stage today. That created
contract drift: schema entries existed without executable enforcement, while tests
only verified CI-2/CI-3 runtime-budget wiring.

## Decision

Limit the runtime-budget contract to workflows that currently execute the
runtime-budget evaluator end-to-end.

As of this ADR, the authoritative scope is:

- `ci-2-analyst-diagnostics`
- `ci-3-pr-producer`

CI-5/CI-6 remain explicitly out of runtime-budget scope until they implement all
three surfaces in the same change set:

1. Runtime metrics emission (`<artifact>/runtime-metrics.json`)
2. Runtime-budget evaluation + report emission
3. Contract tests that assert stage-ID parity against `schema/runtime-budgets.json`

## Alternatives considered

### Keep CI-5/CI-6 entries as forward-looking placeholders (rejected)

- **Pros:** pre-declares intended future budget coverage.
- **Cons:** introduces false confidence; schema appears enforced where no runtime
  evaluator exists and no workflow-stage parity is tested.

### Implement CI-5/CI-6 runtime-budget stages immediately (deferred)

- **Pros:** full cross-workflow parity now.
- **Cons:** larger workflow changes with additional runtime and artifact handling;
  outside the scope of the current remediation cycle.

## Consequences

- `schema/runtime-budgets.json` is now aligned to executable enforcement (CI-2/CI-3 only).
- Runtime-budget regression tests must continue to validate schema/workflow stage parity.
- Any future addition of CI-5/CI-6 (or other workflows) to the schema must land with
  workflow wiring and tests in the same PR to avoid reintroducing contract drift.

## References

- [ADR-004](ADR-004-split-ci-workflow-governance.md)
- [ADR-015](ADR-015-extended-ci-trust-model.md)
- [docs/mvp-runbook.md](../mvp-runbook.md)
- [schema/runtime-budgets.json](../../schema/runtime-budgets.json)
