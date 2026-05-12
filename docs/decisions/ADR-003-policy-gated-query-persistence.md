# ADR-003: Enforce policy-gated query persistence with machine-readable envelopes

## Status
Accepted

## Date
2026-04-12

## Context

Persisting every query result would create noise and weak signal quality in
`wiki/analyses/**`. Automation also needs deterministic outcomes for both write
and no-write scenarios.

The spec introduces `auto_persist_when_high_value` and requires result envelopes
for write-capable paths.

## Decision

Use `auto_persist_when_high_value` as the default persistence gate.

Persist query outputs only when all conditions hold:

1. `confidence >= 4`,
2. at least two source references,
3. no unresolved contradiction flag.

Require machine-readable JSON envelopes on automation paths with stable fields:
`status`, `reason_code`, `policy`, `analysis_path`, `index_updated`,
`log_appended`, and `sources`.

## Alternatives considered

### Always persist query outputs

- **Pros:** captures every run.
- **Cons:** high noise, low average quality, increased review burden.
- **Rejected:** does not meet high-value-only persistence goal.

### Manual-only persistence

- **Pros:** human quality control before writes.
- **Cons:** lower throughput and inconsistent behavior across runs.
- **Rejected:** MVP requires deterministic automation behavior with explicit policy gates.

## Consequences

- Automation can distinguish policy no-write from hard failures without ambiguity.
- `wiki/analyses/**` remains higher signal with bounded growth.
- Downstream workflows can key behavior on stable envelope values.

## References

- `raw/processed/SPEC.md` (Assumptions and Defaults; Machine-readable result envelopes; Interface contract matrix; Final Ambiguity Checklist)
