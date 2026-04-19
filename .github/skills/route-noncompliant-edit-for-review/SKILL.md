---
name: route-noncompliant-edit-for-review
description: Routes a change-patrol incident record to the correct governed review lane based on the risk classification. Use when patrol-human-edits has produced a high-risk finding that requires escalation before any downstream write-capable lane can open.
---

# Route Noncompliant Edit for Review

## Overview

This skill documents the incident-routing step for the `change-patrol` persona.
After `patrol-human-edits` produces a risk classification, this skill determines
the correct governance lane for the incident — human steward review, policy-arbiter
escalation, or a `log-patrol-incident` record — and routes accordingly. It does not
remediate or revert the edit directly.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Routing and lane-selection only. No direct edit, revert,
  or remediation.

## When to Use

- `patrol-human-edits` has produced a high-risk or medium-risk classification
- An incident record needs to be created and escalated to the correct governance lane
- A destructive or policy-violating edit needs to reach human steward review
- `change-patrol` must select between `log-patrol-incident`, `policy-arbiter`
  escalation, and standard maintenance-lane routing

## Contract

- Input: a `patrol-human-edits` risk classification output and the original edit diff
- Output: a routing decision specifying the next governance lane and required incident
  record type
- Handoff: high-risk incidents route to `log-patrol-incident` and then to human
  steward; medium-risk incidents route to `policy-arbiter`; low-risk continue to
  the standard maintenance lane

## Assertions

- No edit is reverted, deleted, or modified directly by this skill
- A high-risk incident without a `log-patrol-incident` record does not allow
  downstream write-capable lanes to proceed
- The routing decision is explicit and does not silently downgrade a high-risk
  finding to a lower tier
- Missing risk classification input fails closed

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `.github/skills/log-patrol-incident/SKILL.md`
- `.github/skills/log-policy-conflict/SKILL.md`
- `.github/agents/change-patrol.md`
- `.github/agents/policy-arbiter.md`
