---
type: template
title: "Locality 4 Justification Trailer"
status: active
updated_at: "2026-06-10"
owner: ".github/skills/audit-knowledgebase-workspace"
---

# Locality 4 Justification Trailer Template

Use this commit trailer only when an instruction must remain Locality 4
(always-on) and no paired deletion candidate exists.

## Format

```text
Locality-4-Justification: <one-line reason explaining why this rule must be Locality 4>
```

The reason must fit on one line and explain why a lower-locality destination
cannot carry the rule. Trailer use counts against the soft budget defined by
ADR-028 (pending): by default, one trailer per ten commits touching global
rules sections, until a paired deletion lands.

## Example

```text
Locality-4-Justification: keep this rule always-on because it prevents unsafe cross-worktree edits before any skill can load
```
