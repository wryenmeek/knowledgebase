---
name: route-wiki-task
description: Selects the correct governed lane for a wiki work item and hands it off to the appropriate persona. Use when knowledgebase-orchestrator must classify incoming work and route it to the ingest lane, query lane, maintenance lane, or review lane.
---

# Route Wiki Task

## Overview

This skill documents the lane-selection and routing step for the `knowledgebase-orchestrator`
persona. Every piece of wiki work enters through this step: the orchestrator classifies
the work type, confirms that prerequisites for the target lane are satisfied, and
hands off to the correct first-contact persona. No work bypasses this step.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Classification and routing only. No direct wiki write.

## When to Use

- New work arrives (new source, query, maintenance request, or curation backlog item)
- `knowledgebase-orchestrator` must select between the ingest lane, query
  lane, maintenance lane, or review lane
- A prior step has escalated an item back to the orchestrator for re-routing
- An operator needs to understand which lane a specific work type belongs in

## Contract

- Input: a work item description (source path, query, maintenance finding, or
  backlog item) and any available prior-step context
- Output: a routing decision specifying the next persona, required prerequisites,
  and lane entry conditions
- Handoff: the routing decision is the required input for the first-contact persona
  in the selected lane
- HITL/AFK classification: each work item is classified as HITL (requires full persona pipeline) or AFK (eligible for fast-path per ADR-014 allowlist) based on the deny-by-default AFK criteria

## Assertions

- No wiki work bypasses the orchestrator routing step
- Lane prerequisites must be confirmed before the handoff is issued
- The orchestrator does not open a write path directly; writes happen only in
  declared downstream writer surfaces
- A work item that cannot be classified as ingest, query, maintenance, or review
  routes to human steward review, not to an arbitrary lane
- Tasks not on the ADR-014 AFK allowlist default to HITL and route through the full persona pipeline
- Operator may override any classification to HITL but NEVER to AFK (deny-by-default)
- AFK-classified tasks still require `wiki/.kb_write.lock`, `wiki/log.md` entry with `classification: afk`, and post-publication `change-patrol` review

## Issue tracking recommendation

For HITL-classified work, create a GitHub Issue as a tracking artifact before
beginning the persona pipeline. Suggested labels: `wiki-change`, `hitl`,
`lane:<ingest|query|maintenance|review>`.

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `.github/agents/knowledgebase-orchestrator.md`
- `docs/decisions/ADR-014-hitl-afk-work-classification.md`
