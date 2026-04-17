# AGENTS

Repository-level operational rules for maintaining the knowledgebase.

## Mission

Keep wiki content deterministic, provenance-first, and policy-aligned with the canonical spec at `raw/processed/SPEC.md`.

## Repository zones

- `raw/inbox/`: untrusted incoming source material pending ingest.
- `raw/processed/`: immutable post-ingest source artifacts.
- `raw/assets/`: media/binary assets tracked with checksums.
- `wiki/`: curated knowledge pages and audit artifacts.
- `schema/`: page, taxonomy, ontology, metadata, and ingest contracts.
- `scripts/kb/` and `tests/kb/`: implementation and verification surface for knowledgebase tooling.

## Guardrails

1. Fail closed on validation, policy, or lock errors.
2. Restrict writes to repository allowlisted knowledgebase paths.
3. Treat `wiki/log.md` as append-only and record state changes only.
4. Use canonical SourceRef citations: `repo://<owner>/<repo>/<path>@<git_sha>#<anchor>?sha256=<64-hex>`. Authoritative provenance is commit-bound: `git_sha` must resolve to a real git revision that contains the cited raw artifact/path and matching bytes. Ingest-time placeholder git SHAs remain provisional only until that reconciliation happens.
5. Keep wiki frontmatter and companion knowledge-structure contracts aligned with `schema/page-template.md`, `schema/taxonomy-contract.md`, `schema/ontology-entity-contract.md`, and `schema/metadata-schema-contract.md`.
