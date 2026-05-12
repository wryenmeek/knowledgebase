# ADR-007: Layer the wiki-curation control plane over deterministic scripts

## Status
Accepted

## Date
2026-04-16

## Historical note

When accepted on 2026-04-16, ADR-007 defined an MVP-only package boundary
limited to `.github/agents/**`, `.github/skills/**`, `scripts/kb/**`, and
`tests/kb/**`. This amendment keeps that boundary as the statement of what is
currently landed and additionally approves post-MVP package surfaces at
`scripts/validation/**`, `scripts/reporting/**`, `scripts/context/**`,
`scripts/maintenance/**`, and `scripts/ingest/**`. It does **not** change the
CI-1/CI-2/CI-3 permission split from ADR-004, the workflow-plus-lock
concurrency model from ADR-005, the authoritative source boundary from
ADR-006, or deny-by-default behavior for undeclared write paths.

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

Follow-on planning now needs ratified package locations for validators,
maintenance utilities, context-sync tooling, reporting, and ingest helpers
without implying that those paths are current runtime entrypoints or blanket
write-authorized surfaces.

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
- and thin wrappers around existing `scripts/kb/**` entrypoints where they are
  narrow, deterministic, and justified by the MVP boundary. At present, the
  landed wrappers cover governance validation and index/state synchronization,
  while `scripts/kb/ingest.py`, `scripts/kb/update_index.py`,
  `scripts/kb/lint_wiki.py`, `scripts/kb/qmd_preflight.py`, and
  `scripts/kb/persist_query.py` remain the authoritative deterministic
  execution surface, with ingest and query persistence still used directly as
  operator/runtime entrypoints.

### Deferred beyond MVP

The framework MVP does **not** include:

- porting the broader cross-repository script backlog into new `scripts/**`
  trees,
- replacing `scripts/kb/**` with agent-native or skill-local implementations,
- or mixing heavyweight repository crawlers, report generators, snapshots, or
  external-service integrations into the initial scaffolding milestone.

### Approved post-MVP package surfaces

The repository boundary is widened for post-MVP implementation work at:

- `scripts/validation/**` for deterministic validators, freshness checks, and
  baseline/snapshot utilities,
- `scripts/reporting/**` for repository-scoped reporting,
- `scripts/context/**` and `scripts/maintenance/**` for context-sync and
  maintenance orchestration invoked by thin skills,
- `scripts/ingest/**` for heavyweight repository-local ingest/conversion
  helpers.

These are approved packaging locations, not blanket runtime write
authorization. `scripts/kb/ingest.py`, `scripts/kb/update_index.py`,
`scripts/kb/lint_wiki.py`, `scripts/kb/qmd_preflight.py`, and
`scripts/kb/persist_query.py` remain the authoritative deterministic execution
surface for the currently landed system.

### Preserved invariants

- ADR-004 permission expectations remain intact: CI-1 and CI-2 stay read-only,
  and CI-3 remains the only PR-producing write-capable path with explicit
  allowlists and preflight.
- ADR-005 still governs shared-artifact writes: post-MVP writers that touch
  `wiki/index.md`, `wiki/log.md`, or generated pages must keep the workflow
  concurrency group plus `wiki/.kb_write.lock`.
- ADR-006 still governs source authority: authoritative ingest remains limited
  to repository-local `raw/inbox/**` inputs and checksummed `raw/assets/**`.
- Paths outside the current MVP surfaces plus the approved post-MVP package
  surfaces remain deny-by-default unless a narrower contract explicitly names
  them.

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
- Future script ports now have approved package locations, but each new
  runtime-capable entrypoint must still document its narrower write scope and
  preserve existing governance invariants.
- Packaging decisions now have a stable home in architecture docs and ADRs.

## References

- `AGENTS.md`
- `docs/architecture.md`
- `docs/ideas/wiki-curation-agent-framework.md`
