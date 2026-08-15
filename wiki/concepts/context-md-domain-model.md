---
type: concept
title: "CONTEXT.md Domain Model"
status: active
sources:
  - "repo://local/knowledgebase/raw/processed/context-md-domain-model.md@021d32778765eb6ba54644c53740f2eb2fb70473#asset?sha256=6495e596a109c6ced0410451ec13de4332a3646b16eb2390899d230334c210bd"
open_questions: []
confidence: 5
sensitivity: internal
updated_at: "2026-08-14T06:00:00Z"
tags:
  - context-md
  - agent-context
  - domain-vocabulary
  - session-continuity
search:
  boost: 2
---

# CONTEXT.md Domain Model

## Summary

`CONTEXT.md` files are machine-readable context artifacts placed at the repo root
and in module directories to capture domain vocabulary, entity relationships,
and project patterns that agents need across sessions. Unlike `AGENTS.md`, which
defines rules and boundaries, `CONTEXT.md` defines vocabulary: what this project
calls things and what invariants apply.

**Problem solved.** Agents discover domain terminology mid-session through
conversation but lose it when the session ends. Each new session re-derives the
same vocabulary through trial and error, wasting tokens and risking inconsistency.
`CONTEXT.md` files persist this vocabulary.

**File format.** Each `CONTEXT.md` uses YAML frontmatter with `scope` and
`last_updated` fields, and exactly three required sections enforced by the
pre-commit hook (`check_context_md_format.py`):

- `## Terms` — a markdown table of term/definition pairs
- `## Invariants` — rules that must never be violated in this domain
- `## File Roles` — what each key file in the scope does

Maximum file size is 200 lines; beyond that the file is split into
directory-scoped files.

**Placement rules.** Files are placed at the most specific applicable scope:

| Location | Scope |
|---|---|
| `/CONTEXT.md` | Repo-wide terminology, cross-cutting patterns, global invariants |
| `scripts/kb/CONTEXT.md` | KB tooling terms (lock semantics, contract types, result codes) |
| `wiki/CONTEXT.md` | Wiki content domain (page types, namespace rules, frontmatter fields) |
| `.github/skills/CONTEXT.md` | Skill framework vocabulary |
| `scripts/github_monitor/CONTEXT.md` | GitHub monitor pipeline terms |
| `scripts/drive_monitor/CONTEXT.md` | Drive monitor pipeline terms |
| `schema/CONTEXT.md` | Schema contract vocabulary |

**Loading precedence.** Most specific scope wins on conflict. The
`context-engineering` skill loads these files at session start.

**Staleness enforcement.** `tests/kb/test_context_md_freshness.py` fails
when ≥ 10 domain commits land after a `CONTEXT.md`'s `last_updated` date,
enforcing that vocabulary stays current.

**Implementation status.** Seven `CONTEXT.md` files landed as of 2026-04-29:
repo-root, `schema/`, `scripts/kb/`, `scripts/github_monitor/`,
`.github/skills/`, `scripts/drive_monitor/`, and `wiki/`.

## Evidence

- `repo://local/knowledgebase/raw/processed/context-md-domain-model.md@021d32778765eb6ba54644c53740f2eb2fb70473#asset?sha256=6495e596a109c6ced0410451ec13de4332a3646b16eb2390899d230334c210bd`:
  Primary source. Defines the problem, file format, placement rules, lifecycle,
  and integration with `context-engineering` skill. All open questions from the
  original proposal resolved as of 2026-04-29.

## Open Questions

None — all design questions resolved at implementation.
