"""GitHub source monitoring pipeline for the knowledgebase.

This package implements the GitHub source monitoring pipeline described in
ADR-012. It polls external GitHub repositories for changes to tracked files,
vendors fetched content into ``raw/assets/``, and applies diff-aware updates
to the relevant wiki pages.

Scripts in this package follow the same governance model as ``scripts/kb/**``:
all write-capable surfaces must be declared in the ``AGENTS.md`` write-surface
matrix before they can write to any path.

Modules:
    check_drift     -- Read-only drift detection; emits a JSON drift report.
    fetch_content   -- Fetches and vendors assets; updates registry state.
    synthesize_diff -- Applies diff-aware wiki page updates from fetched assets.
"""
