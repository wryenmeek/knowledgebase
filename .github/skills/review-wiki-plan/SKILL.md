---
name: review-wiki-plan
description: Reviews wiki plans against MVP governance and deterministic execution boundaries. Use when evaluating proposed wiki work before implementation or approval.
---

# Review Wiki Plan

## Overview

Use this skill before implementation to pressure-test a wiki plan from multiple
lenses. In MVP it is a doc-only workflow that checks orchestration order,
policy/gov boundaries, QA coverage, documentation hygiene, and deterministic
execution limits before new automation or high-risk changes proceed.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Review and handoff only. Do not approve plans that
  invent new runtime surfaces, bypass governance order, or skip verification.

## When to Use

- Before implementing wiki-curation framework work
- When a plan proposes new wrappers, validators, or state-management steps
- When deciding whether proposed work is MVP-safe or deferred
- When a tranche touches skills, agents, tests, and docs together
- When a high-risk plan needs explicit multi-lens review before execution

## Contract

- Input: a proposed wiki plan, implementation tranche, or automation change
- Review lenses: orchestration, policy, QA, documentation/references, and
  execution-boundary fit
- Output: an approve, revise, or defer recommendation with concrete blocking
  findings and required follow-ups
- Handoff rule: approved work still routes through the normal governance and
  implementation lanes; rejected work records blockers instead of proceeding

## Assertions

- Plans must stay inside the ratified MVP boundary and repo execution surface
- Proposed helpers must be thin, deterministic, typed, and fail-closed
- Verification must be explicit for touched framework surfaces
- Plans must preserve governance-before-durable-follow-up ordering
- Missing references, stale commands, or unsupported runtime expansion are
  blocking until corrected

## Review lenses

### 1. Orchestration lens

Confirm the plan follows the current lane order and routes durable follow-up back
through governance rather than directly to synthesis, topology, or writes.

### 2. Policy lens

Check whether the plan preserves repository guardrails, append-only history,
SourceRef expectations, and fail-closed escalation behavior.

### 3. QA lens

Require relevant existing tests for touched framework surfaces and ensure the
plan does not rely on unverified manual assumptions alone.

### 4. Documentation and references lens

Verify that referenced paths, commands, skills, tests, and attached tools still
resolve and that the plan updates directly related documentation when behavior or
classification changes.

### 5. Execution-boundary lens

Reject new repo-level `scripts/validation/*`, `scripts/reporting/*`,
`scripts/context/*`, or `scripts/maintenance/*` trees and reject shell/eval or
dynamic-dispatch helpers.

## Procedure

1. Confirm the plan stays within the ratified MVP boundary: `.github/skills/**`,
   `.github/agents/**`, `scripts/kb/**`, `tests/kb/**`, boundary docs under
   `docs/**`, and schema contracts under `schema/**`.
2. Verify the plan preserves the governance order: intake -> verification ->
   policy -> synthesis/query/topology.
3. Check that every touched surface has a verification step using existing test
   or wrapper entrypoints.
4. Verify referenced commands, files, validators, and attached-tool paths exist
   before approving the plan.
5. Defer any work that introduces heavyweight automation, hidden state, or
   unsupported runtime expansion.

## Commands

```bash
python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py
python3 -m unittest tests.kb.test_framework_contracts tests.kb.test_framework_skills tests.kb.test_framework_agents tests.kb.test_framework_references tests.kb.test_skill_wrappers
```

## Boundaries

- Do not approve a plan that bypasses governance before durable follow-up
- Do not approve untyped helpers, shell glue, eval, or dynamic dispatch
- Do not treat missing tests or stale references as non-blocking for framework
  changes
- Do not allow new runtime trees outside `scripts/kb/**` in MVP

## Verification

- [ ] Review covers orchestration, policy, QA, documentation, and execution boundaries
- [ ] Referenced commands and paths resolve
- [ ] Verification steps match the touched framework surfaces
- [ ] Governance-before-durable-follow-up ordering is preserved
- [ ] Unsupported runtime expansion is deferred

## References

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`docs/decisions/ADR-007-control-plane-layering-and-packaging.md`](../../../docs/decisions/ADR-007-control-plane-layering-and-packaging.md)
- [`docs/ideas/wiki-curation-agent-framework.md`](../../../docs/ideas/wiki-curation-agent-framework.md)
- [`schema/page-template.md`](../../../schema/page-template.md)
- [`schema/ingest-checklist.md`](../../../schema/ingest-checklist.md)
