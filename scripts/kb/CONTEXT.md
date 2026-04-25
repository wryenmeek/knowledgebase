---
scope: module
last_updated: 2025-07-10
---

# CONTEXT — scripts/kb/

Vocabulary for the canonical utility module layer. All agent context for work in this directory starts here. `AGENTS.md` takes precedence on any conflict.

## Terms

| Term | Definition |
|------|------------|
| page_template_utils | Module containing frontmatter parsing, heading extraction, namespace constants, and wiki-page structural helpers. The first place to look before implementing any frontmatter or page-structure logic (ADR-011). |
| write_utils | Module for safe file writes, atomic operations, `check_no_symlink_path`, write-lock primitives, and rollback helpers. All lock-protected writes go through this module. |
| contracts | Module containing status enums, reason codes, governed artifact contracts, result type definitions, and the lock path constants. Single source of truth for all constants. |
| sourceref | Module for deterministic SourceRef parsing, validation, and the exported `SOURCEREF_RE` regex. Never create a `sourceref_utils.py` — extend this module (ADR-011). |
| agents_matrix_utils | Module for parsing the AGENTS.md write-surface matrix table. Used by both tests and the matrix-coverage pre-commit hook to avoid parser duplication. |
| SurfaceResult | The `dataclass` from `scripts/_optional_surface_common.py` used as the structured exit contract for all `run_surface_cli`-backed surfaces. Defined outside `scripts/kb/` but consumed throughout. |
| run_surface_cli | The CLI entrypoint helper in `scripts/_optional_surface_common.py`. All surfaces that emit structured JSON results use this. |
| qmd_preflight | `scripts/kb/qmd_preflight.py` — prerequisite check that the `.qmd/index` exists before any index-writing operation can proceed. |
| lint_wiki | `scripts/kb/lint_wiki.py` — validates wiki structure against the page template contract. |
| `check_no_symlink_path` | Function in `write_utils` that verifies a resolved path stays inside an allowed root without following symlinks. Canonical path-safety pattern for all governed writes. |
| `exclusive_create_write_once` | Function in `write_utils` that creates a file exactly once using `O_CREAT | O_EXCL`. Used for write-once assets and processed artifacts. |
| GOVERNANCE_LOCK_FILES | Frozenset in `contracts.py` containing the basenames of all governance lock files, derived from the lock path constants. Never hardcode lock basenames elsewhere. |
| REQUIRED_WIKI_FIELDS | Pre-commit fast-path subset of `REQUIRED_FRONTMATTER_KEYS` declared in `page_template_utils.py`. Used by `check_frontmatter` hook. Keep in sync via drift-guard comment. |
| REQUIRED_SKILL_FIELDS | Pre-commit fast-path subset for SKILL.md frontmatter, declared in `page_template_utils.py`. |

## Invariants

| Invariant | Description |
|-----------|-------------|
| ADR-011 canonical reuse | Check the four canonical modules (`page_template_utils`, `write_utils`, `contracts`, `sourceref`) before implementing any new helper. Extend, don't create parallel copies. |
| ADR-005 lock ordering | When combining `wiki/.kb_write.lock` with any other lock, always acquire `wiki/.kb_write.lock` first. Reverse order causes deadlock. |
| `is_relative_to()` not `startswith()` | Always use `Path.is_relative_to(wiki_root.resolve())` to verify a resolved path stays inside an allowed root. `str(resolved).startswith(str(root))` is not separator-safe. |
| Single source of truth for constants | Every module-level constant has one canonical definition. Import from `contracts.py` rather than copying values. |
| `__all__` required on public helpers | Every new public helper added to a canonical module must be listed in `__all__`. |

## File Roles

| File | Role |
|------|------|
| `contracts.py` | Enums, reason codes, governed artifact contracts, lock path constants, `GOVERNANCE_LOCK_FILES`. |
| `page_template_utils.py` | Frontmatter parsing, heading extraction, namespace constants, required-field constants. |
| `write_utils.py` | Safe file writes, locks, symlink checks, atomic replace, write-once creation. |
| `sourceref.py` | SourceRef parsing, validation, `SOURCEREF_RE` regex. |
| `agents_matrix_utils.py` | AGENTS.md write-surface matrix parser shared by tests and hooks. |
| `path_utils.py` | `normalize_repo_relative_path()` and path safety helpers. |
| `qmd_preflight.py` | `.qmd/index` prerequisite check for index operations. |
| `lint_wiki.py` | Wiki structure linter against page-template contract. |
| `update_index.py` | Index regeneration (requires `qmd_preflight` check first). |
