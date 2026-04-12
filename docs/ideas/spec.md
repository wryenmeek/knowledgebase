# Spec Refinement: Hybrid Contract + Assertion

## Problem Statement
How might we make `SPEC.md` unambiguous enough to start implementation planning immediately, while reducing agent misinterpretation risk through deterministic contracts and checks?

## Recommended Direction
Adopt a **hybrid model** where contract tables are the canonical specification spine, and each high-risk rule is paired with an explicit assertion (pass/fail condition). Contracts define workflow boundaries (inputs, outputs, side effects, idempotency, and failure behavior). Assertions make those boundaries testable and harder to misread by humans or agents.

Given the selected aggressive risk posture, the refinement should prioritize determinism over prose elegance. The spec should remain readable, but ambiguity-heavy language should be replaced with constrained, verifiable statements for security, scope, and automation behavior. This reduces interpretation drift during implementation planning and later automation authoring.

## Key Assumptions to Validate
- [ ] Contract tables are treated as the single source of truth by maintainers and agents — test by running one implementation-planning pass using only contract sections.
- [ ] Assertion coverage is sufficient to prevent major misinterpretation of trust/scope rules — test by adversarial review of ambiguous scenarios and check for deterministic outcomes.
- [ ] Aggressive determinism does not create unacceptable authoring overhead — test by timing one full spec update cycle and collecting friction points.

## MVP Scope
Introduce and enforce:
- Canonical contract tables for all critical workflows (`ingest`, `update_index`, `lint`, `query/persist`, gh-aw handoffs).
- Assertion-linked checks for high-risk rules (trust boundaries, write allowlists, trigger policy, repo-only scope, contradiction handling).
- A conformance-oriented verification matrix mapping policies to test types.
- Explicit ambiguity closure status for each pre-implementation checklist item.

Do not broaden MVP into delivery features; keep this as a spec-hardening pass that enables immediate implementation planning.

## Not Doing (and Why)
- Full machine-readable policy compiler layer (YAML/JSON schema generation) — valuable later, but not required to start implementation planning now.
- Reorganizing the entire spec around a strict scope-firewall narrative — rejected direction; keep scope controls explicit without making them the sole organizing structure.
- Expanding Phase 2 outcomes (GitHub Pages browse/search and feedback loop) into MVP — would dilute focus and increase delivery risk.

## Open Questions
- Should assertion IDs become mandatory references in future implementation PRs?
- What is the minimum assertion set that catches most misinterpretation risk without overfitting?
- Do we want a lightweight “spec lint” step to detect contract/prose drift automatically?
