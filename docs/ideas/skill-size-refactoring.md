# Inventory: Skill Size Refactoring

**Status:** In progress — `references/` directories created for 7 skills; SKILL.md content not yet extracted (2026-04-27)
**Date:** 2025-07-18
**Author:** Design research (Phase 7-C)

> **Implementation note (2026-04-27):** `references/` directories were created for
> 7 skills (test-driven-development, ci-cd-and-automation, frontend-ui-engineering,
> shipping-and-launch, code-review-and-quality, security-and-hardening,
> performance-optimization) plus a global `.github/skills/references/` shared
> directory. However, no SKILL.md content has been extracted yet — line counts
> are unchanged from the inventory below. **Exception:** `using-agent-skills`
> grew from 191 → 349 lines (all 97 skills catalogued with Route column). The
> line counts in §2 remain accurate for all other skills. Decision from §7 has
> not been made; implementation is paused at the `references/` scaffolding stage.

---

## 1. Problem

22 skills exceed 150 lines (the mattpocock target is ≤100 lines per skill).
Large skills are harder for agents to parse, increase context window consumption,
and drift from the "skills are workflows not documentation" principle.

When a skill file contains embedded examples, reference tables, and detailed
checklists alongside the workflow steps, agents must spend tokens processing
content that could live in linked reference files.

## 2. Inventory

All SKILL.md files exceeding 150 lines, verified via `wc -l`:

| # | Skill | Lines | Over Target (100) |
|---|-------|------:|---------:|
| 1 | jules-session-triage | 444 | +344 |
| 2 | test-driven-development | 379 | +279 |
| 3 | code-simplification | 338 | +238 |
| 4 | frontend-ui-engineering | 322 | +222 |
| 5 | context-engineering | 314 | +214 |
| 6 | shipping-and-launch | 309 | +209 |
| 7 | code-review-and-quality | 307 | +207 |
| 8 | documentation-and-adrs | 303 | +203 |
| 9 | browser-testing-with-devtools | 302 | +202 |
| 10 | git-workflow-and-versioning | 300 | +200 |
| 11 | debugging-and-error-recovery | 300 | +200 |
| 12 | api-and-interface-design | 294 | +194 |
| 13 | ci-cd-and-automation | 286 | +186 |
| 14 | incremental-implementation | 254 | +154 |
| 15 | security-and-hardening | 241 | +141 |
| 16 | planning-and-task-breakdown | 223 | +123 |
| 17 | deprecation-and-migration | 206 | +106 |
| 18 | spec-driven-development | 200 | +100 |
| 19 | source-driven-development | 194 | +94 |
| 20 | using-agent-skills | 349 | +249 | *(grew: now covers all 97 skills)* |
| 21 | performance-optimization | 183 | +83 |
| 22 | idea-refine | 178 | +78 |

**Note:** The original estimate was 23 skills. Verified count is 22.

## 3. Decomposition Strategies

### 3.1 Extract Examples → `references/examples/`

Many skills embed multi-line code examples (test patterns, refactoring before/after,
API design templates). These can move to linked reference files:

```
.github/skills/test-driven-development/
  SKILL.md              ← workflow steps only
  references/
    examples/
      tdd-cycle.md      ← RED/GREEN/REFACTOR code examples
      mock-patterns.md  ← mocking and stubbing examples
```

**Estimated savings:** 30–80 lines per skill with embedded examples.

### 3.2 Extract Reference Tables → `references/`

Skills like `git-workflow-and-versioning` and `shipping-and-launch` contain
lookup tables (commit message conventions, launch checklists, branch naming
rules). These are reference data, not workflow steps.

**Estimated savings:** 20–50 lines per skill with tables.

### 3.3 Extract Checklists → `references/checklists/`

Review checklists, security checklists, and launch checklists are standalone
artifacts that can be linked rather than inlined.

**Estimated savings:** 15–40 lines per skill with checklists.

### 3.4 Split Multi-Phase Skills

Some skills describe multiple distinct phases that could be independent skills:
- `test-driven-development` has TDD cycle + coverage analysis + browser testing
- `code-review-and-quality` has review + checklist + quality metrics
- `shipping-and-launch` has pre-launch + launch + post-launch

**Caution:** Splitting adds skill count and inter-skill coordination overhead.
Only split when phases are independently triggerable.

### 3.5 Inherently Large Skills

Some skills are genuinely complex workflows that resist splitting:
- `jules-session-triage` handles multiple Jules states (stuck, failed, waiting,
  PR review) — each state is a distinct workflow path
- `context-engineering` combines context hierarchy + loading rules + validation
  — these are tightly coupled

These should be documented as exemptions rather than force-split.

## 4. Per-Skill Recommendations (Top 10)

### 1. jules-session-triage (444 lines)

**Recommendation: Extract + partial split.** Contains extensive Jules SDK
usage examples and API response handling patterns that can move to
`references/examples/jules-sdk-patterns.md`. The session-state decision tree
(stuck/failed/waiting/PR) could become a linked reference table.
**Estimated reduction:** ~150 lines → ~294 lines remaining. Still large but
inherently complex (multi-state workflow).

### 2. test-driven-development (379 lines)

