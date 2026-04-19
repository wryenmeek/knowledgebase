---
name: compute-kpis
description: Aggregates repo-level quality KPIs from existing evidence without opening a durable write path. Use when quality-analyst needs a read-only KPI snapshot to inform curation prioritization or operator reporting.
---

# Compute KPIs

## Overview

This skill documents the KPI-computation step for the `quality-analyst` persona.
KPIs are derived from existing evidence — freshness scores, quality scores,
maintenance findings, and index topology — and expressed as simple ratios or counts
(e.g., stale page percentage, evidence coverage rate). KPI computation is read-only
in MVP. Any KPI writeback or durable report artifact requires explicit maintainer
approval and a schema declaration in `schema/**`.

**Doc-only workflow — read-only only.** No `logic/` dir is introduced. KPI writeback
and pipeline automation are approval-gated (Phase 3 per the framework gap plan).

## Classification

- **Mode:** Doc-only workflow — read-only only
- **MVP status:** Active
- **Execution boundary:** Read-only KPI derivation. Durable KPI writeback and
  pipeline automation are approval-gated.

## When to Use

- `quality-analyst` needs an aggregate health snapshot of the wiki
- An operator wants to track quality trend signals across a maintenance cycle
- `prioritize-curation-backlog` requires KPI context to rank follow-up work
- A governance review needs summary statistics about wiki health without a full audit

## Contract

- Input: available evidence from freshness-audit, score-page-quality, and any
  maintenance-arm findings
- Output: a structured KPI snapshot with named metrics and source evidence citations
- Handoff: KPI snapshot informs `prioritize-curation-backlog` and operator reporting;
  no durable write is opened

## Assertions

- KPI computation is read-only; no write path is opened by this skill
- KPI writeback requires a schema declaration in `schema/**` and explicit approval
- KPIs must be derivable from existing repo evidence; external data imports are
  not permitted
- Missing evidence for a KPI dimension must be surfaced as a gap, not silently omitted

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `.github/skills/report-content-quality/SKILL.md`
- `.github/skills/prioritize-quality-follow-up/SKILL.md`
- `.github/agents/quality-analyst.md`
- `docs/ideas/spec.md`
