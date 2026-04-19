---
name: route-wiki-task
description: Selects the correct governed lane for a wiki work item and hands it off to the appropriate persona. Use when knowledgebase-orchestrator must classify incoming work and route it to the intake-safe gate, synthesis lane, maintenance arm, or quality lane.
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
- `knowledgebase-orchestrator` must select between the intake-safe gate, synthesis
  lane, maintenance arm, or quality lane
- A prior step has escalated an item back to the orchestrator for re-routing
- An operator needs to understand which lane a specific work type belongs in

## Contract

- Input: a work item description (source path, query, maintenance finding, or
  backlog item) and any available prior-step context
- Output: a routing decision specifying the next persona, required prerequisites,
  and lane entry conditions
- Handoff: the routing decision is the required input for the first-contact persona
  in the selected lane

## Assertions

- No wiki work bypasses the orchestrator routing step
- Lane prerequisites must be confirmed before the handoff is issued
- The orchestrator does not open a write path directly; writes happen only in
  declared downstream writer surfaces
- A work item that cannot be classified as intake, synthesis, maintenance, or quality
  routes to human steward review, not to an arbitrary lane

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `.github/agents/knowledgebase-orchestrator.md`
