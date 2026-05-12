# ADR-002: Require frontmatter schema and canonical SourceRef provenance

## Status
Accepted

## Date
2026-04-12

## Context

Generated wiki content must remain verifiable and safe for future automation.
Without strict metadata and provenance rules, claims become hard to audit and
sensitivity handling can drift.

The spec defines mandatory frontmatter fields and a canonical SourceRef format:

`repo://<owner>/<repo>/<path>@<git_sha>#<anchor>?sha256=<64-hex>`

## Decision

Require all generated wiki pages to include the frontmatter contract from the spec,
including `type`, `status`, `sources`, `open_questions`, `confidence`,
`sensitivity`, `updated_at`, and `tags`.

Require `sources` entries to be canonical SourceRef values with:

1. an anchor (`#Lx-Ly` or `#asset`),
2. a `sha256` checksum,
3. repository-relative paths scoped to `raw/inbox/**`, `raw/processed/**`, or `raw/assets/**`.

## Alternatives considered

### Looser metadata with optional fields

- **Pros:** lower authoring overhead.
- **Cons:** weaker validation, inconsistent policy enforcement, poorer downstream automation reliability.
- **Rejected:** conflicts with deterministic ingest/lint and traceability requirements.

### Path-only citations without checksum

- **Pros:** simpler citation strings.
- **Cons:** cannot detect content drift; provenance becomes ambiguous across revisions.
- **Rejected:** checksum is required for reliable integrity guarantees.

## Consequences

- Ingest/lint tooling must validate frontmatter completeness and SourceRef shape.
- Provenance checks become deterministic and testable.
- Sensitive-content classification is explicit and machine-checkable.

## References

- `raw/processed/SPEC.md` (Assumptions and Defaults; Terminology; Frontmatter Contract; Security and Trust Model)
