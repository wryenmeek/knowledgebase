# Architecture Decision Records

This directory captures durable architecture and governance decisions derived from
[`raw/inbox/SPEC.md`](../../raw/inbox/SPEC.md).

## ADR index

| ADR | Title | Status |
|---|---|---|
| [ADR-001](ADR-001-persistent-wiki-architecture.md) | Adopt a persistent repository-scoped wiki architecture | Accepted |
| [ADR-002](ADR-002-frontmatter-and-sourceref-contract.md) | Require frontmatter schema and canonical SourceRef provenance | Accepted |
| [ADR-003](ADR-003-policy-gated-query-persistence.md) | Enforce policy-gated query persistence with machine-readable envelopes | Accepted |
| [ADR-004](ADR-004-split-ci-workflow-governance.md) | Split CI governance into gatekeeper, analyst, and PR-producing workflows | Accepted |
| [ADR-005](ADR-005-write-concurrency-guards.md) | Enforce write concurrency with workflow group and local file lock | Accepted |
| [ADR-006](ADR-006-authoritative-source-boundary.md) | Restrict authoritative ingestion scope to repository-local inputs | Accepted |
