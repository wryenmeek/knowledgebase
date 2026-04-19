---
name: detect-ai-tells
description: Identifies hallucination markers, confident-but-unsupported claims, and AI-generation artifacts in wiki drafts and synthesis outputs. Use when evidence-verifier needs to flag content that reads as plausibly correct but lacks verifiable cited support.
---

# Detect AI Tells

## Overview

This skill documents the AI-artifact detection step for the `evidence-verifier`
persona. "AI tells" are content patterns that are characteristic of language-model
generation rather than evidence-grounded human authorship: confident present-tense
assertions without citations, fabricated-sounding specificity, uniform sentence
rhythm, and claims that are plausible-sounding but unverifiable.

Detection is read-only. Flagged content routes to `policy-arbiter` for a
governed pass/reject/escalate decision rather than being silently removed.

**Doc-only workflow — read-only only.** No `logic/` dir is introduced in MVP.
Any automated scanning tool that writes annotations requires its own explicit
write authorization.

## Classification

- **Mode:** Doc-only workflow — read-only only
- **MVP status:** Active
- **Execution boundary:** Read-only artifact detection. Annotation persistence
  requires separate write authorization.

## When to Use

- `evidence-verifier` is reviewing a draft synthesis page for provenance completeness
- A paragraph makes specific, confident claims but cites no source
- A draft contains numerical specificity (percentages, dates, named programs) that
  does not appear in any cited `raw/processed/**` artifact
- A synthesis output was produced by an agent and has not yet passed a human review
- `claim-inventory` flagged a set of unsupported claims and a secondary check is
  needed to assess whether they resemble generation artifacts vs. authorial oversight

## Contract

- **Input:** a synthesis draft, page body, or claim set from `evidence-verifier`
  or `claim-inventory`
- **Output:** a structured tell-detection report listing:
  - specific sentences or passages flagged
  - the tell pattern observed (e.g., "confident assertion without SourceRef",
    "numeric specificity not in cited source", "uniform cadence across N sentences")
  - severity: `low` (style only), `medium` (missing citation), `high` (potentially
    fabricated fact)
  - recommended disposition: add citation, rewrite with hedge, or escalate
- **Handoff:** the tell-detection report is appended to the evidence review bundle
  for `policy-arbiter`; it does not modify the draft directly

## Assertions

- This skill is read-only; it does not modify wiki pages or synthesis drafts
- Detection findings are structured evidence, not editorial changes
- High-severity findings always escalate to `policy-arbiter` rather than being
  silently dropped
- This skill operates on already-staged synthesis drafts; it is not an ingestion
  gate and does not prevent source registration
- Absence of detected tells is NOT proof of correctness — citation verification
  via `verify-citations` remains mandatory

## References

- `AGENTS.md`
- `raw/processed/SPEC.md`
- `.github/skills/claim-inventory/SKILL.md`
- `.github/skills/semi-formal-reasoning/SKILL.md`
- `.github/skills/verify-citations/SKILL.md`
- `.github/skills/enforce-npov/SKILL.md`
- `.github/agents/evidence-verifier.md`
- `.github/agents/policy-arbiter.md`
