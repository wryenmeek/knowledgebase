# Knowledgebase Architecture

This document summarizes the implemented architecture and governance model from
[`raw/inbox/SPEC.md`](../raw/inbox/SPEC.md), and points to stable ADRs for key decisions.

## Goals

The system is designed to keep knowledge:

1. **Persistent** (wiki artifacts are stored in-repo, not only generated at query-time).
2. **Traceable** (claims are tied to canonical SourceRef citations).
3. **Deterministic** (policy-driven behavior with explicit failure semantics).
4. **Auditable** (state changes are visible through git history and `wiki/log.md`).

## Repository zones

| Zone | Role | Trust level |
|---|---|---|
| `raw/inbox/**` | New source inputs pending ingest | Untrusted input |
| `raw/processed/**` | Post-ingest source artifacts | Immutable source-of-truth |
| `raw/assets/**` | Vendored external assets | Authoritative only when checksummed |
| `wiki/**` | Synthesized knowledge artifacts | Controlled write surface |
| `schema/**` | Page/ingest contracts | Controlled write surface |
| `scripts/kb/**` + `tests/kb/**` | Automation implementation and verification | Controlled write surface |

## Core workflow

1. Ingest source content from `raw/inbox/**`.
2. Generate/update wiki pages (`wiki/sources/**`, `wiki/entities/**`, `wiki/concepts/**`).
3. Rebuild deterministic index (`wiki/index.md`).
4. Append `wiki/log.md` only when a real state change occurred.
5. Move successfully ingested inputs to `raw/processed/**`.
6. Enforce strict lint and test gates before write-capable automation proceeds.

## Automation model (CI-1..CI-3)

| CI | Responsibility | Write capability |
|---|---|---|
| **CI-1** | Trusted-trigger gatekeeper/handoff | No |
| **CI-2** | Read-only diagnostics and analysis | No |
| **CI-3** | PR-producing write path with allowlists and preflight | Yes (allowlisted paths only) |

This split is intentional: it isolates trust checks, diagnostics, and write operations
so permission scope can stay minimal for each path.

## Write and safety controls

- Canonical write allowlist for automation: `wiki/**`, `wiki/index.md`, `wiki/log.md`, `raw/processed/**`.
- Raw immutability: `raw/processed/**` must not be mutated after ingest.
- Concurrency guard: workflow-level concurrency group plus local lock file (`wiki/.kb_write.lock`).
- Fail-closed behavior: missing prerequisites, permission mismatches, or lock contention stop writes.
- Policy-gated query persistence: write only when `auto_persist_when_high_value` criteria pass.

## Decision records

Key architecture decisions are captured in ADRs:

- [`ADR-001`](decisions/ADR-001-persistent-wiki-architecture.md): persistent repository-scoped wiki model
- [`ADR-002`](decisions/ADR-002-frontmatter-and-sourceref-contract.md): required frontmatter and SourceRef provenance
- [`ADR-003`](decisions/ADR-003-policy-gated-query-persistence.md): deterministic query-persist policy and envelopes
- [`ADR-004`](decisions/ADR-004-split-ci-workflow-governance.md): split CI governance and permission profiles
- [`ADR-005`](decisions/ADR-005-write-concurrency-guards.md): workflow + local lock concurrency model
- [`ADR-006`](decisions/ADR-006-authoritative-source-boundary.md): repository-local authoritative source boundary
