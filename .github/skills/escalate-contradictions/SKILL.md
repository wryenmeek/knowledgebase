---
name: escalate-contradictions
description: Produces a governed escalation record when factual contradictions between wiki content and source evidence cannot be resolved automatically. Use when policy-arbiter, evidence-verifier, or maintenance-auditor identifies an unresolvable conflict that requires human steward review.
---

# Escalate Contradictions

## Overview

This skill documents the contradiction-escalation step for the `policy-arbiter`
persona. When two sources conflict, when new evidence contradicts existing wiki
content, or when a merge decision cannot be made without additional context, this
skill produces a structured escalation record and routes the conflict to human
steward review. No contradiction is silently suppressed.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Escalation record production only. No content modification,
  deletion, or resolution is attempted without human review.

## When to Use

- Two SourceRefs make conflicting factual claims about the same subject
- New evidence contradicts established wiki content and a resolution policy is needed
- `compare-against-existing-pages` has flagged an irresolvable conflict
- `policy-arbiter` must produce a governed record before blocking a synthesis step
- `maintenance-auditor` has identified a contradiction that exceeds its remediation authority

## Contract

- Input: the conflicting claims, their SourceRef citations, the affected wiki page(s),
  and the nature of the conflict
- Output: a structured escalation record (`log-policy-conflict` format) with both
  sides of the contradiction, evidence citations, and the reason automated resolution
  is not safe
- Handoff: the escalation record routes to human steward; no downstream lane opens
  until the contradiction is resolved

## Assertions

- Contradictions are never silently resolved in favor of one source without human review
- The escalation record must cite both conflicting sources with SourceRef format
- Incomplete or ambiguous conflict descriptions fail closed
- Automated resolution of contradictions requires explicit ADR approval

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `.github/skills/log-policy-conflict/SKILL.md`
- `.github/skills/record-open-questions/SKILL.md`
- `.github/agents/policy-arbiter.md`
