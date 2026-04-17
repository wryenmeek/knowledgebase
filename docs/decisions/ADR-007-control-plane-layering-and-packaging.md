# ADR-007: Layer the wiki-curation control plane over deterministic scripts

## Status
Accepted

## Date
2026-04-16

## Context

`docs/ideas/wiki-curation-agent-framework.md` proposes a substantial control
plane for wiki curation: agent personas, skills, wrapper logic, validators, and
future script ports. Without a ratified boundary, that proposal can sprawl into
simultaneously:

- scaffolding the control plane,
- porting broad cross-repository script backlogs,
- and replacing the repository's existing deterministic `scripts/kb/**`
  execution layer.

The repository already treats `scripts/kb/**` and `tests/kb/**` as the
implementation and verification surface for knowledgebase tooling, and
`AGENTS.md` requires deterministic, provenance-first, fail-closed behavior.

## Decision

Implement the wiki-curation framework as an MVP control plane layered over the
existing deterministic Python tooling.

### Accepted control-plane layering

1. **Global policy** lives in `AGENTS.md` and existing ADRs.
2. **Agent personas** live in `.github/agents/**` and define mission, handoff,
   and stop-condition contracts.
3. **Skill workflows and thin wrappers** live in `.github/skills/**` and may
   include small `logic/` helpers that invoke deterministic tooling.
4. **Authoritative execution** remains in `scripts/kb/**`.
5. **Verification** remains in `tests/kb/**`.

### MVP scope

The framework MVP includes:

- agent and skill scaffolding,
- workflow documentation and references,
- and thin wrappers around existing `scripts/kb/ingest.py`,
  `scripts/kb/update_index.py`, `scripts/kb/lint_wiki.py`,
  `scripts/kb/qmd_preflight.py`, and `scripts/kb/persist_query.py`.

### Deferred beyond MVP

The framework MVP does **not** include:

- porting the broader cross-repository script backlog into new `scripts/**`
  trees,
- replacing `scripts/kb/**` with agent-native or skill-local implementations,
- or mixing heavyweight repository crawlers, report generators, snapshots, or
  external-service integrations into the initial scaffolding milestone.

## Alternatives considered

### Port the full script backlog as part of MVP

- **Pros:** more automation lands immediately.
- **Cons:** mixes framework scaffolding with large new execution surfaces and
  obscures what is actually required to make the control plane real.
- **Rejected:** MVP should establish boundaries first, then add broader script
  ports deliberately.

### Put most operational logic directly in personas or skill prose

- **Pros:** fewer files at the start.
- **Cons:** weak testability, poor reuse, and higher risk of policy drift across
  agents.
- **Rejected:** personas should stay concise and skills should stay procedural;
  deterministic behavior belongs in scripts and tests.

### Replace the current `scripts/kb/**` entrypoints during framework rollout

- **Pros:** one consolidated implementation surface.
- **Cons:** risks regressions in already-deterministic flows and violates the
  repository's current execution contract.
- **Rejected:** the MVP must preserve existing Python entrypoints as the
  authoritative execution layer.

## Consequences

- Framework implementation work can stay scoped to concrete control-plane
  scaffolding.
- Operators still use the existing `scripts/kb/**` commands while the framework
  is being added.
- Future script ports must be documented as later work and should not be mixed
  into MVP by default.
- Packaging decisions now have a stable home in architecture docs and ADRs.

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/ideas/wiki-curation-agent-framework.md`
