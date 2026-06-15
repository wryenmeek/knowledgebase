---
name: audit-knowledgebase-workspace
description: Audits the framework workspace for reference drift, stale commands, attached-tool resolution gaps, and instruction-locality drift. Use when verifying that skills, agents, tests, thin wrappers, and read-only improve dry-runs still point at real repo-local surfaces.
category: dev-support
---

# Audit Knowledgebase Workspace

## Overview

Use this skill to self-audit the framework layer as the skill and agent surface grows. The default flow remains the current structural lint workflow via existing repository checks. The orchestrator scaffold currently returns empty findings even though Phase 4 classifier components are landed; wiring slices remain pending.

## Classification

- **Mode:** Read-only scaffold; **Category:** `dev-support`; **Status:** Active Phase 3 scaffold
- **Boundary:** Audit and handoff only; no self-heal edits, broad crawler, or second runtime.
- **Forward references:** `.github/.customizations.lock` (declared by ADR-028;
  pending issue #191; not acquired here), Phase 4 apply wiring (#208–#211), and
  slice 9b lock acquisition (#209).

## When to Use

- Framework skills, agents, prompts, or tests changed together
- A plan or PR may have introduced broken references or stale commands
- Attached wrapper allowlists or tool-resolution paths may have drifted
- You need a deterministic audit of repo-local framework surfaces before merge
- You need the Phase 3 `improve` dry-run scaffold without applying mutations
- Orphaned but useful framework assets need governed follow-up rather than silent deletion

## Contract

- Input: the current framework workspace or a scoped set of changed framework files
- Audit targets: skill docs, agent docs, hooks, framework tests, and thin wrapper references
- Default flow: structural lint only through the existing framework test commands
- Logic surface: compatibility `default` mode and `improve` dry-run mode return empty findings at this slice
- Output: a pass/fail audit summary with zero writes attempted
- Handoff rule: failures route to the owning skill or `review-wiki-plan`; useful
  orphaned assets route to governed planning rather than ad hoc fixes

## Assertions

- Repo-local references and commands must resolve deterministically
- Attached-tool and wrapper allowlist paths must point to real repo-local files
- The audit fails closed on missing framework dependencies
- The logic scaffold is `read-only only`; writable paths are none and writes are forbidden
- The `improve` scaffold returns empty findings until classifier/orchestrator wiring lands
- Self-healing, classifier output, apply mode, and lock acquisition are deferred

## Phase 4 classifier components (landed; not yet wired into orchestrator)

- Slice 8a (#202): `logic/skill_corpus_cache.py` landed; covered by `tests/kb/test_audit_workspace_cache.py`.
- Slice 8b (#203): finding schema landed at `schema/finding.schema.json`; covered by `tests/kb/test_audit_workspace_finding_schema.py`.
- Slice 8c (#204): `logic/friction_queries.py` landed; covered by `tests/kb/test_audit_workspace_friction_queries.py`.
- Slice 8d (#205): `logic/stale_generator.py` landed; covered by `tests/kb/test_audit_workspace_stale_generator.py`.
- Slice 8e (#206): `logic/redundancy_generator.py` landed; covered by `tests/kb/test_audit_workspace_redundancy_generator.py`.
- Orchestrator status: `logic/audit_workspace.py --mode improve` remains a read-only dry-run scaffold that emits empty findings until slices 5a/5b/9a/9b/9c wire classifier execution and apply behavior.

## Procedure

1. Run the default structural lint flow with the framework test commands below, which audit repo-local links, command examples, wrapper allowlists, and attached-tool references.
2. When requested, run the logic surface in `--mode improve`; this scaffold returns
   an empty findings list and records `writes_attempted: 0`.
3. Route failures to the owning skill or `review-wiki-plan`; route broader
   integration work through governed planning instead of invisible fixes.

## Commands

```bash
python3 .github/skills/audit-knowledgebase-workspace/logic/audit_workspace.py --mode improve
python3 -m unittest tests.kb.test_framework_references tests.kb.test_skill_wrappers
python3 -m unittest tests.kb.test_framework_contracts tests.kb.test_framework_skills tests.kb.test_framework_agents
python3 -m pytest tests/kb/test_doc_cascade_completeness.py tests/kb/test_docs_ideas_archival.py -v
```

## Verification

- [ ] Repo-local references and commands resolve
- [ ] Attached-tool and wrapper paths resolve to real files
- [ ] Phase 3 `improve` scaffold returns empty findings
- [ ] `writes_attempted` remains `0`
- [ ] No daemon, crawler, auto-edit, or `.github/.customizations.lock` acquisition occurs
- [ ] The audit stays inside existing framework tests and repo-local surfaces

## References

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/decisions/ADR-028-instruction-locality-ladder.md`](../../../docs/decisions/ADR-028-instruction-locality-ladder.md) (Accepted)
- `.github/.customizations.lock` declaration (pending, issue #191)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`docs/decisions/ADR-007-control-plane-layering-and-packaging.md`](../../../docs/decisions/ADR-007-control-plane-layering-and-packaging.md)
- [`docs/ideas/wiki-curation-agent-framework.md`](../../../docs/ideas/wiki-curation-agent-framework.md)
- Phase 4 classifier/apply work (issues #202–#211)
- [`references/locality-ladder.md`](references/locality-ladder.md)
- [`tests/kb/test_framework_references.py`](../../../tests/kb/test_framework_references.py)
- [`tests/kb/test_skill_wrappers.py`](../../../tests/kb/test_skill_wrappers.py)
