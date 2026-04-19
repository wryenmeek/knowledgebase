---
name: score-page-quality
description: Produces a read-only quality score for a wiki page based on evidence coverage, freshness, and structural compliance. Use when quality-analyst needs deterministic quality signals before recommending any curation action.
---

# Score Page Quality

## Overview

This skill documents the page-quality scoring step for the `quality-analyst` persona.
Quality scoring is read-only and recommendation-mode only in MVP: scores inform
`prioritize-curation-backlog` and `knowledgebase-orchestrator` but do not automatically
trigger write operations. Score writeback is approval-gated (Phase 3 per the framework
gap plan).

**Doc-only workflow — read/recommend mode only.** No `logic/` dir is introduced.
Score writeback requires explicit maintainer approval and an AGENTS.md row before
any durable score artifact can be produced.

## Classification

- **Mode:** Doc-only workflow — read/recommend mode only
- **MVP status:** Active
- **Execution boundary:** Read-only quality assessment. Score writeback is
  approval-gated and may not proceed without a separate schema declaration.

## When to Use

- `quality-analyst` needs a deterministic per-page quality signal for triage
- A wiki page needs evidence-coverage, freshness, and structural checks aggregated
  into a single score
- `prioritize-curation-backlog` requires per-page quality scores to rank work
- An operator wants a read-only quality snapshot before deciding on curation actions

## Contract

- Input: a wiki page path and any available freshness/evidence/structural findings
  from prior maintenance-arm steps
- Output: a structured quality score per page (0–100 or tiered label) with
  dimension breakdowns (evidence, freshness, structure)
- Handoff: scores route to `prioritize-curation-backlog`; any score writeback
  requires explicit approval before it can persist

## Assertions

- Quality scores are recommendations only; no write path is opened by this skill
- Score writeback to any durable artifact is blocked until explicit approval and
  schema declaration exist in `schema/**`
- Missing evidence, freshness data, or structural violations reduce the score
  deterministically rather than being skipped
- No `logic/` dir is introduced; adding one for score computation requires an
  AGENTS.md row first

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `schema/page-template.md`
- `.github/skills/report-content-quality/SKILL.md`
- `.github/agents/quality-analyst.md`
- `docs/ideas/spec.md`