**Recommendation: Extract examples and browser testing section.** The TDD
cycle diagram, mock/stub examples, and the browser testing integration section
are extractable. Browser testing could be a cross-reference to
`browser-testing-with-devtools` rather than duplicated content.
**Estimated reduction:** ~130 lines → ~249 lines. Consider further splitting
coverage analysis into a linked checklist.

### 3. code-simplification (338 lines)

**Recommendation: Extract "Five Principles" examples.** Each principle has
before/after code examples that can move to `references/examples/`. The
principles themselves (one line each) stay in SKILL.md.
**Estimated reduction:** ~120 lines → ~218 lines.

### 4. frontend-ui-engineering (322 lines)

**Recommendation: Extract component patterns and CSS reference tables.**
Contains UI pattern catalog (forms, layouts, state management) that is reference
material, not workflow. Move to `references/ui-patterns.md`.
**Estimated reduction:** ~100 lines → ~222 lines.

### 5. context-engineering (314 lines)

**Recommendation: Extract context hierarchy table and rules file examples.**
The context hierarchy reference table and `.github/copilot-instructions.md`
structure examples are extractable. Knowledgebase helper surface docs could
link to the logic files directly.
**Estimated reduction:** ~90 lines → ~224 lines. Inherently large (combines
context theory + loading mechanics + validation).

### 6. shipping-and-launch (309 lines)

**Recommendation: Extract all checklists.** Pre-launch, launch-day, and
post-launch checklists are standalone artifacts. Extract to
`references/checklists/`. Workflow steps stay: "run pre-launch checklist"
with a link.
**Estimated reduction:** ~130 lines → ~179 lines.

### 7. code-review-and-quality (307 lines)

**Recommendation: Extract review checklist and quality dimensions table.**
The multi-axis review checklist (correctness, readability, architecture,
security, performance) is a reference artifact.
**Estimated reduction:** ~100 lines → ~207 lines.

### 8. documentation-and-adrs (303 lines)

**Recommendation: Extract ADR template and documentation structure examples.**
The ADR template and docs structure reference are standalone. Link to them.
**Estimated reduction:** ~80 lines → ~223 lines.

### 9. browser-testing-with-devtools (302 lines)

**Recommendation: Extract DevTools recipes.** Contains detailed DevTools
panel-by-panel instructions (Console, Network, Performance, Elements) that
are reference material. Extract to `references/devtools-recipes.md`.
**Estimated reduction:** ~120 lines → ~182 lines.

### 10. git-workflow-and-versioning (300 lines)

**Recommendation: Extract commit message conventions and branch naming tables.**
Convention tables are pure reference data. Workflow steps are "follow commit
conventions (see reference)".
**Estimated reduction:** ~100 lines → ~200 lines.

## 5. Reduction Target

**Goal:** Reduce from 22 to ≤15 skills over 150 lines.

Skills most likely to drop below 150 lines with extraction:

| Skill | Current | Est. After | Under 150? |
|-------|--------:|-----------:|:----------:|
| idea-refine | 178 | ~110 | ✓ |
| performance-optimization | 183 | ~120 | ✓ |
| using-agent-skills | 191 | ~125 | ✓ |
| source-driven-development | 194 | ~130 | ✓ |
| spec-driven-development | 200 | ~135 | ✓ |
| deprecation-and-migration | 206 | ~140 | ✓ |
| shipping-and-launch | 309 | ~179 | Borderline |
| planning-and-task-breakdown | 223 | ~148 | Borderline |

**Confident reductions (6 skills):** idea-refine, performance-optimization,
using-agent-skills, source-driven-development, spec-driven-development,
deprecation-and-migration.

**Possible reductions (2 skills):** shipping-and-launch, planning-and-task-breakdown.

**Result:** 22 → 14–16 skills over 150 lines (meets ≤15 target with the
confident reductions plus one borderline).

## 6. Implementation Approach (if approved)

1. **Create `references/` structure** in each skill directory.
2. **Extract one skill at a time** — each extraction is a single PR.
3. **Verify agent behavior** — confirm agents still follow the workflow
   correctly with linked references vs inline content.
4. **Measure context savings** — track total SKILL.md token count before/after.
5. **Start with the smallest wins:** idea-refine, performance-optimization,
   using-agent-skills (easiest to bring under 150 lines).

## 7. Decision Needed

Whether to pursue this refactoring and what the target should be:

- **A) Aggressive (100 lines):** Target mattpocock's ≤100 lines. Requires
  extensive extraction and possibly splitting complex skills. High effort.
- **B) Moderate (150 lines):** Target ≤150 lines for all skills. Focus on
  the 6–8 easiest reductions first. Medium effort.
- **C) Pragmatic (no fixed target):** Extract obvious reference material from
  the top 5 largest skills. No line-count mandate. Low effort.
- **D) Defer:** Current sizes are acceptable for now. Revisit when agent
  context windows change or skill count grows.

**Recommendation:** Option B — 150-line target is achievable for 6–8 skills
with pure extraction (no splitting required). The aggressive 100-line target
would require splitting skills, which adds coordination complexity. Start with
the confident reductions, measure agent behavior impact, then decide whether
to push further.
