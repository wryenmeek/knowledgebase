---
name: audit-knowledgebase-workspace
description: Audits the framework workspace for reference drift, stale commands, and attached-tool resolution gaps. Use when verifying that skills, agents, tests, and thin wrappers still point at real repo-local surfaces.
---

# Audit Knowledgebase Workspace

## Overview

Use this skill to self-audit the framework layer itself as the skill and agent
surface grows. In MVP it is a doc-only workflow focused on reference drift,
documented-command validity, wrapper allowlist integrity, and attached-tool
resolution using existing repository checks rather than a new crawler runtime.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Audit and handoff only. Do not self-heal by editing
  files automatically, spawn a broad crawler, or create a second audit runtime.

## When to Use

- Framework skills, agents, prompts, or tests changed together
- A plan or PR may have introduced broken references or stale commands
- Attached wrapper allowlists or tool-resolution paths may have drifted
- You need a deterministic audit of repo-local framework surfaces before merge
- Orphaned but useful framework assets need governed follow-up rather than silent
  deletion

## Contract

- Input: the current framework workspace or a scoped set of changed framework
  files
- Audit targets: skill docs, agent docs, framework tests, and attached thin
  wrapper references
- Output: a pass/fail audit summary with broken references, stale commands,
  unresolved attached tools, and recommended governed follow-up
- Handoff rule: failures route to the owning skill/plan review surface; useful
  orphaned assets route to governed integration planning instead of ad hoc fixes

## Assertions

- Repo-local references and commands must resolve deterministically
- Attached-tool and wrapper allowlist paths must point to real repo-local files
- The audit fails closed on missing framework dependencies
- The skill uses existing tests and documentation surfaces instead of inventing a
  second runtime
- Self-healing is deferred until a later explicitly governed phase

## Procedure

### Step 1: Audit reference integrity

Review skill and agent docs for repo-local links, command examples, and cited
framework files that no longer resolve.

### Step 2: Audit attached-tool resolution

Check wrapper allowlist paths, documented validator entrypoints, and other
attached-tool references for real repo-local targets.

### Step 3: Audit drift and orphan risk

Flag stale commands, broken references, or orphaned-but-useful framework assets
that should be integrated or retired through a governed plan.

### Step 4: Route follow-up

Send failures to the relevant owning skill or `review-wiki-plan`; route broader
integration work back through governed planning instead of fixing it invisibly.

## Commands

```bash
python3 -m unittest tests.kb.test_framework_references tests.kb.test_skill_wrappers
python3 -m unittest tests.kb.test_framework_contracts tests.kb.test_framework_skills tests.kb.test_framework_agents
```

## Boundaries

- Do not create a daemon, webhook mesh, or broad repo crawler for this audit in MVP
- Do not auto-edit files as part of the audit result
- Do not treat missing references or unresolved attached tools as advisory when
  they break framework execution or review
- Do not expand beyond repo-local framework surfaces without a separate governed
  decision

## Verification

- [ ] Repo-local references and commands resolve
- [ ] Attached-tool and wrapper paths resolve to real files
- [ ] Drift findings distinguish blocking failures from follow-up opportunities
- [ ] Orphaned assets are routed to governed planning instead of silently removed
- [ ] The audit stays inside existing framework tests and repo-local surfaces

## References

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`docs/decisions/ADR-007-control-plane-layering-and-packaging.md`](../../../docs/decisions/ADR-007-control-plane-layering-and-packaging.md)
- [`docs/ideas/wiki-curation-agent-framework.md`](../../../docs/ideas/wiki-curation-agent-framework.md)
- [`tests/kb/test_framework_references.py`](../../../tests/kb/test_framework_references.py)
- [`tests/kb/test_skill_wrappers.py`](../../../tests/kb/test_skill_wrappers.py)
