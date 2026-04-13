# ADR-004: Split CI governance into gatekeeper, analyst, and PR-producing workflows

## Status
Accepted

## Date
2026-04-12

## Context

Knowledgebase automation needs strong trust boundaries and least-privilege
permissions while still supporting end-to-end ingest and update flows.

A single monolithic workflow would combine trigger validation, diagnostics, and
write operations under one permission context, increasing risk.

## Decision

Adopt the three-workflow governance model:

- **CI-1:** trusted-trigger gatekeeper/handoff (`tp-gatekeeper`).
- **CI-2:** read-only diagnostics/analysis (`tp-analyst-readonly`).
- **CI-3:** PR-producing write-capable path (`tp-pr-producer`).

Enforce fail-closed preflight checks for trust context, permissions scope,
allowlisted write paths, and prerequisite readiness before write-capable steps.

## Alternatives considered

### Monolithic all-in-one workflow

- **Pros:** fewer workflow files and handoffs.
- **Cons:** weaker privilege isolation, harder auditing, larger blast radius on failure.
- **Rejected:** conflicts with least-privilege and explicit boundary requirements.

### Direct-main write automation

- **Pros:** lower latency from ingest to main.
- **Cons:** bypasses PR-centered review gates and increases governance risk.
- **Rejected:** incompatible with controlled merge and review model.

## Consequences

- Permission scope is explicit and bounded per workflow role.
- Trust gating and diagnostics are independently observable.
- Write-capable operations remain constrained to PR-producing automation.

## References

- `raw/inbox/SPEC.md` (gh-aw Automation Model; Token permission profiles; Runtime prerequisite checks; CI quality gate requirements; Security and Trust Model)
