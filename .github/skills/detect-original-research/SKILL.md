---
name: detect-original-research
description: Checks whether a wiki page or draft contains unsourced original research, speculative conclusions, or claims that exceed what the cited SourceRefs support. Use when policy-arbiter needs a deterministic NPOV and evidence-boundary assessment before clearing a draft for publication.
---

# Detect Original Research

## Overview

This skill documents the original-research detection step for the `policy-arbiter`
persona. It compares claims in a draft or existing wiki page against their cited
SourceRefs and flags any assertion that introduces unsourced synthesis, speculation,
or original analysis beyond what the evidence directly supports. Findings gate
publication clearance.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Read-only policy assessment. No draft mutation or
  publication action is opened.

## When to Use

- A draft from `synthesis-curator` needs policy review before publication clearance
- `policy-arbiter` suspects that a submitted page exceeds the evidence boundary
- A human editor has added speculative or interpolated content that may violate
  the `enforce-npov` contract
- A `claim-inventory` review has flagged potentially unsupported assertions

## Contract

- Input: a draft or existing wiki page plus its associated SourceRef citations
- Output: a structured list of original-research findings, each with the affected
  claim, the cited SourceRef, and the policy violation type
- Handoff: pages with unresolved original-research findings are blocked from
  publication clearance and route to human steward review

## Assertions

- Claims that exceed SourceRef evidence are always flagged, not silently accepted
- Speculation, forward-looking assertions without evidence, and AI-generated
  interpolation are original research violations
- A page without original-research findings still requires full policy-arbiter
  review before clearance
- This step does not modify draft content

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `.github/skills/enforce-npov/SKILL.md`
- `.github/skills/verify-citations/SKILL.md`
- `.github/agents/policy-arbiter.md`
