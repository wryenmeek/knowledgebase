# Architecture Decision Records

This directory captures durable architecture and governance decisions derived from
[`raw/processed/SPEC.md`](../../raw/processed/SPEC.md).

## ADR index

| ADR | Title | Status |
|---|---|---|
| [ADR-001](ADR-001-persistent-wiki-architecture.md) | Adopt a persistent repository-scoped wiki architecture | Accepted |
| [ADR-002](ADR-002-frontmatter-and-sourceref-contract.md) | Require frontmatter schema and canonical SourceRef provenance | Accepted |
| [ADR-003](ADR-003-policy-gated-query-persistence.md) | Enforce policy-gated query persistence with machine-readable envelopes | Accepted |
| [ADR-004](ADR-004-split-ci-workflow-governance.md) | Split CI governance into gatekeeper, analyst, and PR-producing workflows | Accepted |
| [ADR-005](ADR-005-write-concurrency-guards.md) | Enforce write concurrency with workflow group and local file lock | Accepted |
| [ADR-006](ADR-006-authoritative-source-boundary.md) | Restrict authoritative ingestion scope to repository-local inputs | Accepted |
| [ADR-007](ADR-007-control-plane-layering-and-packaging.md) | Layer the wiki-curation control plane over deterministic scripts | Accepted |
| [ADR-008](ADR-008-agent-writes-to-framework-paths.md) | Authorize agent write paths for `.github/skills/**` and `docs/**` | Accepted |
| [ADR-009](ADR-009-canonical-identity-and-anchor-management.md) | Canonical identity, slug normalization, and redirect management | Accepted |
| [ADR-010](ADR-010-convert-sources-adr006-compliance-review.md) | ADR-006 compliance review for `convert_sources_to_md.py` | Accepted |
| [ADR-011](ADR-011-canonical-utility-reuse.md) | Canonical utility modules and single-definition rule for shared helpers | Accepted |
| [ADR-012](ADR-012-github-source-monitoring.md) | GitHub source monitoring pipeline | Accepted |
| [ADR-013](ADR-013-rejected-source-registry.md) | Rejected-source registry | Accepted |
| [ADR-014](ADR-014-hitl-afk-work-classification.md) | HITL/AFK work classification for wiki curation | Accepted |
| [ADR-015](ADR-015-extended-ci-trust-model.md) | Extend CI governance with framework-writer (CI-4) and GitHub-monitor (CI-5) | Accepted |
| [ADR-016](ADR-016-pre-commit-hooks-governance.md) | Use raw git hooks (not the pre-commit framework) for local governance checks | Accepted |
| [ADR-017](ADR-017-agent-persona-category-taxonomy.md) | Two-category agent persona taxonomy (kb-workflow / dev-support) | Accepted |
| [ADR-018](ADR-018-context-md-vocabulary-pattern.md) | CONTEXT.md files as structured agent-vocabulary artifacts | Accepted |
| [ADR-019](ADR-019-fleet-jules-orchestration.md) | Jules-based fleet orchestration for parallel issue-to-PR dispatch | Accepted |
| [ADR-020](ADR-020-post-mvp-package-family-criteria.md) | Criteria for approving post-MVP script package families | Accepted |
| [ADR-021](ADR-021-google-drive-source-monitoring.md) | Google Drive source monitoring pipeline | Accepted |
