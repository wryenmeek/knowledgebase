---
name: report-content-quality
description: Summarizes repo-local content quality through the approval-gated reporting surface. Use when you need deterministic quality signals over docs or wiki content without persisting undeclared report artifacts.
---

# Report Content Quality

## Overview

This thin skill routes content-quality reporting to `scripts/reporting/content_quality_report.py`. The heavy repo walk and quality counting stay in the repo-level reporting script while any durable report persistence remains blocked until a schema-backed artifact contract exists.

## When to Use

- When you need a summary of missing `sources`, missing `updated_at`, or placeholder markers in `docs/**` or `wiki/**`
- When you want a deterministic placeholder-focused audit without writing report files
- When a later-phase reporting workflow needs explicit approval-gated persist signaling that still fails closed today

## Contract

- Inputs stay typed: `--mode`, repeated `--path`, and optional `--approval`
- The skill routes directly to `scripts/reporting/content_quality_report.py`
- `summary` and `placeholder-audit` remain read-only; `persist` stays approval-gated and blocked until a durable report contract exists
- Reporting remains repo-local and deny-by-default for writes

## Assertions

- No `.github/skills/report-content-quality/logic/**` helper is introduced
- No undeclared durable report artifact is written from this skill
- Quality signals stay deterministic and derived from repo-local evidence only
- The heavy report implementation stays in `scripts/reporting/content_quality_report.py`

## Commands

```bash
python3 scripts/reporting/content_quality_report.py --mode summary --path wiki
python3 scripts/reporting/content_quality_report.py --mode placeholder-audit --path docs
python3 scripts/reporting/content_quality_report.py --mode persist --path wiki --approval approved
```

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/ideas/wiki-curation-agent-framework.md`
- `scripts/reporting/content_quality_report.py`
