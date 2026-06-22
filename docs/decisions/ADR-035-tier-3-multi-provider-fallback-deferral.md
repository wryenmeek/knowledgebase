# ADR-035: Tier 3 multi-provider implementation-agent fallback — 30-day deferral

**Date:** 2026-06-21

## Status

Accepted — extends ADR-019

## Context

Issue #82 (Jules dispatch outage 2026-05-26 → 2026-06-19) and issue #341
(architectural fallback gap) raised the question of whether the fleet should
abstract over multiple implementation-agent providers — for example, falling
back from Jules to `copilot-swe-agent`, Codex, Devin, or other emerging
agents — so a single-provider outage does not block all ready-for-agent work.

The current fleet (ADR-019, ADR-032) is Jules-first. ADR-032's "Positive
consequences" section originally claimed *"Ready-for-agent dispatch falls
back to `copilot-swe-agent` cleanly without blocking the entire fleet
cycle,"* but cross-portfolio code review on 2026-06-21 verified that **no
such fallback is implemented** in this repository (or in any of the operator's
other repositories — `wryenmeek/hot-springs-island`, `wryenmeek/vscode-genai`,
`wryenmeek/Scribe`). That aspirational claim was removed from ADR-032 in the
same session that filed this ADR (see ADR-032 "Amendment" section).

The cross-portfolio research synthesis
([`docs/research/jules-fleet-cross-portfolio-patterns.md`](../research/jules-fleet-cross-portfolio-patterns.md))
found no prior art for a multi-provider abstraction in the operator's portfolio
and no public references that solve the problem in a way the repo could lift
directly. Building such an abstraction from scratch would be expensive (provider
SDK heterogeneity, prompt-format divergence, output-shape divergence, label /
PR-management convention divergence) for a benefit (cross-provider resilience)
that is not yet validated to be worth the cost.

The 2026-06-21 `/grill-with-docs` session ratified the deferral as Question 10
of the 12-question decision log distributed across issues #345–#351.

## Decision

**Defer Tier 3 (multi-provider implementation-agent abstraction) for 30 days.**
Revisit date: **2026-07-21**.

Specific commitments during the deferral window:

1. **No fleet code referencing alternative providers ships.** `scripts/fleet/`
   remains Jules-first. Any provider-specific code lands only after Tier 3 is
   re-evaluated and explicitly accepted.
2. **No new ADR references a multi-provider design as in-flight or planned.**
   ADR-032's aspirational line was removed in the same session (see ADR-032
   "Amendment" / "Consequences > Positive" current text). If future ADRs need
   to discuss the topic, they cite ADR-035's deferral status.
3. **Operational visibility for single-provider outages is improved during the
   deferral.** Specifically: issue #348 (un-stick `awaitingUserFeedback`
   sessions, daily) and issue #349 (scheduled `jules-account-probe.yml` 3
   slots/day with tracking-issue notification) ship as Tier 1 to ensure a
   future Jules outage surfaces in ≤9h instead of the 24-day discovery latency
   of issue #82.
4. **The 2026-07-21 revisit is operator-driven**, not auto-triggered. The
   operator opens a new issue or re-opens #341 with whatever new evidence
   (Codex GA features, Devin adoption signals, `copilot-swe-agent` stability
   data, additional cross-portfolio prior art) has accumulated.

## Alternatives considered

- **A. Build a minimal `copilot-swe-agent` fallback now.** Rejected: ADR-032's
  aspirational line set this expectation but no design existed. Cross-portfolio
  research found zero prior art; building from scratch under the pressure of a
  single recent incident is the wrong sequence. The Tier 1 visibility
  improvements address the immediate operational pain (24-day discovery latency)
  more cheaply than a fallback abstraction would.
- **B. Defer indefinitely (no revisit date).** Rejected: an open-ended deferral
  becomes a permanent neglect signal. A 30-day window forces an explicit
  revisit with whatever evidence has accumulated.
- **C. Defer 90 days.** Rejected: 30 days is enough to gather meaningful new
  evidence (a Tier 0 + Tier 1 + Tier 2 implementation cycle is roughly two
  weeks of fleet runs); 90 days defers past the point where most teams forget
  the original motivation.

## Consequences

### Positive

- The fleet keeps shipping during the deferral; no design paralysis from
  trying to abstract over providers we have not yet validated.
- Operational visibility into Jules-specific outages improves significantly
  (Tier 1 issues #348 + #349) — addressing the actual pain that motivated the
  Tier 3 question without committing to a heavy abstraction.
- ADR-032 no longer contains an aspirational fallback claim that did not
  match implementation.
- Future re-evaluation has 30 days of additional evidence (Codex GA timing,
  Devin maturity, fresh portfolio-wide observations) that the current decision
  could not benefit from.

### Negative / Trade-offs

- A second sustained Jules outage during the deferral window would re-expose
  the lack of fallback. Mitigation: Tier 1 issues #348 + #349 reduce
  discovery latency from 24 days to ≤9h; the operator can manually re-route
  blocked issues to alternative provider workflows on a per-incident basis if
  needed.
- The 2026-07-21 revisit is operator-driven; if the operator forgets, the
  deferral silently extends. Mitigation: this ADR exists and is discoverable
  from `docs/decisions/README.md`; a calendar reminder is recommended but not
  enforced in-repo.
- We commit to NOT advertising a fallback in any user-facing doc during the
  deferral. ADR-032's cleanup is the only correction we need today.

## Reversibility

This ADR is fully reversible at the 2026-07-21 revisit. To reverse before
2026-07-21:

1. Open a new issue with the evidence motivating early revisit.
2. File an amendment to this ADR's Status (e.g., `Accepted — superseded by
   ADR-036`) or in-place amendment if the new design extends rather than
   replaces.
3. If the early revisit produces a concrete multi-provider design, file
   ADR-036 with that design and update this ADR's Status to point at it.

If the 2026-07-21 revisit reaffirms the deferral, the simplest action is to
file a brief Amendment section on this ADR documenting the second deferral
decision plus the next revisit date.

## Related decisions

- [`ADR-019`](ADR-019-fleet-jules-orchestration.md) — Jules-based fleet
  orchestration; this ADR extends ADR-019 by formally deferring the
  multi-provider question that ADR-019 left open.
- [`ADR-032`](ADR-032-fleet-quota-saturation-soft-warn.md) — Originally
  contained the aspirational `copilot-swe-agent` fallback line; the cleanup
  that motivated this ADR removed that line in the same session.

## References

- Issue #341 — Architectural fallback gap (filed 2026-06-21).
- Issue #82 — Jules `FAILED_PRECONDITION` outage 2026-05-26 → 2026-06-19
  (root-caused to ADR-032 fix; closed 2026-06-21).
- [`docs/research/jules-fleet-cross-portfolio-patterns.md`](../research/jules-fleet-cross-portfolio-patterns.md)
  — Cross-portfolio research synthesis documenting the absence of multi-provider
  prior art in `wryenmeek/hot-springs-island`, `wryenmeek/vscode-genai`, and
  `wryenmeek/Scribe`.
- [`docs/ideas/fleet-defensive-layer-and-label-driven-dispatch.md`](../ideas/fleet-defensive-layer-and-label-driven-dispatch.md)
  — Umbrella for the Tier 0/1/2 plan that ships during this deferral window.
- 2026-06-21 `/grill-with-docs` session, Question 10 (decision log distributed
  across issues #345–#351 bodies).
