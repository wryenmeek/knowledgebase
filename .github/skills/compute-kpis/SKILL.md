---
name: compute-kpis
description: Aggregates repo-level quality KPIs from existing quality-scores report artifacts. Use when quality-analyst needs a read-only KPI snapshot to inform curation prioritization or operator reporting.
---

# Compute KPIs

## Overview

This skill implements KPI aggregation for the `quality-analyst` persona.
KPIs are derived from `wiki/reports/quality-scores-*.json` artifacts (written by
`quality_runtime.py score-update`) and expressed as ratios and counts
(e.g., average quality score, stale page percentage, high/low score counts).

KPI computation is **read-only**. Any KPI writeback or durable report artifact
requires explicit maintainer approval and a schema declaration in `schema/**`.

## Classification

- **Mode:** `snapshot` — read-only KPI derivation from available score artifacts
- **MVP status:** Active
- **Execution boundary:** Read-only. No write path is opened.

## When to Use

- `quality-analyst` needs an aggregate health snapshot of the wiki
- An operator wants to track quality trend signals across a maintenance cycle
- `prioritize-curation-backlog` requires KPI context to rank follow-up work
- A governance review needs summary statistics about wiki health without a full audit

## Contract

- **Input:** `wiki/reports/quality-scores-*.json` artifacts produced by
  `quality_runtime.py score-update`
- **Output:** structured KPI snapshot with `page_count`, `avg_score`,
  `low_score_count`, `high_score_count`, `score_coverage_pct`; returns empty
  snapshot (not failure) when no artifacts exist
- **Handoff:** KPI snapshot informs `prioritize-curation-backlog` and operator
  reporting; no durable write is opened

## Assertions

- KPI computation is read-only; no write path is opened by this skill
- KPI writeback requires a schema declaration in `schema/**` and explicit approval
- KPIs must be derivable from existing repo evidence; external data imports are
  not permitted
- Missing or malformed score artifacts surface as warnings; the scan continues
  with remaining artifacts rather than hard-failing

## References

- `AGENTS.md`
- `schema/report-artifact-contract.md`
- `raw/processed/SPEC.md`
- `.github/skills/compute-kpis/logic/compute_kpis.py`
- `.github/skills/report-content-quality/SKILL.md`
- `.github/skills/prioritize-quality-follow-up/SKILL.md`
- `.github/agents/quality-analyst.md`
