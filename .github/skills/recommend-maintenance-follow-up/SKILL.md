---
name: recommend-maintenance-follow-up
description: Packages maintenance findings into a recommendation-first handoff that sends content-changing follow-up back through governance. Use when maintenance review identifies stale, orphaned, archive, supersede, or discoverability issues that may need later governed remediation.
---

# Recommend Maintenance Follow-Up

## Overview

Use this skill to keep the maintenance lane read-only in MVP. It packages findings
from `maintenance-auditor`, `scan-content-freshness`, and related review surfaces
into a governed recommendation bundle. This is a doc-only workflow: no direct
`wiki/**` edit, archive action, or index mutation occurs here.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Recommendation-first handoff only. Content-changing
  follow-up must return to `knowledgebase-orchestrator` before any downstream
  write-capable surface reopens.

## When to Use

- `maintenance-auditor` identified stale, orphaned, contradiction, or
  archive/supersede pressure
- `scan-content-freshness` found stale content that may need editorial follow-up
- Discoverability review suggests a governed page, index, or taxonomy change
- A maintainer needs a clear split between read-only evidence and later governed
  remediation

## Contract

- Input: maintenance findings, affected page list, and repo-local evidence only
- Packaging rule: separate read-only observations from requested content changes
- Governance rule: content-changing work returns to `knowledgebase-orchestrator`
  for `evidence-verifier` and `policy-arbiter` review before any downstream
  execution
- Output: a maintenance recommendation bundle naming the evidence, affected
  paths, requested follow-up lane, and blocked/deferred items

## Assertions

- The skill is recommendation-first and does not remediate content directly
- No direct wiki write, archive action, redirect creation, or bulk rewrite is
  permitted from this skill
- Evidence stays repo-local and deterministic
- Unsupported crawler, reporting, or maintenance runtime expansion remains
  deferred
- Fail closed when the requested follow-up would bypass orchestrator, evidence,
  or policy review

## Procedure

### Step 1: Gather read-only evidence

Collect the maintenance findings bundle, freshness output, and any relevant
taxonomy or discovery notes without mutating repository state.

### Step 2: Split observations from remediation asks

List the facts first, then separately name any content-changing request such as
page edits, archive/supersede decisions, topology refreshes, or index updates.

### Step 3: Route governed follow-up

Send any content-changing ask back to `knowledgebase-orchestrator` so
`evidence-verifier` and `policy-arbiter` can clear scope before
`topology-librarian`, `synthesis-curator`, or `sync-knowledgebase-state` are
reopened.

### Step 4: Defer unsupported runtime expansion

If the request depends on a new `scripts/maintenance/**`, `scripts/reporting/**`,
or crawler-style runtime, block it and record a defer recommendation instead of
inventing new automation.

## Commands

```bash
python3 scripts/validation/check_doc_freshness.py --scope wiki --as-of 2024-01-31 --max-age-days 45
python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py --mode signal --validator topology-hygiene --path wiki/index.md
python3 -m unittest tests.kb.test_maintenance_runtime
```

## Boundaries

- Do not edit `wiki/**` from this skill
- Do not bypass `knowledgebase-orchestrator`, `evidence-verifier`, or
  `policy-arbiter`
- Do not invent a new maintenance remediation runtime in MVP
- Do not treat advisory findings as permission to perform direct content changes

## Verification

- [ ] Findings remain read-only and recommendation-first
- [ ] Content-changing follow-up routes back through governance
- [ ] Deferred runtime expansion is recorded instead of implemented
- [ ] Commands and referenced surfaces resolve inside the repository

## References

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`docs/decisions/ADR-007-control-plane-layering-and-packaging.md`](../../../docs/decisions/ADR-007-control-plane-layering-and-packaging.md)
- [`docs/ideas/wiki-curation-agent-framework.md`](../../../docs/ideas/wiki-curation-agent-framework.md)
- [`.github/agents/maintenance-auditor.md`](../../agents/maintenance-auditor.md)
- [`.github/skills/scan-content-freshness/SKILL.md`](../scan-content-freshness/SKILL.md)
- [`.github/skills/review-wiki-plan/SKILL.md`](../review-wiki-plan/SKILL.md)
- [`.github/skills/search-and-discovery-optimization/SKILL.md`](../search-and-discovery-optimization/SKILL.md)
- [`.github/skills/validate-wiki-governance/SKILL.md`](../validate-wiki-governance/SKILL.md)
