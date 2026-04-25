---
name: plan-wiki-job
description: Produces a structured execution plan for a multi-step wiki curation job before any lane work begins. Use when knowledgebase-orchestrator must serialize a complex work sequence, estimate prerequisites, and confirm that all required inputs exist before activating downstream lanes.
---

# Plan Wiki Job

## Overview

This skill documents the job-planning step for the `knowledgebase-orchestrator` persona.
Before a complex or multi-step wiki curation job is activated, this step produces
a structured execution plan: ordered steps, required prerequisites per step,
estimated scope, and stop conditions. The plan is an orchestration artifact —
not a write-capable action — and must be reviewed before any lane is activated.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Planning and prerequisite confirmation only. No write
  path is opened by this skill.

## When to Use

- A multi-step curation job (e.g., ingest + synthesis + topology + publish) needs
  a serialized plan before activation
- `knowledgebase-orchestrator` must confirm that all lane prerequisites exist
  before routing work to `source-intake-steward`, `synthesis-curator`, or
  `topology-librarian`
- An operator wants a pre-flight checklist before starting a large batch job
- A prior failed job needs a revised plan before retry

## Contract

- Input: a work item or job description, available context from prior steps, and
  current repo state (index, log, open-questions)
- Output: a structured plan with ordered steps, prerequisite checks, expected
  outputs, stop conditions, and HITL/AFK classification per step (ADR-014)
- Handoff: the plan is the entry artifact for the first lane step; no lane is
  activated without a confirmed plan

## Assertions

- No write path is opened by plan creation
- A plan without explicit prerequisites and stop conditions is incomplete and must
  not be activated
- The plan does not promise outcomes that would require undeclared write surfaces
- Plan revision requires re-confirmation of all prerequisites
- Each step in the plan must be classified HITL or AFK per the ADR-014 allowlist
- Steps classified AFK must match an allowlist rule; unmatched steps default to HITL

## Issue tracking

See `route-wiki-task` for issue tracking guidance. HITL-classified steps
should have a tracking Issue; AFK-classified steps may skip Issue creation.

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `.github/agents/knowledgebase-orchestrator.md`
- `docs/decisions/ADR-014-hitl-afk-work-classification.md`
