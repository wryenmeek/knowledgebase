---
name: validate-wiki-governance
description: Validates wiki governance gates with fixed read-only checks. Use when reviewing wiki safety, proving governance compliance, or before any state-changing wiki action.
---

# Validate Wiki Governance

## Overview

Run the governance gate before proposing or approving wiki changes. This skill stays inside the post-MVP wrapper boundary by running only deterministic repo-local checks for SourceRef shape, page-template compliance, append-only log discipline, and approved topology hygiene.

## When to Use

- Before any write-capable wiki workflow
- When checking fail-closed governance behavior
- When reviewing whether protected wiki paths are safe to mutate
- When you need advisory `signal` mode for non-protected follow-up

## Fixed validation path

Run from the repository root:

```bash
python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py
python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py --mode signal --path README.md --validator page-template
python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py --mode blocking --path wiki/index.md --validator topology-hygiene
python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py --mode signal --validator freshness-threshold
```

Supported validators:

1. `sourceref-shape`
2. `page-template`
3. `append-only-log`
4. `topology-hygiene`
5. `freshness-threshold` (opt-in — must be passed explicitly via `--validator freshness-threshold`; not included in the default set)

Protected/write paths default to `blocking` mode even when `--mode` is omitted. Unsupported validators, missing prerequisites, and partial results are hard failures on protected/write paths.

## Execution boundaries

- No shell, `eval`, or dynamic script-path dispatch
- Fixed repository root derived from the wrapper location
- Typed `signal` and `blocking` modes only; no free-form command forwarding
- Read-only validation only
- No network behavior
- Fail closed on unsupported validators, missing prerequisites, and protected-path partial results
- Approved post-MVP checks only; no crawl-heavy analysis or broad reporting runtime

## Inputs and references

- Governance policy: `AGENTS.md`
- Architecture boundary: `docs/architecture.md`
- Packaging rule: `docs/decisions/ADR-007-control-plane-layering-and-packaging.md`
- Page/schema contracts: `schema/page-template.md`, `schema/ingest-checklist.md`
- Topology contract: `schema/taxonomy-contract.md`

## Do not use this skill for

- Broad reporting pipelines
- Heavyweight freshness analysis or repo-wide maintenance crawlers
- New repo-level `scripts/validation/*`, `scripts/reporting/*`, `scripts/context/*`, or `scripts/maintenance/*` trees before approval
- Ad hoc shell command execution
