---
type: reference
title: "Locality Ladder — Manual Fallback Cheat Sheet"
status: active
updated_at: "2026-06-10"
owner: ".github/skills/audit-knowledgebase-workspace"
---

# Locality Ladder — Manual Fallback Cheat Sheet

Concise operator reference invoked from the `## ⚠️ Slash-Command Override` block
in `.github/copilot-instructions.md` and `AGENTS.md`. Use this only when the
`audit-knowledgebase-workspace` skill's `improve` flow is unavailable (skill not
installed, logic not yet implemented, or runtime gated).

The full design rationale lives in `docs/ideas/audit-workspace-improve-flow.md`
(PR #215) and `ADR-028: Instruction Locality Ladder` (`docs/decisions/ADR-028-instruction-locality-ladder.md`).
This file is the minimum operator-actionable subset.

## The Locality Ladder (Locality 0 → Locality 4)

Each Locality names **when** the agent pays the context cost. Lower tiers defer
context delivery (progressive disclosure / JIT). Reading top-to-bottom: per-turn
cost grows from 0 to full-file body.

| Locality | Trigger | Mechanism | Per-turn cost |
|---|---|---|---|
| **0** | File read | Code comment, `# noqa` rationale, docstring | **0** (body cost only when file is read) |
| **1** | File matches glob | `.github/instructions/<scope>.instructions.md` with required `applyTo:` frontmatter | **~1 metadata row** (file body on `view` when matched) |
| **2** | User invocation | `.github/skills/<name>/SKILL.md` | **0** (full skill body when invoked) |
| **3a** | Tool call (inject) | `PreToolUse` hook → returns context | **0** |
| **3b** | Tool call (block) | `PreToolUse` hook → non-zero exit | **0** |
| **3c** | After file edited | `PostToolUse` hook on edit + path glob | **0** |
| **3d** | Pre-commit | `.pre-commit-config.yaml` hook | **0** (block/warn at `git commit`) |
| **3e** | Prompt submit | `UserPromptSubmit` hook | **0** |
| **4** | Always-on | `.github/copilot-instructions.md` AND `AGENTS.md` | **Full file body, every turn** |

> Instruction files **without** `applyTo:` frontmatter behave as Locality 4
> (always loaded). `scripts/hooks/check_instructions_applyto_present.py`
> enforces the invariant at commit time.

## The 5-step efficiency check

Goal: find the tier that delivers a rule with **minimum expected token waste**
across its actual trigger pattern. A rule stays at Locality 4 only if all five
lower tiers produce worse expected token efficiency.

1. **Locality 0** — Can it live as a code comment / docstring / `# noqa`
   rationale at a single point in the codebase? If yes, **always pick this**
   (cheapest deterministic tier).
2. **Locality 1** — Can a plausible `applyTo:` glob be authored? Bar is "no
   glob *could* be authored," not "no glob exists today." Author a new
   `.github/instructions/<scope>.instructions.md` file if a glob would scope
   correctly. Consider per-package globs for friction concentrated in
   `scripts/kb/**`, `scripts/fleet/**`, `scripts/github_monitor/**`,
   `scripts/drive_monitor/**`, `scripts/ingest/**`, `scripts/validation/**`,
   `scripts/reporting/**`, `scripts/maintenance/**`, `scripts/context/**`,
   `scripts/hooks/**`, `.github/skills/**`, `.github/agents/**`, `wiki/**`,
   `schema/**`, `docs/decisions/**`, `tests/kb/**`.
3. **Locality 2** — Is it a discrete multi-step workflow? Could it live as a
   new skill or as a `references/` checklist under an existing skill?
4. **Locality 3a–3e** — Can a hook event fire it (PreToolUse, PostToolUse,
   pre-commit, UserPromptSubmit)?
5. **Locality 4** — Only after the above are exhausted. Requires a paired
   deletion candidate **or** a `Locality-4-Justification:` git trailer
   (see "Paired-deletion rule" below).

## Paired-deletion rule (Locality 4 additions)

Every Locality 4 addition to `.github/copilot-instructions.md` or `AGENTS.md`
must satisfy one of:

1. **Paired deletion** — accompany the addition with a deletion candidate of
   roughly equivalent token weight from the same file. The deletion must be a
   real removal, not a reformatting. Identify and execute in the same commit.
2. **Trailer escape** — include a `Locality-4-Justification:` git trailer on
   the commit explaining why no deletion candidate exists. Use the template at
   `docs/templates/locality-4-justification-trailer.md`. Trailer usage is
   audited and rate-limited (soft budget: 1 per 10 commits to either file).

The override block in both always-on files codifies this rule. ADR-028
defines the normative enforcement; the `audit-knowledgebase-workspace`
skill applies it when available.

## Cross-surface scope

Both `.github/copilot-instructions.md` and `AGENTS.md` are Locality 4 in this
repo. The write-surface matrix table body in `AGENTS.md` is **exempt** from the
paired-deletion rule — it grows with the codebase by design. Apply the rule
only to prose sections, not to the matrix.

## When this file is not enough

If the friction signal you are responding to does not classify cleanly via the
5-step check (e.g., crosses multiple Localities, or the candidate destination
file does not yet exist), **fail closed** per the override block: stop, do not
edit `.github/copilot-instructions.md` or `AGENTS.md`, and report the
unresolved classification. The full `improve` flow handles ambiguity through
escalation; this manual fallback intentionally does not.

## References

- [`docs/ideas/audit-workspace-improve-flow.md`](../../../../docs/ideas/audit-workspace-improve-flow.md) — full design (PR #215)
- [`docs/templates/locality-4-justification-trailer.md`](../../../../docs/templates/locality-4-justification-trailer.md) — trailer template
- [`scripts/hooks/check_instructions_applyto_present.py`](../../../../scripts/hooks/check_instructions_applyto_present.py) — Locality 1 invariant enforcement
- ADR-028 ([`docs/decisions/ADR-028-instruction-locality-ladder.md`](../../../../docs/decisions/ADR-028-instruction-locality-ladder.md)) — normative spec for the locality ladder and trailer governance
