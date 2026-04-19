---
name: cross-reference-symmetry-check
description: Audits wiki cross-references for symmetry, dangling links, and unreciprocated relationships. Use when maintenance-auditor needs a deterministic link-health evidence surface before recommending any topology remediation.
---

# Cross-Reference Symmetry Check

## Overview

This skill documents the cross-reference symmetry audit for the `maintenance-auditor`
persona. It checks that relationships between wiki pages are reciprocal where required,
that referenced pages exist, and that anchor links resolve. Findings are read-only;
any topology repair routes through `knowledgebase-orchestrator` and `topology-librarian`.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Read-only topology evidence only. No link repair or
  redirect creation is performed by this skill.

## When to Use

- A wiki page has been updated or added and cross-reference health needs to be checked
- `maintenance-auditor` needs link-health evidence before recommending a topology fix
- An index drift or topology-hygiene validator finding needs deeper cross-reference
  attribution
- A supersede or archive action requires confirming all references to the affected
  page are identified

## Contract

- Input: a set of wiki pages (or the full `wiki/**` scope)
- Output: a structured list of cross-reference findings per page including dangling
  links, non-reciprocal relationships, and broken anchors
- Handoff: findings route to `maintenance-auditor` and then `topology-librarian`
  for governed follow-up

## Assertions

- No write path is opened by this skill
- Dangling link or broken anchor findings must be explicit, not silently omitted
- Any cross-reference repair routes back through `knowledgebase-orchestrator` and
  `topology-librarian`
- This skill does not create or modify redirects directly

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `schema/taxonomy-contract.md`
- `.github/skills/check-link-topology/SKILL.md`
- `.github/agents/maintenance-auditor.md`
