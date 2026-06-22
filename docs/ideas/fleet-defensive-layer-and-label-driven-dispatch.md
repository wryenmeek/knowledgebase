# Fleet defensive layer + label-driven dispatch (Tier 0/1/2 plan)

**Status:** Proposed

> Cross-portfolio research informed this plan; see [`docs/research/jules-fleet-cross-portfolio-patterns.md`](../research/jules-fleet-cross-portfolio-patterns.md) for the evidence base, threat model, and pattern catalog.

## Problem

Three operational concerns surfaced together on 2026-06-21:

1. **Issue #82** — Jules dispatch was silently failing for 24 days (2026-05-26 → 2026-06-19) before discovery, with no operational signal that fleet was non-functional.
2. **Issue #341** — The fleet has no fallback, no proactive notification, and no canary; a Jules outage on day 1 looks identical to "no eligible issues today."
3. **Issue #342** — Scribe's audit of 81 Jules-bot commits found 2 silent-revert PRs (2.5% rate) under benign Conventional Commits titles. Same threat model applies here even though we have not yet observed an incident.

Without coordinated action, the next dozen Jules-authored PRs in this repo have a ~25% cumulative probability of producing a Scribe-class silent revert.

## Proposed approach — 4 tiers, 7 ready-for-agent issues

| Tier | Goal | Issues | Status |
|---|---|---|---|
| **Tier 0 — Defensive layer** | Zero content destruction (ratified-Q1 metric) | [#345](https://github.com/wryenmeek/knowledgebase/issues/345) advisory CODEOWNERS, [#346](https://github.com/wryenmeek/knowledgebase/issues/346) stale-bot-branch sweeper, [#347](https://github.com/wryenmeek/knowledgebase/issues/347) commit-scope check (gates B+C), [#351](https://github.com/wryenmeek/knowledgebase/issues/351) flip sweeper to real-delete after 14d | ready-for-agent (#351 needs-triage until activation) |
| **Tier 1 — Operational resilience** | ≤9h detection latency on Jules outages; un-stick `awaitingUserFeedback` sessions ≤24h | [#348](https://github.com/wryenmeek/knowledgebase/issues/348) port `fleet-submit-prs.ts` from HSI, [#349](https://github.com/wryenmeek/knowledgebase/issues/349) schedule `jules-account-probe.yml` 3×/day + tracking-issue notification | ready-for-agent |
| **Tier 2 — Label-driven dispatch** | Replace planner ad-hoc triage with HSI ADR-030 model + 3-strikes abort | [#350](https://github.com/wryenmeek/knowledgebase/issues/350) adopt HSI ADR-030 verbatim + ADR-033 + ADR-034 + ADR-032 cleanup | ready-for-agent |
| **Tier 3 — Multi-provider abstraction** | Evaluate `copilot-swe-agent` / Codex / Devin as Jules fallback | (no issue) — formally deferred 30 days, revisit 2026-07-21 | deferred |

## Why this shape

- **Tier 0 ships first** because content destruction is irreversible; operational annoyance from a quota-saturation blackout is recoverable.
- **Tier 1 ships second** because it directly addresses the failure mode that caused issue #82 to go undiscovered for 24 days.
- **Tier 2 ships third** because the label-driven model only adds value once Tiers 0 + 1 are stable enough that the fleet pipeline runs reliably.
- **Tier 3 is deferred** because no repository in the operator's portfolio has built a multi-provider abstraction (verified via cross-portfolio research), so we have no prior art to lift; building from scratch is high cost / low validated benefit until the other tiers settle.

## What this is NOT

- **Not** a unilateral re-architecting of the fleet — the 7 implementation issues are scoped narrowly so each can land independently.
- **Not** a replacement for ADR-019 (fleet orchestration) — Tier 2 extends it; Tier 1 builds alongside it; Tier 0 is orthogonal.
- **Not** a multi-provider abstraction — Tier 3's decision is "wait 30 days, gather more evidence, revisit."

## Cross-cutting design constraints applied uniformly across all 7 issues

- **Tests use pytest (Python) or `bun:test` (TypeScript); never `unittest.TestCase` for new tests** (enforced by `scripts/hooks/check_test_framework.py` per ADR-029).
- **AGENTS.md write-surface matrix rows + `EXPECTED_WRITE_SURFACE_MATRIX_ROWS` test entries** must land together (bidirectional equality enforced).
- **Workflow schedule docs sync rule:** every cron string must appear verbatim in `docs/mvp-runbook.md` Trigger column.
- **Cross-functional-review merge gate:** every PR for these issues requires the `cross-functional-reviewed` label OR a session evidence artifact before `gh pr merge` will succeed (enforced by `scripts/hooks/check_cross_functional_review.py`).
- **Argv discipline + `--` git terminator** for any branch-name-handling code (issue #346, future #351 deletion path).
- **Step-scoped `JULES_API_KEY` binding** (never job-level) per AGENTS.md "Step-scoped secret binding" rule.

## Implementation discoverability

All 7 issues carry the audit comment posted 2026-06-21 documenting the cross-functional review pass and the 63 findings remediated in the issue bodies. The `remediation_findings` session SQL ledger captured the audit trail (not persisted to repo).

CONTEXT.md commits `3de17be` and `222161a` added two glossary terms (`sensitive paths`, `silent-revert PR`) that are load-bearing across the new ADRs and the commit-scope check.

## Ratification trail

- 2026-06-21 12-question `/grill-with-docs` session ratified all 12 decisions (full decision log distributed across the 7 implementation issue bodies).
- User overrode 2 of my recommendations: (a) Tier 2 adopted verbatim with 3-strikes abort rather than my recommended minimal subset; (b) plan split into 7 granular issues for maximum parallelism rather than my recommended 3-4 bundled issues.

## Open questions

- After #346 ships and runs 14 nights of clean dry-run output, does the operator approve the flip to real-delete (#351)?
- When the 30-day Tier 3 revisit comes due (2026-07-21), what new evidence (Codex GA features, Devin adoption signals, copilot-swe-agent stability data) has changed the calculus?
- Does HSI's ADR-030 graduate from Proposed to Accepted in their repo? If they amend or reject after our adoption, our ADR-033 explicitly requires re-review within 14 days.

## Provenance

Filed 2026-06-21 as the umbrella synthesis for the cross-portfolio plan ratified in this session's `/grill-with-docs`. References [`docs/research/jules-fleet-cross-portfolio-patterns.md`](../research/jules-fleet-cross-portfolio-patterns.md) for the evidence base.
