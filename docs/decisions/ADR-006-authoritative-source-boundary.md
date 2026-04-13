# ADR-006: Restrict authoritative ingestion scope to repository-local inputs

## Status
Accepted

## Date
2026-04-12

## Context

The MVP must prevent uncontrolled corpus expansion and preserve provenance
quality. Unbounded external input ingestion introduces trust and verification
risks that are difficult to audit.

## Decision

Define authoritative source scope as:

- repository-local sources under `raw/inbox/**`,
- checksummed external assets vendored under `raw/assets/**`.

Treat all non-vendored or non-checksummed external material as citation-only
context in MVP (not authoritative ingest input).

## Alternatives considered

### Allow arbitrary external URLs/files as authoritative inputs

- **Pros:** broader source coverage with less prep work.
- **Cons:** weak provenance guarantees and larger abuse surface.
- **Rejected:** violates deterministic trust-boundary requirements.

### Disallow all external assets

- **Pros:** simplest trust model.
- **Cons:** blocks valid asset-backed evidence use cases needed in practice.
- **Rejected:** too restrictive for expected knowledgebase workflows.

## Consequences

- Corpus scope remains bounded and auditable.
- External assets can still be used authoritatively when vendored and checksummed.
- Tooling and tests must enforce checksum and path-boundary rules.

## References

- `raw/inbox/SPEC.md` (Assumptions and Defaults; Scope; Canonical sources format; Security and Trust Model; Threat model mapping)
