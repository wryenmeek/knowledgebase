# ADR-009: Canonical identity and durable anchor management for wiki pages

## Status
Accepted

## Date
2026-04-19

## Context

As the wiki grows, page addresses become dependencies. Other pages link to them,
query results cite them, and source attribution references embed them. Without a
canonical slug assignment rule and a governed redirect mechanism, renaming or
reorganizing pages silently breaks these references.

Phase 3 (G4c) promotes the `manage-redirects-and-anchors` skill from a doc-only
placeholder to an executable surface with a `logic/` directory. Before that
promotion can land, the repository needs a ratified identity contract that
specifies:

1. How canonical slugs (page identifiers) are derived from page metadata.
2. How redirects are recorded when a slug changes.
3. Which script or skill is authoritative for anchor updates.
4. What schema governs the redirect record file.

## Decision

### Slug derivation rules

- The canonical slug for a wiki page is derived from its `title` frontmatter
  field using the following normalization:
  1. Convert to lowercase.
  2. Replace spaces and underscores with hyphens.
  3. Strip all characters that are not alphanumeric or hyphens.
  4. Collapse consecutive hyphens to a single hyphen.
  5. Strip leading and trailing hyphens.
- Example: `"Medicare Advantage Part C"` → `medicare-advantage-part-c`.
- Slugs must be unique within `wiki/`. A duplicate slug is a hard error.
- The file name of a wiki page must match its slug: `wiki/<slug>.md`.

### Anchor assignment

- Anchors within a page (`#section-heading`) are derived from section headings
  using the same normalization as slug derivation.
- Anchors are considered durable once a page has been referenced by an external
  citation (SourceRef). Changing a durable anchor requires a redirect entry.
- Intra-wiki links may use either the file path form (`../other-page.md`) or
  the slug form (`other-page`) — both resolve identically.

### Redirect record schema

Redirects are recorded in `wiki/redirects.md` as an append-only Markdown table:

```markdown
| old_slug | new_slug | redirected_at | reason |
|----------|----------|----------------|--------|
| example-old | example-new | 2026-04-19 | page renamed |
```

- `old_slug`: the previous canonical slug (no `.md` extension).
- `new_slug`: the current canonical slug, or `REMOVED` if the page was
  deleted without a replacement.
- `redirected_at`: ISO 8601 date of the redirect record creation.
- `reason`: a short human-readable description.
- The table is append-only: existing rows must not be modified or deleted.
- `wiki/redirects.md` is a governed artifact; see `schema/governed-artifact-contract.md`.

### Authoritativeness

- `topology-librarian` (via the `manage-redirects-and-anchors` skill) is the
  sole authoritative surface for writing to `wiki/redirects.md`.
- Slug changes that originate from maintainer edits must be followed by a
  `manage-redirects-and-anchors` invocation to record the redirect.
- No other script or skill may write to `wiki/redirects.md` directly.

### Lock requirements

- Writes to `wiki/redirects.md` must acquire `wiki/.kb_write.lock` via the
  shared `exclusive_write_lock` utility before appending.
- Approval gate: `--approval approved` is required.

## Alternatives considered

### Store redirects in a JSON or YAML file

- **Rejected for MVP:** Markdown table is human-readable, diff-friendly, and
  consistent with the existing wiki frontmatter conventions. A machine-readable
  format (JSON/YAML) can be added as a derived artifact if tooling demands it.

### Allow any wiki-writing skill to update redirects

- **Rejected:** Centralizing redirect authorship in topology-librarian keeps the
  governance surface narrow and makes redirect records auditable.

### Derive slugs from file names rather than title frontmatter

- **Rejected:** File names can be changed without updating frontmatter, breaking
  the identity contract. Title-derived slugs make the canonical identifier explicit
  and independent of the file system path.

## Consequences

- All wiki pages must have unique, normalized slugs matching their file names.
- Slug changes require a redirect record in `wiki/redirects.md`.
- `wiki/redirects.md` is governed by topology-librarian and inherits the
  append-only write concurrency model.
- `manage-redirects-and-anchors` skill can now be promoted to an executable
  surface (G4c) with a `logic/` dir and AGENTS.md row.

## References

- `AGENTS.md` (write-surface matrix; `manage-redirects-and-anchors` row)
- `ADR-005-write-concurrency-guards.md`
- `schema/governed-artifact-contract.md`
- `schema/taxonomy-contract.md`
- `.github/skills/manage-redirects-and-anchors/SKILL.md`
- `.github/agents/topology-librarian.md`
