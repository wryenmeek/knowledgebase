---
name: freshness-audit
description: Produces a read-only freshness assessment of wiki or docs content using the approved validation script family. Use when maintenance-auditor needs age-based evidence before recommending follow-up, or when scan-content-freshness results need to be triaged into maintenance recommendations.
---

# Freshness Audit

## Overview

This skill documents the freshness-audit step for the `maintenance-auditor` persona.
It uses `scan-content-freshness` (or directly `scripts/validation/check_doc_freshness.py`)
to produce age-based evidence, then applies the `recommend-maintenance-follow-up` skill
to route stale findings back through the governed maintenance lane. Freshness audit
produces read-only findings — it does not edit, archive, or delete content.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Read-only freshness evidence only. All follow-up routes
  through `knowledgebase-orchestrator` before any content change.

## When to Use

- A maintenance cycle needs age-based health signals for `wiki/**` or `docs/**`
- `maintenance-auditor` requires freshness evidence before recommending supersede,
  archive, or refresh actions
- An operator wants to know which pages have exceeded a configurable age threshold
- Freshness findings need to be combined with semantic-lint results for a full
  maintenance triage

## Contract

- Input: scope (`wiki`, `docs`, or `all`), as-of date, and maximum allowed age in days
- Output: a structured freshness report listing stale files and their age
- Handoff: stale findings route to `recommend-maintenance-follow-up` and then to
  `knowledgebase-orchestrator` for any content-changing follow-up

## Assertions

- No write path is opened by this skill
- Freshness findings are evidence for triage, not authorization for direct edits
- Missing `updated_at` or invalid timestamps are flagged as findings, not silently
  skipped
- All remediation routes back through the governed maintenance lane

## Commands

Run from the repository root (delegates to `scan-content-freshness`):

```bash
python3 scripts/validation/check_doc_freshness.py --scope wiki --as-of <YYYY-MM-DD> --max-age-days 90
```

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `scripts/validation/check_doc_freshness.py`
- `.github/skills/scan-content-freshness/SKILL.md`
- `.github/skills/recommend-maintenance-follow-up/SKILL.md`
- `.github/agents/maintenance-auditor.md`
