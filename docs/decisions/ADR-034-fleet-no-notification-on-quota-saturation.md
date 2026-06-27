# ADR-034: Fleet no-notification policy on quota saturation

## Status

Accepted — extends ADR-032

## Date

2026-06-22

## Context

Fleet quota saturation is already handled by ADR-032 as a soft-warn exit path.
Adding per-event notification would create alert noise during transient quota
windows and duplicate information already visible in workflow logs and issue
audit trails.

HSI ADR-029 established the same policy direction: no additional notification
channel for quota-saturation events beyond existing operational surfaces.

## Decision

Adopt a no-notification policy for quota saturation in this repository:

1. Keep ADR-032 soft-warn exit behavior for quota saturation.
2. Do not emit extra issue comments, emails, or paging notifications for each
   quota-saturation event.
3. Use existing visibility channels instead:
   - `::warning::` annotations in workflow logs
   - canary tracking issue operations from issue #349
   - per-issue dispatch comments with session links from Tier 2 dispatch flow

## Alternatives considered

- Per-event issue comment notifications. Rejected: high noise and repeated
  comments during transient saturation.
- Dedicated alerting workflow. Rejected: additional maintenance surface with
  low signal gain over existing canary + logs.
- Hard-fail exit status on quota saturation. Rejected: conflicts with ADR-032
  and blocks unrelated ready-for-agent progress.

## Consequences

### Positive

- Reduces alert fatigue during short-lived quota saturation periods.
- Keeps operational visibility through existing channels without new workflows.
- Preserves ADR-032's non-blocking behavior for transient saturation.

### Negative / Trade-offs

- Operators must monitor existing canary/log surfaces rather than receiving
  explicit per-event notifications.
- Debugging depends on good session/issue traceability in dispatch comments.

## Reversibility

Reversible by amending this ADR and ADR-032 if saturation behavior changes or
if the canary/log visibility channels prove insufficient in production.

## Related decisions

- [`ADR-032`](ADR-032-fleet-quota-saturation-soft-warn.md) — defines soft-warn
  classification and exit behavior.
- [`ADR-033`](ADR-033-fleet-label-driven-dispatch-adoption.md) — per-issue
  dispatch comments used as audit trail visibility.
- [`ADR-019`](ADR-019-fleet-jules-orchestration.md) — fleet workflow baseline.

## References

- `repo://wryenmeek/hot-springs-island/docs/decisions/ADR-029-fleet-dispatch-quota-saturation-exit-code.md@affffd1b53a0b84d84fd17fcbaa246b1dcce46c2#asset?sha256=73021ac67c12410fdff59e09119d4227a06f2fd5ca8628ff95ff30cea5b554ad`
- Issue #349
- Issue #350
- `scripts/fleet/_fleet_output.ts`
