---
name: prioritize-curation-backlog
description: Ranks open curation work items by quality signals and evidence priority. Use when quality-analyst needs to produce an evidence-backed prioritized backlog recommendation before routing work to knowledgebase-orchestrator.
---

# Prioritize Curation Backlog

## Overview

This skill documents the curation-backlog prioritization step for the `quality-analyst`
persona. It combines quality scores, freshness findings, missed-query gaps, and
maintenance recommendations into a ranked backlog of curation work. Prioritization is
a recommendation only — no work items are automatically created, assigned, or
activated. The ranked backlog routes to `knowledgebase-orchestrator` for intake
consideration.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Recommendation only. No write path is opened by this skill.

## When to Use

- `quality-analyst` has accumulated quality scores, freshness findings, and missed-query
  gaps and needs to produce a prioritized next-action list
- `knowledgebase-orchestrator` needs an evidence-backed backlog recommendation before
  authorizing new synthesis or maintenance work
- An operator wants a structured view of what curation work to tackle next
- A sprint or maintenance cycle needs a ranked work queue derived from repo evidence

## Contract

- Input: quality scores, freshness findings, coverage-gap report, and any existing
  backlog items from `wiki/backlog.md`
- Output: a ranked list of curation work items with priority tier, supporting evidence
  citations, and suggested next lane
- Handoff: the ranked backlog routes to `knowledgebase-orchestrator`; no work item
  is activated without orchestrator authorization

## Assertions

- Prioritization is based on repo evidence only; speculation or external preferences
  must not influence rankings without explicit operator input
- No wiki write path is opened by this step
- Curation work items without supporting evidence citations are deprioritized, not
  silently accepted
- Any writeback to `wiki/backlog.md` requires explicit authorization from
  `sync-knowledgebase-state`

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `wiki/backlog.md`
- `.github/skills/prioritize-quality-follow-up/SKILL.md`
- `.github/agents/quality-analyst.md`
- `.github/agents/knowledgebase-orchestrator.md`
