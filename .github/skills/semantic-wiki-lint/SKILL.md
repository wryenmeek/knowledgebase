---
name: semantic-wiki-lint
description: Audits wiki pages for semantic maintenance risk including stale summaries, orphaned evidence, and broken structural relationships. Use when maintenance-auditor needs a deterministic evidence surface before recommending any remediation action.
---

# Semantic Wiki Lint

## Overview

This skill documents the semantic-lint step for the `maintenance-auditor` persona.
Semantic wiki lint goes beyond syntax checking to flag pages where evidence no longer
supports the summary, where referenced entities or concepts have been superseded, or
where structural relationships are broken. Findings are read-only and route back
through `knowledgebase-orchestrator` before any remediation write path opens.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Read-only audit only. No direct wiki write or remediation.

## When to Use

- A regular maintenance cycle needs a structured semantic health assessment
- `maintenance-auditor` requires a deterministic evidence surface for triage
- A wiki page has changed recently and semantic drift needs to be checked
- An operator suspects that summaries no longer match their evidence

## Contract

- Input: a set of wiki pages (or the full `wiki/**` scope)
- Output: a structured list of semantic findings per page, including affected page,
  finding type, and remediation recommendation
- Handoff: findings are passed to `maintenance-auditor` for triage; any content-
  changing remediation routes through `knowledgebase-orchestrator`

## Assertions

- No write path is opened by this skill
- Findings are recommendations only; remediation requires a separate governed step
- Missing evidence, broken cross-references, or structural violations are flagged
  explicitly rather than silently passed
- This skill does not delete, archive, or supersede pages directly

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `schema/page-template.md`
- `schema/taxonomy-contract.md`
- `.github/agents/maintenance-auditor.md`
- [Manual of Style](../references/manual-of-style.md) — prose register, heading conventions, vocabulary standards
