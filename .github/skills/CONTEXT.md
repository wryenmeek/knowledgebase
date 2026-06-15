---
scope: directory
last_updated: 2026-06-15
---

# CONTEXT — .github/skills/

Vocabulary for the skill and agent persona layer. `AGENTS.md` takes precedence on any conflict.

## Terms

| Term | Definition |
|------|------------|
| skill | A workflow unit defined by a `SKILL.md` file in `.github/skills/<name>/`. Skills describe procedures and contracts, not executable logic (unless a `logic/` subdirectory is present). |
| agent persona | A custom agent configuration in `.github/agents/`. Personas like `knowledgebase-orchestrator` and `source-intake-steward` encapsulate domain knowledge and routing decisions. |
| operator-direct | Work that an operator (human or autonomous CI) routes directly to a declared AFK-eligible skill, bypassing the full persona pipeline. Requires an ADR-014 allowlist entry. |
| persona-routed | Work that flows through the full persona pipeline: `knowledgebase-orchestrator` → `source-intake-steward` → `evidence-verifier` → `policy-arbiter` → `synthesis-curator`. Default for all wiki work not on the AFK allowlist. |
| intake lane | The governing pathway for processing new source material. Requires: boundary validation → provenance check → evidence verification → policy review → synthesis. |
| AFK lane | Operator-direct pathway for tasks on the ADR-014 allowlist. Skips persona pipeline but still requires lock, log entry, and post-publication patrol. |
| evidence-verifier → policy-arbiter → synthesis-curator pipeline | The three-persona sequence that governs non-AFK synthesis. `knowledgebase-orchestrator` tests enforce this ordering — AFK cannot bypass without an allowlist entry. |
| synthesis combined entrypoint | `.github/skills/synthesize-entity-page/logic/synthesize_combined.py` — CI-3 entrypoint that synthesizes entity + concept pages in one critical section under a single `wiki/.kb_write.lock` acquisition. |
| `parents[4]` import pattern | The canonical way to import from `scripts.kb` inside skill logic files: `sys.path.insert(0, str(Path(__file__).resolve().parents[4]))`. Resolves 4 levels up from `logic/<file>.py` to the repo root. |
| skill-first execution | When a task matches a skill, invoke and follow that skill workflow. Do not quick-implement around an applicable skill. |
| instruction ratchet | The pattern where always-on instruction files such as `.github/copilot-instructions.md` grow monotonically add-only, decoupled from customization-surface growth. Measured by net line change in a window where skill count is flat. |
| Locality | A trigger-frequency ordinal for instruction destinations (Locality 0–4); frequency increases monotonically. Locality 4 = every turn (always-on); Locality 0 = only when a single file is read. See ADR-028. |
| trailer soft budget | The rolling-window cap on `Locality-4-Justification:` git trailers (default 1 per 10 commits to global rules sections) that prevents the escape hatch from normalizing into bypass. ADR-028 owns the enforcement details. |
| customizations lock | The planned file `.github/.customizations.lock` — concurrency guard for approved `--apply` mode writes to `.github/**` introduced by ADR-028; runtime acquisition remains deferred to slice 9b / issue #209. Sibling to `wiki/.kb_write.lock` and `raw/.rejection-registry.lock`; never held simultaneously with either once implemented. |

## Invariants

| Invariant | Description |
|-----------|-------------|
| Skill-first execution | If a task matches a skill, invoke the skill workflow. Do not skip required skill phases for non-trivial work. |
| Fail-closed on lock/policy | Skill logic files in `logic/` must fail closed on any lock contention, policy gap, or validation error. Partial success is treated as failure on protected/write paths. |
| Combined synthesis uses one lock | CI-3 synthesis flows run entity and concept draft generation under one lock-critical section (`synthesize_combined.py`) and release only after all writes/index/log updates complete. |
| `parents[4]` for imports | Skill logic files use `sys.path.insert(0, str(Path(__file__).resolve().parents[4]))` to import from `scripts.kb`. Never inline-reimplement helpers from canonical modules. |
| Logic files need matrix rows | Every `logic/*.py` file needs a row in the AGENTS.md write-surface matrix. A doc-only skill (no `logic/`) needs no row. |

## File Roles

| Directory | Role |
|-----------|------|
| `.github/skills/<name>/SKILL.md` | Skill contract: description, use-when triggers, procedure, acceptance criteria. |
| `.github/skills/<name>/logic/` | Optional executable logic implementing the skill contract. All logic files are read-only-only unless they declare a narrower write-surface row in AGENTS.md. |
| `.github/agents/` | Persona definitions for custom agents used in the skill framework (e.g., `knowledgebase-orchestrator.md`, `source-intake-steward.md`). |
| `.github/hooks/` | Agent lifecycle hooks for VS Code/Copilot integration. |
| `scripts/hooks/` | Pre-commit + PostToolUse hook scripts: `check_frontmatter.py`, `check_hooks_json.py`, `check_no_staged_locks.py`, `check_sourceref_format.py`, `check_context_md_format.py`, `check_matrix_coverage.py`, `check_mixed_scope.py`, `check_instructions_applyto_present.py`, `check_adr_cross_ref.py`, `check_stub_archive_path.py`, `locality_postuse_advisory.py`. |
| `.github/skills/references/` | Canonical shared checklists and reference docs used across multiple skills. |
