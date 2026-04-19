---
name: patrol-human-edits
description: Reviews recent human or agent edits to wiki pages for policy, provenance, and citation risk before any lane downstream of change-patrol can open. Use when change-patrol needs a diff-based risk classification for changed wiki content.
---

# Patrol Human Edits

## Overview

This skill documents the edit-patrol step for the `change-patrol` persona. It
inspects a diff (or set of changed pages) for policy risk — citation removals,
destructive edits, NPOV violations, and provenance gaps — and produces a risk
classification. The patrol result gates downstream maintenance and quality lanes;
it does not remediate content directly.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Read-only diff assessment only. No content change or
  remediation is performed.

## When to Use

- A human editor or external agent has committed changes to `wiki/**`
- `change-patrol` must classify the risk before downstream lanes open
- An operator suspects a destructive or policy-violating edit has occurred
- A CI/CD pipeline needs a governed diff review before any write-capable step proceeds

## Contract

- Input: a diff or set of changed page paths, along with the before/after content
- Output: a structured risk classification per change, including the risk level
  (low/medium/high), affected policy areas, and recommended next lane
- Handoff: high-risk findings route to `log-patrol-incident`; low-risk findings
  allow the normal downstream lane to proceed

## Assertions

- No content is modified by this skill
- Citation removals, deleted provenance sections, and NPOV violations are always
  classified as high risk
- The patrol result is the required input for any downstream maintenance or quality
  lane that follows a human edit
- Missing or ambiguous diff input fails closed

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `.github/skills/policy-diff-review/SKILL.md`
- `.github/skills/log-patrol-incident/SKILL.md`
- `.github/agents/change-patrol.md`
