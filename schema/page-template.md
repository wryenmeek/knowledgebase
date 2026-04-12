# Wiki Page Template

Use this contract for pages in `wiki/sources/`, `wiki/entities/`, `wiki/concepts/`, and `wiki/analyses/`.

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
