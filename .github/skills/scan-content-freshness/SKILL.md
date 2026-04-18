---
name: scan-content-freshness
description: Scans repo-local markdown freshness through the approved validation script family. Use when you need deterministic age checks over wiki or docs content without re-implementing freshness logic inside a skill wrapper.
---

# Scan Content Freshness

## Overview

Use this skill as a thin operator-facing wrapper over `scripts/validation/check_doc_freshness.py`. The skill keeps freshness logic in the repo-level validation surface and exposes only typed arguments for scope, as-of date, max age, and optional repo-relative path filters. In maintenance flows, treat the result as read-only evidence for `maintenance-auditor` or `recommend-maintenance-follow-up`, not as permission to edit stale content directly.

## When to Use

- When you need a deterministic freshness check for `wiki/**` or `docs/**`
- When you want repo-root execution without adding wrapper-local policy logic
- When a maintenance or quality review needs fail-closed freshness evidence

## Contract

- Inputs are typed only: `scope`, `as_of`, `max_age_days`, and optional repeated repo-relative `path`
- The skill routes directly to `scripts/validation/check_doc_freshness.py`
- Execution stays repo-local and read-only
- Freshness findings may inform `maintenance-auditor`, but any page edit, archive, supersede, or index change returns to `knowledgebase-orchestrator` for `evidence-verifier` and `policy-arbiter` review first
- Any invalid path, missing `updated_at`, invalid timestamp, or stale document fails closed

## Assertions

- No `.github/skills/scan-content-freshness/logic/**` helper is introduced
- No shell expansion, dynamic dispatch, or wrapper-local freshness scoring is introduced
- The script runs from the repository root and returns deterministic JSON
- Writes remain forbidden for this skill and script family
- No direct remediation or write-capable handoff is introduced from freshness output alone

## Commands

Run from the repository root:

```bash
python3 scripts/validation/check_doc_freshness.py --scope wiki --as-of 2024-01-31 --max-age-days 45
python3 scripts/validation/check_doc_freshness.py --scope docs --as-of 2024-01-31 --max-age-days 30 --path docs/mvp-runbook.md
```

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/decisions/ADR-007-control-plane-layering-and-packaging.md`
- `docs/ideas/spec.md`
- `scripts/validation/check_doc_freshness.py`
