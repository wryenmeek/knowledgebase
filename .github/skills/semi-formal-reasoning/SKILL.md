---
name: semi-formal-reasoning
description: Applies structured informal-to-formal argument analysis to wiki claims and synthesis drafts. Use when evidence-verifier needs to assess whether stated conclusions follow from cited premises, or when a draft conflates correlation with causation, uses modal hedging incorrectly, or makes unsupported inferential leaps.
---

# Semi-Formal Reasoning

## Overview

This skill documents the argument-structure analysis step for the `evidence-verifier`
persona. "Semi-formal" reasoning means applying logical structure checks without
requiring full first-order logic proofs — the goal is to flag unsupported inferential
moves, scope overreach, and modal errors that a careful reader would catch.

**Doc-only workflow — read-only only.** No `logic/` dir is introduced in MVP.
Any automated flagging tool that writes annotations requires its own explicit
write authorization.

## Classification

- **Mode:** Doc-only workflow — read-only only
- **MVP status:** Active
- **Execution boundary:** Read-only argument analysis. Annotation persistence
  requires separate write authorization.

## When to Use

- `evidence-verifier` is reviewing a synthesis draft for logical soundness
- A claim states causation when the cited evidence only shows correlation
- Premises are temporally or geographically scoped but the conclusion is not
- A draft uses hedging language ("may", "might") in a way that obscures whether
  the claim is supported or speculative
- An escalation artifact needs to document the specific inferential flaw rather
  than just flagging a general "quality concern"

## Contract

- **Input:** a synthesis draft, claim set, or escalation bundle from
  `evidence-verifier` or `policy-arbiter`
- **Output:** a structured reasoning-gap report listing:
  - the specific claim or sentence being analyzed
  - the premises cited in support
  - the inferential move being made (e.g., correlation-to-causation, scope
    extension, modal drift)
  - a recommended repair action (reword, add qualifier, escalate to human)
- **Handoff:** the reasoning-gap report becomes part of the evidence review bundle
  routed to `policy-arbiter`; it does not directly modify the draft

## Assertions

- This skill is read-only; it does not modify wiki pages or synthesis drafts
- Reasoning gaps are flagged as structured findings, not as editorial changes
- When a gap cannot be resolved by adding a qualifier or citation, the finding
  escalates to `policy-arbiter` rather than silently approving the draft
- Missing or unavailable premises are surfaced as evidence gaps, not as
  proof by absence

## References

- `AGENTS.md`
- `raw/processed/SPEC.md`
- `.github/skills/claim-inventory/SKILL.md`
- `.github/skills/verify-citations/SKILL.md`
- `.github/skills/enforce-npov/SKILL.md`
- `.github/agents/evidence-verifier.md`
- `.github/agents/policy-arbiter.md`
