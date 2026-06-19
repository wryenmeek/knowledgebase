---
scope: module
last_updated: 2026-06-18
---

# CONTEXT — scripts/kb/

Vocabulary for the canonical utility module layer. All agent context for work in this directory starts here. `AGENTS.md` takes precedence on any conflict.

## Terms

| Term | Definition |
|------|------------|
| agents_matrix_utils | Module for parsing the AGENTS.md write-surface matrix table. Used by both tests and the matrix-coverage pre-commit hook to avoid parser duplication. |
| `check_no_symlink_path` | Function in `write_utils` that verifies a resolved path stays inside an allowed root without following symlinks. Canonical path-safety pattern for all governed writes. |
| checkpoint_registry | Runtime for the wiki-processing checkpoint registry (`--bootstrap`, `--mutate`, `--verify`) governed by ADR-026 and `schema/wiki-processing-checkpoint-registry-contract.md`. |
| contracts | Module containing status enums, reason codes, governed artifact contracts, result type definitions, and the lock path constants. Single source of truth for all constants. |
| `exclusive_create_write_once` | Function in `write_utils` that creates a file exactly once using `O_CREAT | O_EXCL`. Used for write-once assets and processed artifacts. |
| github_customizations_freshness | Module for detecting drift in `.github/` customization files and producing structured drift reports. Used by the `github-customizations-freshness.yml` workflow. |
| github_customizations_graph | Module for building a cross-reference graph of agent persona → skill → script → copilot-instructions relationships. Used by `test_github_customizations.py`, `check_hooks_json.py`, and the `github-customizations-freshness` CI workflow. |
| GOVERNANCE_LOCK_FILES | Frozenset in `contracts.py` containing the basenames of all governance lock files, derived from the lock path constants. Never hardcode lock basenames elsewhere. |
| ingest_render | Module for rendering ingest artifacts (processed markdown and metadata). Used by `ingest.py`. |
| lint_wiki | `scripts/kb/lint_wiki.py` — validates wiki structure against the page template contract. |
| page_template_utils | Module containing frontmatter parsing, heading extraction, namespace constants, and wiki-page structural helpers. The first place to look before implementing any frontmatter or page-structure logic (ADR-011). |
| qmd_preflight | `scripts/kb/qmd_preflight.py` — prerequisite check that the `.qmd/index` exists before any index-writing operation can proceed. |
| rejection_validators | Module for validating rejection registry records. Used by the `log-intake-rejection` skill and `raw/rejected/` writes (ADR-013). |
| repo_identity | Module for canonical repository-name fallback logic shared by skill logic and SourceRef builders. |
| REQUIRED_SKILL_FIELDS | Pre-commit fast-path subset for SKILL.md frontmatter, declared in `page_template_utils.py`. |
| REQUIRED_WIKI_FIELDS | Pre-commit fast-path subset of `REQUIRED_FRONTMATTER_KEYS` declared in `page_template_utils.py`. Used by `check_frontmatter` hook. Keep in sync via drift-guard comment. |
| run_surface_cli | The CLI entrypoint helper in `scripts/_optional_surface_common.py`. All surfaces that emit structured JSON results use this. |
| sourceref | Module for deterministic SourceRef parsing, validation, and the exported `SOURCEREF_RE` regex. Never create a `sourceref_utils.py` — extend this module (ADR-011). |
| SurfaceResult | The `dataclass` from `scripts/_optional_surface_common.py` used as the structured exit contract for all `run_surface_cli`-backed surfaces. Defined outside `scripts/kb/` but consumed throughout. |
| write_utils | Module for safe file writes, atomic operations, `check_no_symlink_path`, write-lock primitives, and rollback helpers. All lock-protected writes go through this module. |

## Invariants

| Invariant | Description |
|-----------|-------------|
| ADR-011 canonical reuse | Check the four canonical modules (`page_template_utils`, `write_utils`, `contracts`, `sourceref`) before implementing any new helper. Extend, don't create parallel copies. |
| ADR-005 lock ordering | When combining `wiki/.kb_write.lock` with any other lock, always acquire `wiki/.kb_write.lock` first. Reverse order causes deadlock. |
| `exclusive_write_lock` is single-threaded | `write_utils._HELD_LOCK_COUNTS` supports same-process reentrancy for CLI flows but is not thread-safe; multithreaded callers must guard lock acquisition with `threading.Lock` or avoid concurrent use. |
| `is_relative_to()` not `startswith()` | Always use `Path.is_relative_to(wiki_root.resolve())` to verify a resolved path stays inside an allowed root. `str(resolved).startswith(str(root))` is not separator-safe. |
| Single source of truth for constants | Every module-level constant has one canonical definition. Import from `contracts.py` rather than copying values. |
| `__all__` required on public helpers | Every new public helper added to a canonical module must be listed in `__all__`. |

## File Roles

| File | Role |
|------|------|
| `agents_matrix_utils.py` | AGENTS.md write-surface matrix parser shared by tests and hooks. |
| `checkpoint_registry.py` | Bootstrap, mutate, and verify runtime for `raw/wiki-processing/wiki-processing-checkpoint-registry.json`; uses `CHECKPOINT_REGISTRY_LOCK_PATH`, atomic replace semantics, and the wiki-lock-before-checkpoint-lock ordering rule when a caller combines it with `wiki/.kb_write.lock`. |
| `contracts.py` | Enums, reason codes, governed artifact contracts, lock path constants, `GOVERNANCE_LOCK_FILES`. |
| `github_customizations_freshness.py` | Drift detection for `.github/` customization files. Powers the freshness CI workflow. |
| `github_customizations_graph.py` | Cross-reference graph: agents → skills → scripts → copilot-instructions. Shared by tests, hooks, and CI. |
| `ingest_render.py` | Ingest artifact rendering: processed markdown and companion `.meta.json` output. |
| `lint_wiki.py` | Wiki structure linter against page-template contract. |
| `page_template_utils.py` | Frontmatter parsing, heading extraction, namespace constants, required-field constants. |
| `path_utils.py` | `normalize_repo_relative_path()` and path safety helpers. |
| `qmd_preflight.py` | `.qmd/index` prerequisite check for index operations. |
| `rejection_validators.py` | Rejection registry record validation for `raw/rejected/` writes. |
| `repo_identity.py` | Canonical repository-name fallback helper for standard checkouts, linked worktrees, bare clones, and detached HEAD. |
| `sourceref.py` | SourceRef parsing, validation, `SOURCEREF_RE` regex. |
| `update_index.py` | Index regeneration (requires `qmd_preflight` check first). |
| `write_utils.py` | Safe file writes, locks, symlink checks, atomic replace, write-once creation. |
