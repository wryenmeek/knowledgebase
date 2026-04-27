# ADR-018: CONTEXT.md files as structured agent-vocabulary artifacts

## Status
Accepted

## Date
2026-04-27

## Context

Agents working in this repository re-derive the same domain vocabulary each
session through trial and error — terms like `SourceRef`, `governed artifact`,
`fail closed`, `intake package`, `KB_WRITE_LOCK`, and `AFK` are specific to
this codebase and not covered by general pre-training. The `context-engineering`
skill loads context at session start, but it loaded only prose documentation,
not structured vocabulary that tooling could validate or query.

Two existing approaches were insufficient:

1. **`AGENTS.md` guardrails** — authoritative for rules but written for humans;
   not structured for agent term-lookup or cross-reference.
2. **`docs/architecture.md` and ADRs** — narrative documentation; agents must
   read many pages to extract a single term definition.

A structured vocabulary artifact that is: (a) scoped to the relevant directory,
(b) machine-parseable as well as human-readable, and (c) append-able by agents
during a session without risk of corrupting authoritative rules.

## Decision

Introduce `CONTEXT.md` files as structured agent-vocabulary artifacts with a
defined schema and placement hierarchy.

### Format

Each `CONTEXT.md` file carries a YAML frontmatter block followed by four
markdown-table sections:

```
---
scope: repo | directory | module
last_updated: YYYY-MM-DD
---

## Terms       — name → definition pairs
## Entities    — entity name, description, related-to
## Patterns    — pattern name, description, example files
## Invariants  — prose rules that hold across this scope
```

Markdown tables were chosen over pure YAML for two reasons:
- Human-readable in GitHub diffs and pull request reviews
- Consistent with the repository's existing documentation style

The frontmatter `scope` field and table section headers are validated by
`scripts/hooks/check_context_md_format.py` on commit.

### Placement hierarchy

| Location | Scope | Purpose |
|---|---|---|
| `/CONTEXT.md` | Repo-wide | Project-level terminology, cross-cutting patterns, global invariants |
| `schema/CONTEXT.md` | Module | Schema file naming conventions and contract types |
| `scripts/kb/CONTEXT.md` | Module | KB tooling terms (lock semantics, result codes, surface contracts) |
| `scripts/github_monitor/CONTEXT.md` | Module | GitHub monitoring terms (drift report, registry entry, fetch/synthesize) |
| `.github/skills/CONTEXT.md` | Module | Skill-layer vocabulary (phase gates, routing, artifact types) |

More specific scopes override less specific scopes on term conflicts.

### Ownership

`CONTEXT.md` files are human-maintained with human + agent hybrid update
semantics:
- Agents may append new terms, entities, or patterns discovered mid-session.
- All changes go through normal PR review.
- The file is not append-only at the git level (terms can be corrected), but
  the intent is additive.

### Integration

- `context-engineering` skill loads `CONTEXT.md` files from the repo root and
  any relevant subdirectory as part of session context setup.
- `fill-context-pages` skill can scan `CONTEXT.md` for `[context-needed]`
  markers and fill them from agent knowledge.
- `AGENTS.md` rules take precedence over any `CONTEXT.md` vocabulary entry
  if they conflict.

## Alternatives Considered

### Pure YAML vocabulary file (`vocab.yaml`)

- **Pros:** Machine-parseable without a markdown table parser; standard format.
- **Cons:** Not human-readable in GitHub diffs; inconsistent with the
  repository's markdown-first documentation style; YAML is fragile to hand-edit.
- **Rejected:** Markdown tables meet parsing needs while remaining diff-friendly.

### Centralized single vocabulary file

- **Pros:** One place to look; no hierarchy to navigate.
- **Cons:** Conflates repo-wide terms with module-specific jargon; grows
  without bound; requires every editor to understand the full codebase to
  contribute.
- **Rejected:** Directory-scoped files keep vocabulary close to the code it
  describes and allow per-module ownership.

### Extend `AGENTS.md` with a vocabulary section

- **Pros:** Single authoritative file for agent context.
- **Cons:** `AGENTS.md` is a rules document, not a vocabulary document;
  mixing concerns makes both harder to maintain; agents would need to parse
  a very large file to extract a term definition.
- **Rejected:** Separation of concerns — `AGENTS.md` defines rules, `CONTEXT.md`
  defines vocabulary.

### No structured vocabulary (status quo)

- **Pros:** Zero implementation cost.
- **Cons:** Agents re-derive vocabulary every session; inconsistency risk;
  onboarding cost for new contributors and agents.
- **Rejected:** Token waste and inconsistency cost is real and measurable.

## Consequences

- `CONTEXT.md` files must never contain normative rules (those belong in
  `AGENTS.md`). The file header explicitly states it is descriptive.
- The `check_context_md_format.py` hook validates frontmatter and section
  structure on commit; missing required sections fail the hook.
- File size is soft-capped at ~200 lines; beyond that, split into more
  directory-scoped files.
- Terms not referenced in any source file for >90 days may be flagged for
  review by `freshness-audit` skill if extended to cover `CONTEXT.md` files.

## References

- `CONTEXT.md` — repo-root vocabulary file
- `schema/CONTEXT.md`, `scripts/kb/CONTEXT.md`, `scripts/github_monitor/CONTEXT.md`, `.github/skills/CONTEXT.md`
- `scripts/hooks/check_context_md_format.py` — format validator
- `.github/skills/context-engineering/SKILL.md` — context loading hierarchy
- `docs/ideas/context-md-domain-model.md` — original design proposal
- `AGENTS.md` § Guardrails — rules take precedence over CONTEXT.md vocabulary
