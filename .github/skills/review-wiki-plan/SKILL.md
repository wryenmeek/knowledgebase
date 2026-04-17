---
name: review-wiki-plan
description: Reviews wiki plans against MVP governance and deterministic execution boundaries. Use when evaluating proposed wiki work before implementation or approval.
---

# Review Wiki Plan

## Overview

Review the proposed wiki plan before implementation. This skill is procedural and governance-focused: it checks whether planned work stays inside the repository's MVP control-plane boundary and uses authoritative contracts instead of inventing new execution surfaces.

## When to Use

- Before implementing wiki-curation framework work
- When a plan proposes new wrappers, validators, or state-management steps
- When deciding whether planned work is MVP-safe or deferred

## Review checklist

1. Confirm the plan stays within the ratified MVP boundary: `.github/skills/**`, `.github/agents/**`, `scripts/kb/**`, `tests/kb/**`, boundary docs under `docs/**`, and schema contracts under `schema/**`.
2. Reject plans that introduce new repo-level `scripts/validation/*`, `scripts/reporting/*`, `scripts/context/*`, or `scripts/maintenance/*` trees in MVP.
3. Require fixed repo-root execution, typed args only, and no shell/eval/dynamic dispatch for wrapper helpers.
4. Require validators to default to read-only/no-network behavior.
5. Require no-write-on-failure for any write-capable helper.
6. Verify referenced commands and paths exist before approving the plan.
7. When the plan includes execution, run:

```bash
python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py
```

## Required references

- `AGENTS.md`
- `docs/architecture.md`
- `docs/decisions/ADR-007-control-plane-layering-and-packaging.md`
- `docs/ideas/wiki-curation-agent-framework.md`
- `schema/page-template.md`
- `schema/ingest-checklist.md`

## Approval criteria

- Uses existing `scripts/kb/**` entrypoints as the authoritative execution surface
- Keeps helpers thin and deterministic
- Makes validator/write boundaries explicit
- Defers heavyweight automation outside the MVP boundary
