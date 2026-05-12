---
type: concept
title: "Wiki Quality Best Practices"
status: active
sources:
  - "repo://local/knowledgebase/raw/processed/LLMwiki-best practices-research.md@021d32778765eb6ba54644c53740f2eb2fb70473#asset?sha256=be1da73fb59773dfa81d34ef85d0654fb80a8ce53a0affa7eda3b145061cefb9"
open_questions:
  - "External citations [1]–[13] referenced in the source are not independently verifiable through the repository's SourceRef provenance chain. Claims from those citations are attributed to the source document only."
confidence: 3
sensitivity: internal
updated_at: "2026-05-12T06:00:00Z"
tags:
  - wiki-architecture
  - llm-wiki
  - best-practices
  - information-architecture
search:
  boost: 2
---

# Wiki Quality Best Practices

## Summary

A research survey documents architectural patterns for autonomous LLM-edited wikis,
drawing on practices from large-scale collaborative environments and emerging
agentic AI frameworks. The source documents several recurring themes applied to
the design of this repository.

**Persistent compounding artifact pattern.** The source describes an approach
in which an LLM acts as a structured middle layer between human users and raw
source materials. Rather than retrieving fragments at query time and discarding
context afterward, the system extracts and synthesizes knowledge once, writing
output to a permanent collection of interlinked markdown files that it continuously
maintains. This repository implements this pattern via the `raw/` → `wiki/` pipeline.

**Tripartite knowledge model.** The source documents a three-layer structure:
(1) an immutable raw sources layer that agents read but never modify, (2) a wiki
layer of LLM-owned synthesized markdown files, and (3) a schema layer that
constrains agent behavior. This maps directly to this repository's `raw/processed/**`,
`wiki/**`, and `schema/**` zones.

**Namespace segregation.** The source notes that historical large-scale wikis
use namespace systems to separate article content from administrative content,
and that autonomous LLM wikis enforce equivalent separation through directory
structures defined in schema files. This repository implements this via the
`wiki/entities/`, `wiki/concepts/`, `wiki/analyses/`, and `wiki/sources/`
namespace contract in `schema/taxonomy-contract.md`.

**Frontmatter schemas.** The source describes the use of structured YAML
frontmatter on every generated file to support programmatic querying, with
fields for title, category, confidence score, and operational status. This
repository implements this pattern via `schema/metadata-schema-contract.md`.

**AGENTS.md as global schema.** The source describes `AGENTS.md` as a
machine-readable project-level schema that dictates global agent behavior,
repository expectations, and architectural boundaries. This repository uses
`AGENTS.md` as its primary governance contract.

**Note on source citations.** The research document references external sources
via inline markers `[1]`–`[13]`. These citations are internal to the source
document; they cannot be independently verified through this repository's
SourceRef provenance chain. Claims above are attributed to the source document's
framing, not to the underlying external references directly.

## Evidence

- `repo://local/knowledgebase/raw/processed/LLMwiki-best practices-research.md@021d32778765eb6ba54644c53740f2eb2fb70473#asset?sha256=be1da73fb59773dfa81d34ef85d0654fb80a8ce53a0affa7eda3b145061cefb9`:
  Primary source. Describes the tripartite model, namespace segregation,
  frontmatter schemas, AGENTS.md pattern, and compounding artifact architecture.
  External citations [1]–[13] referenced in the source are not resolvable through
  this repository's provenance system.

## Open Questions

- External citations [1]–[13] in the source document are not independently
  verifiable through this repository's SourceRef chain. If authoritative sourcing
  for specific claims is needed, the original bibliography must be located and
  registered as separate intake sources.
