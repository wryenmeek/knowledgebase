# ADR-014: HITL/AFK work classification for wiki curation

## Status

Accepted

## Date

2026-04-25

## Context

All wiki curation work currently passes through the full persona pipeline:
`knowledgebase-orchestrator` → `source-intake-steward` → `evidence-verifier` →
`policy-arbiter` → downstream (`synthesis-curator`, `topology-librarian`, etc.).
This sequence is enforced by `test_framework_agents.py` and is appropriate for
high-stakes work such as new page synthesis, entity resolution, and policy
disputes.

However, many wiki maintenance tasks are trivial and deterministic — redirect
management, index regeneration, freshness date updates, backlink suggestions.
These incur the full governance cost without proportional risk.

mattpocock/skills uses a HITL/AFK pattern where tasks are classified as
requiring human interaction (HITL) or being fully automatable (AFK). This
pattern was identified in our comparative research as valuable for reducing
governance overhead on low-risk work.

The `route-wiki-task` skill currently treats all tasks with the same governance
weight. ADR-005 already governs write concurrency via `wiki/.kb_write.lock` —
AFK tasks still need locking, just not the full persona review.

## Alternatives Considered

### A fifth lane ("AFK lane")

Create a dedicated AFK lane alongside the four existing lanes (ingest, query,
maintenance, review). Rejected because it would fragment the lane taxonomy — AFK is a
property of how work moves through an existing lane, not a separate kind of work. A
fifth lane would also require updating every lane-aware test and routing contract.

### Allow-by-default with HITL blocklist

Default all tasks to AFK and maintain a blocklist of tasks that require HITL. Rejected
because the failure mode is worse: an accidentally-unblocked high-stakes task would
bypass governance silently. Deny-by-default means unknown tasks get full review, which
is the safe default for a provenance-first system.

### Per-operator AFK trust levels

Allow trusted operators to classify their own tasks as AFK. Rejected because it
conflates identity with policy — the classification should be based on what the task
does (deterministic criteria), not who is doing it.

## Decision

### 1. Scope: wiki workflow only

This ADR applies only to wiki curation work items routed through
`knowledgebase-orchestrator`. Development workflow HITL/AFK classification is
deferred to a follow-on ADR after the wiki taxonomy proves out with real data.

### 2. HITL/AFK is a property, not a lane

Classification is a property of the four existing lanes (ingest, query,
maintenance, review), NOT a fifth lane. This preserves the existing lane
taxonomy while adding classification metadata.

### 3. Classification authority

- `knowledgebase-orchestrator` performs classification at routing time.
- Operator may override any classification to HITL (escalation is always
  allowed).
- Operator may NEVER override a classification to AFK (deny-by-default).
- `route-wiki-task` records the classification but does not change it.

### 4. AFK allowlist (deny-by-default, exhaustive)

The following tasks are eligible for AFK classification. All other tasks default
to HITL. There is no "probably AFK" tier.

- `manage-redirects-and-anchors` — append-only redirect writes.
- `update-index` — bounded index regeneration from existing wiki state.
- `scan-content-freshness` — read-only freshness check (no writes).
- `suggest-backlinks` — read-only suggestions (no writes).
- `cross-reference-symmetry-check` — read-only link audit (no writes).
- **Metadata-only frontmatter corrections** — restricted to the following
  exhaustive field list: `last_updated` date, `quality_assessment.freshness_date`.
  Permitted formatting changes (no other formatting changes qualify): YAML
  indentation normalization, ISO-8601 timestamp zero-padding (e.g.
  `2024-1-15` → `2024-01-15`), trailing whitespace removal. NO changes to:
  `sources`, `related_pages`, `tags`, `status`, `quality_assessment` text
  fields, `title`, `aliases`, `browse_path`, or any field that encodes claims,
  citations, or entity identity.

### 5. AFK governance — what is STILL required

- `wiki/.kb_write.lock` acquisition and release per ADR-005.
- `wiki/log.md` entry with additional fields: `classification: afk` and
  `allowlist_rule_matched: <rule-name>`.
- `change-patrol` post-publication review within the next scheduled patrol
  cycle.

### 6. AFK governance — what is SKIPPED

- `evidence-verifier` review.
- `policy-arbiter` review.
- `synthesis-curator` draft review.
- These personas are only invoked for HITL-classified work.

### 7. Misclassification safety net

- `patrol-human-edits` applies stricter review thresholds to AFK-classified
  outputs: any citation change, new claim, topology change, or entity reference
  that appears in an AFK output is flagged as a potential misclassification.
- If `maintenance-auditor` or `change-patrol` flags an AFK-published change, it
  re-enters the full persona pipeline via `knowledgebase-orchestrator` with
  metadata `reclassified_from: afk`.
- There is no automatic reclassification from HITL → AFK. Reclassification only
  goes AFK → HITL.
- Deterministic enforcement of the AFK safety net is deferred — the current
  implementation relies on the `patrol-human-edits` agent-interpreted contract.
  When AFK-classified writes become operative, a deterministic validator should
  be added to verify AFK outputs against the §4 allowlist boundaries.

### 8. Audit trail

Every AFK classification is logged to `wiki/log.md` with:

```
classification: afk
lane: <ingest|query|maintenance|review>
allowlist_rule_matched: <rule-name>
reason: <brief justification>
decided_by: <orchestrator|operator>
```

When AFK-classified work is reclassified to HITL (via §7), a reclassification
event is also logged:

```
classification: hitl
reclassified_from: afk
lane: <original lane>
reason: <what triggered reclassification>
decided_by: <patrol|maintenance-auditor|operator>
```

### 9. Interaction with existing tests

`test_framework_agents.py` enforces the persona pipeline sequence.
AFK-classified work is an explicit exception to this sequence, documented here.
Test updates must account for the AFK lane exception without weakening the HITL
pipeline enforcement.

### 10. Advisory pre-classification (`afk-candidate`)

CI workflows that assess AFK eligibility from a single signal (e.g., page age in
`wiki-freshness.yml`) use the term `afk-candidate` — not `afk` — for their
output. This distinction exists because a single signal is insufficient to
confirm full AFK eligibility per §4; a downstream step must verify no open
questions, patrol findings, or source staleness before the classification
becomes the governed `afk` value. `afk-candidate` is advisory only and does not
gate any write path.

## Consequences

### Positive

- Reduces governance latency for deterministic maintenance tasks.
- Enables future CI automation of low-risk wiki updates.
- Maintains full governance for high-stakes work.
- Deny-by-default prevents scope creep of the AFK allowlist.

### Negative

- Introduces misclassification risk (mitigated by the safety net described in
  §7).
- Adds complexity to the routing decision in `knowledgebase-orchestrator`.
- Requires test updates to distinguish HITL from AFK paths.

### Neutral

- Does not create a new lane — augments existing lanes with a classification
  property.
- Does not change the HITL pipeline at all — only creates an alternative for
  qualified AFK tasks.

## Relationship to mattpocock/skills

Inspired by the `to-issues` skill's HITL/AFK classification pattern, adapted
for the knowledgebase's governance-heavy context where "AFK" still requires
lock/log/patrol but can skip persona review.

## References

- `ADR-005-write-concurrency-guards.md`
- `AGENTS.md` (persona pipeline, write-surface matrix)
- `test_framework_agents.py`
- `.github/skills/route-wiki-task/SKILL.md`
- `.github/agents/knowledgebase-orchestrator.md`
