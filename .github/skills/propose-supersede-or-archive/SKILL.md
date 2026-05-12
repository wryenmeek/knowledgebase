---
name: propose-supersede-or-archive
description: Produces a governed recommendation to supersede or archive a wiki page based on maintenance-auditor findings. Use when semantic-lint, freshness-audit, or cross-reference results indicate a page should be retired, replaced, or marked as historical.
---

# Propose Supersede or Archive

## Overview

This skill documents the supersede/archive proposal step for the `maintenance-auditor`
persona. A proposal is a structured recommendation with evidence citations — not a
direct action. The proposal routes back through `knowledgebase-orchestrator` and
requires explicit `policy-arbiter` clearance before any page status changes to
`superseded` or `archived`.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Recommendation only. No direct page mutation, status change,
  or redirect creation.

## When to Use

- A page has been flagged as stale, orphaned, or semantically outdated by prior
  maintenance audit steps
- An updated entity or concept page exists that should replace an older version
- A source has been retracted or superseded and any pages derived from it need
  status updates
- `maintenance-auditor` must produce a governed evidence record before escalating
  to human steward review

## Contract

- Input: the target page path, the audit finding that justifies the action, the
  proposed new status (`superseded` or `archived`), and any replacement page reference
- Output: a structured proposal record with page path, proposed action, evidence
  citations, and next required governance step
- Handoff: the proposal routes to `knowledgebase-orchestrator` → `policy-arbiter`
  before any write is authorized

## Assertions

- No page status is changed directly by this skill
- A proposal without supporting evidence citations fails closed
- Supersede proposals must reference the replacement page or concept
- Archive proposals must confirm the page is no longer active or relevant
- All status changes route through the governed lane before any write

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `schema/page-template.md`
- `.github/skills/recommend-maintenance-follow-up/SKILL.md`
- `.github/agents/maintenance-auditor.md`
