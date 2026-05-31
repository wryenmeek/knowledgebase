# Wiki curation agent framework

**Status:** Implemented — core agent roster, Phase 3 write surfaces, and Phase 4 analytics all landed (2026-05-14)

> Archived to `raw/inbox/wiki-curation-agent-framework.md` for wiki source intake.
> Full design proposal and implementation notes are in the archived copy.

## Boundary execution surface anchors

To keep framework contract checks aligned with the archived proposal, these
authoritative entrypoints remain listed verbatim:

- `scripts/kb/ingest.py`
- `scripts/kb/update_index.py`
- `scripts/kb/lint_wiki.py`
- `scripts/kb/qmd_preflight.py`
- `scripts/kb/persist_query.py`

## Governance sequencing anchor

The dependency order remains intake -> verification -> policy -> synthesis/query/topology -> maintenance -> analytics.
No durable save, topology mutation, or publication path should open before that governance sequence succeeds.
Route any content-changing audit or review output back through the Knowledgebase Orchestrator for any durable follow-up.

## Skill state anchors

| Current state | Skills |
|---|---|
| **Skills with Python logic wrappers** | `analyze-missed-queries`, `append-log-entry`, `check-link-topology`, `compute-kpis`, `context-engineering`, `documentation-and-adrs`, `enforce-page-template`, `enforce-repository-boundaries`, `extract-entities-and-claims`, `log-intake-rejection`, `manage-redirects-and-anchors`, `run-deterministic-validators`, `suggest-backlinks`, `sync-knowledgebase-state`, `synthesize-concept-page`, `synthesize-entity-page`, `validate-inbox-source`, `validate-wiki-governance`, `write-sourceref-citations` |
| **Skills delegating to repo-level scripts** | `fill-context-pages` -> `scripts/context/fill_context_pages.py`; `generate-maintenance-docs` -> `scripts/maintenance/generate_docs.py` |
| **Active doc-only skills** | `information-architecture-and-taxonomy`, `ontology-and-entity-modeling`, `knowledge-schema-and-metadata-governance`, `entity-resolution-and-canonicalization`, `search-and-discovery-optimization` |
| **Active doc-only workflow skills** | `verify-citations`, `enforce-npov`, `record-open-questions`, `log-policy-conflict`, `review-wiki-plan`, `audit-knowledgebase-workspace` |
