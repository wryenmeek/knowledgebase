---
name: prioritize-quality-follow-up
description: Prioritizes repo-local quality follow-up through the approval-gated reporting surface. Use when you need recommendation-only ranking from existing evidence while keeping score updates and reporting egress default-off.
---

# Prioritize Quality Follow-up

## Overview

This thin skill routes quality prioritization to `scripts/reporting/quality_runtime.py`. Recommendation-only ranking stays read-only and evidence-backed, while score-updating and reporting-backed modes remain approval-gated and fail closed until an explicit egress contract exists.

## When to Use

- When `quality-analyst` needs repo-local prioritization without writing scores
- When persisted query evidence should inform recommendation-first follow-up
- When an operator wants explicit approval-gated signaling for future score/report modes

## Contract

- Inputs stay typed: `--mode`, repeated `--path`, repeated `--query-evidence`, and optional `--approval`
- The skill routes directly to `scripts/reporting/quality_runtime.py`
- `recommend` remains read-only and recommendation-only
- `score-update` and `report` stay explicit, approval-gated, and fail closed until score writeback and reporting egress contracts are declared

## Assertions

- No `.github/skills/prioritize-quality-follow-up/logic/**` helper is introduced
- No durable score writeback or report artifact is emitted from this skill
- Prioritization stays grounded in repo-local evidence rather than external telemetry
- The heavy implementation stays in `scripts/reporting/quality_runtime.py`

## Commands

```bash
python3 scripts/reporting/quality_runtime.py --mode recommend --path wiki --query-evidence docs/query-evidence.json
python3 scripts/reporting/quality_runtime.py --mode report --path wiki --approval approved
```

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/ideas/wiki-curation-agent-framework.md`
- `scripts/reporting/quality_runtime.py`
