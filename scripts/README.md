# scripts/ — surface landscape

This directory contains all knowledgebase CLI surfaces. Every surface emits deterministic
JSON to stdout and uses stable reason codes for machine-readable outcomes.

## Surface inventory

| Script | Type | CLI pattern | Writable? |
|--------|------|-------------|-----------|
| `kb/ingest.py` | Core KB | Custom `run_cli` | Yes (raw/processed + wiki) |
| `kb/update_index.py` | Core KB | Custom `main` | Yes (wiki/index.md) |
| `kb/lint_wiki.py` | Core validator | Custom `main` | No |
| `kb/persist_query.py` | Core KB | Custom `run_cli` | Yes (wiki/analyses) |
| `kb/qmd_preflight.py` | Core validator | Custom `run_cli` | No |
| `context/fill_context_pages.py` | Optional surface | `run_surface_cli` | Gated (apply mode; `.github/skills/**`, `docs/**`) |
| `context/manage_context_pages.py` | Optional surface | `run_surface_cli` | Gated (publish-status; delegates `wiki/status.md` via sync wrapper) |
| `reporting/content_quality_report.py` | Optional surface | `run_surface_cli` | Gated (persist mode; `wiki/reports/content-quality-*.json`) |
| `reporting/quality_runtime.py` | Optional surface | `run_surface_cli` | Gated (score-update: `wiki/reports/quality-scores-*.json`; report: `wiki/reports/quality-report-*.json`) |
| `maintenance/generate_docs.py` | Optional surface | `run_surface_cli` | Gated (apply mode; `docs/**`) |
| `validation/check_doc_freshness.py` | Validation | Custom `run_cli` | No |
| `validation/snapshot_knowledgebase.py` | Validation | Custom `run_cli` | No |
| `ingest/convert_sources_to_md.py` | Optional surface | `run_surface_cli` | Gated (apply mode; `raw/processed/**`) |
| `github_monitor/check_drift.py` | GitHub monitor Phase 1 | Module CLI (`python -m`) | No (drift report to file only) |
| `github_monitor/fetch_content.py` | GitHub monitor Phase 2 | Module CLI (`python -m`) | Gated (`raw/assets/**`, `raw/github-sources/**` registry) |
| `github_monitor/synthesize_diff.py` | GitHub monitor Phase 3 | Module CLI (`python -m`) | Gated (`wiki/**` change notes, `raw/github-sources/**` registry) |

## Common patterns

**`run_surface_cli` (optional surfaces):** All optional surfaces delegate their CLI shell to
`_optional_surface_common.run_surface_cli`, which handles arg-parse errors, emits canonical
`SurfaceResult` JSON, and returns an exit code. Surface-specific logic lives in `run_*`.

**`run_cli` (core surfaces):** Core surfaces implement their own `run_cli` with injectable
`output_stream`/`error_stream` and `repo_root` for test isolation.

**`if __package__ in (None, ""):` guard:** Appears in scripts that support both direct
execution (`python scripts/kb/lint_wiki.py`) and package import (`from scripts.kb import
lint_wiki`). The guard inserts the repo root into `sys.path` only when run directly.

All scripts that need this guard are nested exactly **two levels deep**
(`scripts/<subdir>/<file>.py`), so `Path(__file__).resolve().parents[2]` always resolves
to the repo root. If you add a script at a different nesting depth, update the `parents[N]`
index accordingly.

With `pip install -e .` (using the `pyproject.toml` at repo root), the repo root is
already on `sys.path` and the guard fires but has no effect. This is the recommended setup
for development and CI.

## Shared modules

| Module | Purpose |
|--------|---------|
| `_optional_surface_common.py` | Shared CLI shell, result types, path helpers for optional surfaces |
| `kb/contracts.py` | Enums, dataclasses, policy/reason-code constants |
| `kb/page_template_utils.py` | Wiki page parsing helpers and structural constants (canonical home) |
| `kb/path_utils.py` | Repo-relative path validation |
| `kb/write_utils.py` | Atomic writes, exclusive write lock, log append |
| `kb/sourceref.py` | SourceRef parse and validate |
