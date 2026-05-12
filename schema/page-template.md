# Wiki Page Template

Use this contract for pages in `wiki/sources/`, `wiki/entities/`, `wiki/concepts/`, and `wiki/analyses/`, plus reserved root-level process pages such as `wiki/index.md`, `wiki/log.md`, `wiki/open-questions.md`, `wiki/backlog.md`, and `wiki/status.md`.

Companion authoritative contracts:

- [`taxonomy-contract.md`](taxonomy-contract.md)
- [`ontology-entity-contract.md`](ontology-entity-contract.md)
- [`metadata-schema-contract.md`](metadata-schema-contract.md)
- [`governed-artifact-contract.md`](governed-artifact-contract.md)

```md
---
type: entity # entity | concept | source | analysis | process
title: "<canonical-title>"
status: active # active | superseded | archived
sources:
  - repo://<owner>/<repo>/<path>@<git_sha>#<anchor>?sha256=<64-hex>
open_questions:
  - "<question requiring arbitration or more evidence>"
confidence: 1 # integer 1..5
sensitivity: public # public | internal | restricted
updated_at: "YYYY-MM-DDTHH:MM:SSZ"
tags:
  - "<normalized-tag>"
---

# <canonical-title>

## Summary
<brief synthesis>

## Evidence
- <SourceRef>: <what this evidence supports>

## Open Questions
- <unresolved contradiction or follow-up>
```

Required frontmatter keys above remain the blocking baseline used by current
deterministic tooling.

Optional extension keys may be added when needed and must follow the companion
contracts:

- `browse_path`: ordered taxonomy segments excluding namespace and page title
- `aliases`: normalized alternate names for the page subject
- `entity_id`: stable identity key for entity pages once ratified
- `schema_version`: explicit schema version when a page opts into a newer schema

Optional body sections:

- `## Aliases`
- `## Relationships`
