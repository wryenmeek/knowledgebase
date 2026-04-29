# Design Proposal: CONTEXT.md Domain Model Pattern

**Status:** Implemented — 2026-04-27
**Date:** 2025-07-18
**Author:** Design research (Phase 7-A)

> **Implementation note (2026-04-27, updated 2026-04-29):** Five CONTEXT.md files
> have landed: `./CONTEXT.md` (repo-root), `schema/CONTEXT.md`,
> `scripts/kb/CONTEXT.md`, `scripts/github_monitor/CONTEXT.md`, and
> `.github/skills/CONTEXT.md`. A sixth, `scripts/drive_monitor/CONTEXT.md`, was
> added with the Drive monitor pipeline. Note: `wiki/CONTEXT.md` listed in §4's
> placement rules was **not** created — wiki content domain vocabulary has not
> been captured in a dedicated CONTEXT.md file yet. The `context-engineering`
> skill loads the existing files. Open questions from §7 were resolved: markdown
> tables (not pure YAML) won; human+agent hybrid ownership with PR review;
> line-count cap enforced informally; no conflict with `copilot-instructions.md`
> (files complement, not replace, each other).

## Remaining Remediation Items

> Items found during 2026-04-29 verification review.

1. **context-engineering auto-loading claim overstated** — The implementation
   note says "The `context-engineering` skill loads the existing files" but the
   skill's SKILL.md only provides manual loading guidance in its context
   hierarchy (Level 1b). No logic file in the skill automatically discovers or
   loads CONTEXT.md files. **Action:** Either update the implementation note to
   say "provides manual loading guidance" or implement actual auto-loading logic
   in the context-engineering skill.

2. **`wiki/CONTEXT.md` not created** — §4 placement rules list
   `wiki/CONTEXT.md` for wiki content domain vocabulary. The implementation note
   acknowledges this gap. Low priority — the pattern is established in 6 other
   locations; wiki content domain vocabulary has not been captured yet.

3. **`fill-context-pages` integration not implemented** — §6 proposed that the
   `fill-context-pages` skill "could scan CONTEXT.md for `[context-needed]`
   markers." This integration does not exist; the skill currently scans only
   `.github/skills/**`, `docs/**`, and `schema/**`. Low priority — the proposal
   used conditional "could" language.

---

## 1. Problem

During coding sessions, agents discover domain terminology, entity relationships,
and project vocabulary through conversation. Examples:

- "SourceRef" means a canonical citation URI with commit-bound provenance
- "governed artifact" means a wiki file managed through the write-surface matrix
- "fail closed" means abort on any validation/policy/lock error — never degrade silently
- "intake package" is the sealed manifest evidence-verifier needs before synthesis

This knowledge is lost between sessions. The `context-engineering` skill loads
context files at session start, but it doesn't capture *new* terminology
discovered mid-session. Each new session re-derives the same vocabulary through
trial and error — wasting tokens and risking inconsistency.

## 2. Proposed Solution

Introduce `CONTEXT.md` files that capture domain model elements inline during
development sessions. These files are human-readable markdown with structured
sections that agents can both read and append to.

A `CONTEXT.md` is **not** documentation — it's a machine-readable context
artifact optimized for agent consumption. It answers: "What does this project
(or module) call things, and what rules apply?"

## 3. File Format

```markdown
---
scope: repo          # repo | directory | module
last_updated: 2025-07-18
---

# CONTEXT

## Terms

| Term | Definition |
|------|-----------|
| SourceRef | Canonical citation URI: `repo://<owner>/<repo>/<path>@<git_sha>#<anchor>?sha256=<64-hex>` |
| governed artifact | A wiki file managed through the write-surface matrix in AGENTS.md |
| fail closed | Abort on any validation, policy, or lock error — never degrade silently |

## Entities

| Entity | Description | Related To |
|--------|------------|------------|
| wiki page | Curated knowledge page in `wiki/` following `schema/page-template.md` | governed artifact, SourceRef |
| intake package | Sealed manifest with provenance, checksums, source-type metadata | evidence-verifier, policy-arbiter |

## Patterns

| Pattern | Description | Example Files |
|---------|------------|---------------|
| write-lock-then-act | Acquire `wiki/.kb_write.lock` before any mutation | `scripts/kb/write_utils.py` |
| path bounds check | `Path.is_relative_to(wiki_root.resolve())` — never string prefix | `scripts/kb/write_utils.py` |

