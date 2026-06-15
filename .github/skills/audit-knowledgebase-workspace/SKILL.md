---
name: audit-knowledgebase-workspace
description: Audits the framework workspace for reference drift, stale commands, attached-tool resolution gaps, and instruction-locality drift. Use when verifying that skills, agents, tests, thin wrappers, and read-only improve dry-runs still point at real repo-local surfaces.
category: dev-support
---

# Audit Knowledgebase Workspace

## Overview

Use this skill to self-audit the framework layer as the skill and agent surface grows. The default flow remains the current structural lint workflow via existing repository checks. The Phase 3 `audit_workspace.py` orchestrator still returns empty findings, while Phase 4 classifier components now exist as tested read-only modules that are not yet wired into that orchestrator.

## Classification

- **Mode:** Read-only scaffold orchestrator plus landed read-only classifier components; **Category:** `dev-support`; **Status:** Active Phase 4 components, not yet orchestrator-wired
- **Boundary:** Audit and handoff only; no self-heal edits, broad crawler, or second runtime.
- **Accepted reference:** ADR-028 owns the instruction-locality ladder and trailer governance.
- **Forward references:** apply-mode work (#208–#210), QA gates (#207/#211),
  and slice 9b `.github/.customizations.lock` acquisition (#209).

## When to Use

- Framework skills, agents, prompts, or tests changed together
- A plan or PR may have introduced broken references or stale commands
- Attached wrapper allowlists or tool-resolution paths may have drifted
- You need a deterministic audit of repo-local framework surfaces before merge
- You need the Phase 3 `improve` dry-run scaffold without applying mutations
- Orphaned but useful framework assets need governed follow-up rather than silent deletion

## Phase 4 classifier components (landed; not yet wired into orchestrator)

These read-only components are present and tested, but `audit_workspace.py --mode
improve` does not yet compose them into findings:

| Component | Slice | Purpose | Test coverage |
|---|---|---|---|
| `logic/skill_corpus_cache.py` | 8a / #202 | Cache skill frontmatter plus first prose paragraph for locality/redundancy checks. | `tests/kb/test_audit_workspace_cache.py` |
| `schema/finding.schema.json` | 8b / #203 | Define the 10-bin classifier output contract, including compliance risk and token-efficiency ranking. | `tests/kb/test_audit_workspace_finding_schema.py` |
| `logic/friction_queries.py` | 8c / #204 | Provide repo-scoped and fallback `session_store_sql` query templates for friction-signal mining. | `tests/kb/test_audit_workspace_friction_queries.py` |
| `logic/stale_generator.py` | 8d / #205 | Generate deterministic stale deletion-candidate findings from tracked files, symbols, ADR status, and issue state. | `tests/kb/test_audit_workspace_stale_generator.py` |
| `logic/redundancy_generator.py` | 8e / #206 | Generate cited redundant-up-the-ladder findings from lower-locality evidence. | `tests/kb/test_audit_workspace_redundancy_generator.py` |

## Contract

- Input: the current framework workspace or a scoped set of changed framework files
- Audit targets: skill docs, agent docs, hooks, framework tests, and thin wrapper references
- Default flow: structural lint only through the existing framework test commands
- Orchestrator surface: compatibility `default` mode and `improve` dry-run mode in `audit_workspace.py` return empty findings until wiring lands
- Output: a pass/fail audit summary with zero writes attempted
- Handoff rule: failures route to the owning skill or `review-wiki-plan`; useful
  orphaned assets route to governed planning rather than ad hoc fixes

## Assertions

- Repo-local references and commands must resolve deterministically
- Attached-tool and wrapper allowlist paths must point to real repo-local files
- The audit fails closed on missing framework dependencies
- The logic scaffold is `read-only only`; writable paths are none and writes are forbidden
- The `improve` orchestrator returns empty findings until component wiring lands
- Classifier components are landed and tested, but composed classifier output, apply mode, and lock acquisition are deferred

## Procedure

1. Run the default structural lint flow with the framework test commands below, which audit repo-local links, command examples, wrapper allowlists, and attached-tool references.
2. When requested, run the orchestrator surface in `--mode improve`; it returns
   an empty findings list and records `writes_attempted: 0` until the landed
   classifier components are wired in.
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
- [ ] Phase 3 `improve` orchestrator returns empty findings until wiring lands
- [ ] `writes_attempted` remains `0`
- [ ] No daemon, crawler, auto-edit, or `.github/.customizations.lock` acquisition occurs
- [ ] The audit stays inside existing framework tests and repo-local surfaces

## References

- [`AGENTS.md`](../../../AGENTS.md)
- [`ADR-028`](../../../docs/decisions/ADR-028-instruction-locality-ladder.md) — accepted instruction locality ladder
- `.github/.customizations.lock` declaration from ADR-028; runtime acquisition deferred to slice 9b / issue #209
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`docs/decisions/ADR-007-control-plane-layering-and-packaging.md`](../../../docs/decisions/ADR-007-control-plane-layering-and-packaging.md)
- [`docs/ideas/wiki-curation-agent-framework.md`](../../../docs/ideas/wiki-curation-agent-framework.md)
- Phase 4 classifier/apply work (issues #202–#211; #202–#206 landed, #207–#211 open)
- [`references/locality-ladder.md`](references/locality-ladder.md)
- [`tests/kb/test_framework_references.py`](../../../tests/kb/test_framework_references.py)
- [`tests/kb/test_skill_wrappers.py`](../../../tests/kb/test_skill_wrappers.py)
