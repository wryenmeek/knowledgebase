---
name: validate-wiki-governance
description: Validates wiki governance gates with fixed read-only checks. Use when reviewing wiki safety, proving governance compliance, or before any state-changing wiki action.
---

# Validate Wiki Governance

## Overview

Run the governance gate before proposing or approving wiki changes. This skill stays inside the MVP boundary by delegating only to deterministic repo-local entrypoints under `scripts/kb/**`.

## When to Use

- Before any write-capable wiki workflow
- When checking fail-closed governance behavior
- When reviewing whether wiki state is safe to sync
- When validating lint/index/preflight prerequisites without mutating repo state

## Fixed validation path

Run from the repository root:

```bash
python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py
```

This wrapper uses fixed repo-root execution and calls only:

1. `python3 scripts/kb/qmd_preflight.py --repo-root <repo-root> --required-resource .qmd/index`
2. `python3 scripts/kb/update_index.py --wiki-root wiki --check`
3. `python3 scripts/kb/lint_wiki.py --wiki-root wiki --strict`

## Execution boundaries

- No shell, `eval`, or dynamic script-path dispatch
- Fixed repository root derived from the wrapper location
- Typed arguments only; no free-form command forwarding
- Read-only by default
- No network behavior
- Fail closed on the first non-zero exit
- No writes occur on failure

## Inputs and references

- Governance policy: `AGENTS.md`
- Architecture boundary: `docs/architecture.md`
- Packaging rule: `docs/decisions/ADR-007-control-plane-layering-and-packaging.md`
- Page/schema contracts: `schema/page-template.md`, `schema/ingest-checklist.md`

## Do not use this skill for

- Broad reporting pipelines
- New repo-level `scripts/validation/*`, `scripts/reporting/*`, `scripts/context/*`, or `scripts/maintenance/*` trees
- Ad hoc shell command execution
