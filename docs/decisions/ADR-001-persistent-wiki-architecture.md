# ADR-001: Adopt a persistent repository-scoped wiki architecture

## Status
Accepted

## Date
2026-04-12

## Context

The knowledgebase needs cumulative, auditable output that can be reviewed and
improved over time. Query-time-only retrieval would not preserve synthesized
artifacts or operational history in repository state.

The spec requires:

- a durable wiki layer under `wiki/**`,
- explicit source zones under `raw/**`,
- append-only audit behavior for state changes,
- and deterministic scripts/tests around those surfaces.

## Decision

Adopt a persistent repository-scoped wiki model with these structural boundaries:

- `raw/inbox/**` for untrusted incoming sources,
- `raw/processed/**` for immutable post-ingest source artifacts,
- `wiki/**` for generated knowledge artifacts (`sources`, `entities`, `concepts`, `analyses`),
- `wiki/index.md` as deterministic discovery anchor,
- `wiki/log.md` as append-only audit log for state changes.

## Alternatives considered

### Query-time-only RAG (no persistent wiki artifacts)

- **Pros:** lower storage overhead, simpler write surface.
- **Cons:** poor auditability, weak long-term knowledge compounding, less reviewable history.
- **Rejected:** conflicts with repository-first knowledge accumulation goals.

### External knowledge store as primary state

- **Pros:** potentially richer indexing/serving features.
- **Cons:** reduced git-native auditability and higher integration overhead for MVP.
- **Rejected:** MVP requires repository-local, reviewable state as source of truth.

## Consequences

- Wiki artifacts become first-class repository outputs and review surfaces.
- Ingest/index/lint/persist tooling must preserve deterministic behavior.
- Git history and `wiki/log.md` jointly provide operational audit evidence.

## References

- `raw/inbox/SPEC.md` (Objective; Scope; Architecture and Repository Structure; Decision Log)
