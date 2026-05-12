---
type: concept
title: "Knowledgebase Specification"
status: active
sources:
  - "repo://local/knowledgebase/raw/processed/SPEC.md@498df4202c004c35dc73bd56ca4ef7f8810826db#asset?sha256=19a9dd9be5f70a2113f2728b507bf2828dc34eb7f7a35de07a49b56b4d3417cb"
open_questions: []
confidence: 5
sensitivity: internal
updated_at: "2026-05-12T06:00:00Z"
tags:
  - knowledgebase
  - governance
  - architecture
  - spec
---

# Knowledgebase Specification

## Summary

The knowledgebase specification defines the foundational assumptions, architecture,
and governance model for this repository's persistent wiki pattern. It establishes
the normative precedence order for resolving requirements conflicts, the canonical
terminology used across all tooling, and the MVP and Phase 2 scope boundaries.

The core architectural commitment is a **persistent wiki pattern** rather than
query-time-only RAG: LLMs extract, synthesize, and persist knowledge into durable
markdown artifacts that compound across sessions instead of being discarded after
each query.

Key governance commitments from the spec:

- `AGENTS.md` is the primary schema and contract file for agent behavior.
- `raw/processed/**` is immutable once written — authoritative ingest is
  irreversible.
- Source sensitivity metadata is required in every page's frontmatter.
- Confidence is numeric `1..5` for synthesized wiki content.
- Canonical source citations use the `repo://` SourceRef format with commit-bound
  git SHA and SHA-256 checksum.
- Concurrency control uses workflow `concurrency.group` plus local `fcntl` write
  locks.
- Query persistence default is `auto_persist_when_high_value` with threshold:
  confidence ≥ 4/5, ≥ 2 source references, no unresolved contradiction flag.
- Append-log policy is `log_only_state_changes`.

## Evidence

- `repo://local/knowledgebase/raw/processed/SPEC.md@498df4202c004c35dc73bd56ca4ef7f8810826db#asset?sha256=19a9dd9be5f70a2113f2728b507bf2828dc34eb7f7a35de07a49b56b4d3417cb`:
  Primary source. Defines all assumptions, normative precedence, terminology,
  MVP scope, architecture, and governance contracts enumerated in this page.

## Open Questions

None — this is the authoritative bootstrap specification.
