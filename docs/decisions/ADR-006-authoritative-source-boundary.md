# ADR-006: Restrict authoritative ingestion scope to repository-local inputs

## Status
Accepted — extended by ADR-021: Google Drive sources added `raw/drive-sources/` and `raw/assets/gdrive/` paths

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

> **Extension (ADR-021):** Google Drive source monitoring added two additional
> authoritative paths: `raw/assets/gdrive/**` (versioned Drive asset storage) and
> `raw/drive-sources/**` (mutable registry files tracking Drive file state). Both
> paths follow the same checksum and provenance requirements as the original
> `raw/assets/**` boundary.

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

- `raw/processed/SPEC.md` (Assumptions and Defaults; Scope; Canonical sources format; Security and Trust Model; Threat model mapping)
- `ADR-021-google-drive-source-monitoring.md` — extends source boundary with `raw/drive-sources/` and `raw/assets/gdrive/`