## Invariants

- `wiki/log.md` is append-only; never rewrite or truncate.
- `raw/processed/**` is immutable after ingest; never modify post-write.
- Lock files (`.lock`) must never be committed to git.
- Every write surface must have a row in the AGENTS.md write-surface matrix.
```

## 4. Placement Rules

| Location | Scope | Purpose |
|----------|-------|---------|
| `/CONTEXT.md` | Repo-wide | Project-level terminology, cross-cutting patterns, global invariants |
| `scripts/kb/CONTEXT.md` | Module | KB tooling-specific terms (lock semantics, contract types, result codes) |
| `wiki/CONTEXT.md` | Module | Wiki content domain (page types, namespace rules, frontmatter fields) |
| `.github/skills/<name>/CONTEXT.md` | Module | Skill-specific vocabulary (phases, triggers, artifact types) |

**Loading precedence** (most specific wins on conflict):
1. Directory-local `CONTEXT.md`
2. Parent directory `CONTEXT.md` (walk up to repo root)
3. Repo-root `CONTEXT.md`

**Integration with `context-engineering` skill:** The skill's context hierarchy
(§ "The Context Hierarchy") should include `CONTEXT.md` files as a recognized
layer, loaded after `.github/copilot-instructions.md` and before task-specific
context.

## 5. Lifecycle

### Creation
- Agent creates `CONTEXT.md` when it encounters ≥3 domain terms in a session
  that aren't defined in any existing context file.
- Human creates manually when onboarding a new module or domain area.

### Update
- Agents append new terms/entities/patterns discovered mid-session.
- Updates are append-only during a session; deduplication happens on review.
- Each update bumps `last_updated` in frontmatter.

### Staleness management
- Terms not referenced in any source file for >90 days flagged for review.
- `freshness-audit` skill could be extended to cover `CONTEXT.md` files.
- Maximum file size: 200 lines. Beyond that, split into directory-scoped files.

### Review
- `CONTEXT.md` changes go through normal PR review.
- Reviewer checks: Are terms accurate? Are invariants actually enforced?

## 6. Interaction with Existing Tools

| Tool | Interaction |
|------|-------------|
| `context-engineering` skill | Loads `CONTEXT.md` files into agent context at session start. Could validate format. |
| `fill-context-pages` skill | Could scan `CONTEXT.md` for `[context-needed]` markers and fill them. |
| `AGENTS.md` | Repo-root `CONTEXT.md` complements `AGENTS.md` — AGENTS defines rules, CONTEXT defines vocabulary. |
| `docs/architecture.md` | Architecture doc is prose for humans; `CONTEXT.md` is structured data for agents. |

## 7. Open Questions

1. **Ownership:** Who is authoritative for `CONTEXT.md` — humans or agents?
   If agents can freely append, entries may be low quality. If human-only,
   the capture-mid-session benefit is lost.

2. **Bloat prevention:** How to prevent `CONTEXT.md` from growing into a
   second `AGENTS.md`? Strict line-count caps? Automated pruning?

3. **Format:** Should the file be pure YAML (machine-first) or markdown tables
   (human-readable with machine parsing)? Markdown tables are easier to read in
   PRs but harder to parse reliably.

4. **Conflict with existing files:** `.github/copilot-instructions.md` already
   contains some domain vocabulary. Should `CONTEXT.md` replace that content
   or supplement it?

5. **Multi-agent consistency:** If two agents edit `CONTEXT.md` concurrently,
   how are conflicts resolved? Standard git merge? Write lock?

## 8. Decision Needed

Whether to adopt the `CONTEXT.md` pattern. Options:

- **A) Full adoption:** Introduce repo-root + per-directory `CONTEXT.md` files,
  update `context-engineering` skill to load them.
- **B) Limited pilot:** Add repo-root `CONTEXT.md` only, evaluate for 30 days.
- **C) Defer:** Current context mechanisms are sufficient; revisit when agent
  context windows grow larger.

## 9. References

- `.github/skills/context-engineering/SKILL.md` — current context loading hierarchy
- `.github/skills/fill-context-pages/SKILL.md` — placeholder fill workflow
- mattpocock/skills research report (session artifact) — skills design principles
- `AGENTS.md` § Guardrails — existing domain rule definitions
