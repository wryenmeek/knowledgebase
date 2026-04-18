---
name: prepare-high-value-synthesis-handoff
description: Packages a cited query or synthesis result for governed durable follow-up without writing directly. Use when an answer or draft insight appears valuable enough to route back through orchestrator, evidence, and policy gates.
---

# Prepare High-Value Synthesis Handoff

## Overview

Use this skill when the right next step is not immediate persistence but a
governed handoff package. In MVP it is a doc-only workflow: take a cited query
result or synthesis summary, explain why it may deserve durable follow-up, and
route that package back through governance.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Packaging and escalation only. Do not publish a page,
  mutate `wiki/`, or bypass persistence controls from this skill.

## When to Use

- A cited answer appears reusable enough to merit governed durable review
- `query-synthesist` or `synthesis-curator` has produced a bounded result that
  should be preserved for later editorial follow-up
- Comparative or cross-page synthesis is valuable but still needs control-plane
  review before any write-capable path opens
- A reviewer needs a consistent artifact explaining why follow-up is worthwhile
- Durable persistence must route back through orchestrator and policy gates

## Contract

- Input: a cited answer, synthesis bundle, or comparative analysis plus the
  consulted evidence scope
- Output: a high-value handoff package describing the proposed durable outcome,
  citations, scope boundary, persistence rationale, and blockers
- Handoff artifact: a high-value synthesis handoff containing cited findings,
  consulted pages or sources, intended downstream lane, and required re-review
  notes
- Escalation artifact: a durable-follow-up ambiguity note describing why the
  value, scope, or policy status remains unresolved
- Handoff rule: every durable candidate returns to `knowledgebase-orchestrator`
  so `evidence-verifier` and `policy-arbiter` can recheck the package before any
  publication-capable step

## Assertions

- High-value recommendations are grounded in cited repository evidence
- Persistence rationale is explicit rather than implied
- Governance-first ordering is preserved for every durable candidate
- Ambiguous value judgments escalate instead of silently opening a write path
- No direct page creation, page update, or persistence side effect occurs here

## Procedure

### Step 1: Summarize the cited result

Capture the answer or synthesis outcome, consulted scope, and key citations in a
form another governed lane can review.

### Step 2: Explain the durable value

State why the result may deserve preservation: repeated demand, cross-page
comparison value, policy significance, or another bounded repository reason.

### Step 3: Name the required downstream lane

Specify whether the candidate should restart at `knowledgebase-orchestrator` for
query persistence review, synthesis drafting review, or Human Steward judgment.

### Step 4: Preserve blockers

Record any evidence gaps, policy uncertainty, or taxonomy/schema ambiguity that
still blocks safe durable follow-up.

### Step 5: Stop before persistence

Return the high-value handoff package instead of calling a write-capable path
directly.

## Boundaries

- Do not treat perceived usefulness as approval to write directly
- Do not skip `knowledgebase-orchestrator`, `evidence-verifier`, or
  `policy-arbiter` for durable candidates
- Do not invent a new persistence queue, tracker, or runtime in MVP
- Do not strip citations or scope notes from the handoff artifact

## Verification

- [ ] The result is cited and scope-bounded
- [ ] The handoff artifact explains why durable follow-up may be worthwhile
- [ ] Required governance lanes are named explicitly
- [ ] Blocking uncertainty is preserved in an escalation artifact when needed
- [ ] No direct durable write path is opened

## References

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`docs/decisions/ADR-007-control-plane-layering-and-packaging.md`](../../../docs/decisions/ADR-007-control-plane-layering-and-packaging.md)
- [`docs/ideas/wiki-curation-agent-framework.md`](../../../docs/ideas/wiki-curation-agent-framework.md)
- [`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md)
- [`scripts/kb/persist_query.py`](../../../scripts/kb/persist_query.py)
