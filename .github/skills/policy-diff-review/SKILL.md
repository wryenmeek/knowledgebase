---
name: policy-diff-review
description: Reviews repository diffs for policy, provenance, and citation risk so change-patrol can emit governed follow-up without remediating content directly. Use when wiki or source edits need diff-based risk classification before governance decides what happens next.
---

# Policy Diff Review

## Overview

Use this skill to keep the change-patrol lane diff-based and recommendation-first. It evaluates already-existing repository diffs for citation removal, provenance drift, governed metadata loss, topology pressure, or destructive edits, then packages the result as a policy/citation-risk review bundle. This is a doc-only workflow: no direct revert, remediation, or content rewrite occurs here.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Diff review and governed handoff only. Any content-changing follow-up must return to `knowledgebase-orchestrator` for `evidence-verifier` and `policy-arbiter` review.

## When to Use

- `change-patrol` receives a diff touching `wiki/**`, `raw/inbox/**`, `raw/processed/**`, or `wiki/index.md`
- A review needs explicit classification of citation-removal, provenance, metadata, or topology risk
- Human edits may be destructive, policy-sensitive, or structurally non-compliant
- A maintainer needs a deterministic route-back decision instead of a direct fix

## Contract

- Input: repo-local diff scope, changed paths, and any triggering governance context
- Classification rule: label each change as intake, evidence, policy, topology, maintenance, or Human Steward follow-up and record severity based on citation, provenance, metadata, or structural impact
- Governance rule: destructive or non-compliant changes route back through `knowledgebase-orchestrator`, then `evidence-verifier` and `policy-arbiter`, before any downstream content-changing lane reopens
- Output: a policy-diff review bundle naming changed paths, observed risk, supporting evidence, and the required next lane

## Assertions

- The skill stays diff-based and does not invent a crawler, daemon, or surveillance runtime
- No direct revert, remediation, suppression, or content rewrite is permitted from this skill
- Citation or provenance removal is treated as a governed risk signal, not an auto-fix trigger
- Unsupported destructive actions fail closed and escalate instead of mutating repository state
- Recommendation-first routing remains explicit and deterministic

## Procedure

### Step 1: Scope the diff

Read only the repo-local changed paths and diff context needed to understand the edit.

### Step 2: Classify risk

Identify whether the change threatens citations, provenance, governed metadata, namespace placement, or other policy-sensitive constraints, then assign the required reassessment lane.

### Step 3: Package governed follow-up

Create a policy-diff review bundle that records the changed paths, triggering evidence, severity, and the downstream governance lane.

### Step 4: Fail closed on remediation asks

If the request expects an automatic revert, cleanup, or destructive edit, block it and escalate through governance or Human Steward review.

## Commands

```bash
git --no-pager diff -- raw/inbox raw/processed wiki .github/agents/change-patrol.md
python3 -m unittest tests.kb.test_change_patrol_runtime
```

## Boundaries

- Do not edit `wiki/**`, `raw/processed/**`, or `wiki/index.md` from this skill
- Do not bypass `knowledgebase-orchestrator`, `evidence-verifier`, or `policy-arbiter`
- Do not convert advisory diff findings into direct remediation authority
- Do not introduce a direct revert path for citation or policy failures

## Verification

- [ ] The review output classifies edit risk from repository diffs
- [ ] Citation and provenance risk route back through governance
- [ ] No direct remediation or revert path is introduced
- [ ] Commands and references resolve inside the repository

## References

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`docs/decisions/ADR-007-control-plane-layering-and-packaging.md`](../../../docs/decisions/ADR-007-control-plane-layering-and-packaging.md)
- [`docs/ideas/wiki-curation-agent-framework.md`](../../../docs/ideas/wiki-curation-agent-framework.md)
- [`schema/ingest-checklist.md`](../../../schema/ingest-checklist.md)
- [`schema/page-template.md`](../../../schema/page-template.md)
- [`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md)
- [`.github/agents/change-patrol.md`](../../agents/change-patrol.md)
