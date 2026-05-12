"""Google Drive source monitoring pipeline (ADR-021).

Six-script pipeline that detects content changes in registered Google Drive
folders and routes changed material through the wiki's provenance-safe ingest
pipeline.

Script execution order::

    check_drift.py       →  drift-report.json          (read-only)
    classify_drift.py    →  afk/hitl-entries.json       (read-only)
    fetch_content.py     →  raw/assets/gdrive/**        (write, --approval)
    synthesize_diff.py   →  wiki/**                     (write, --approval)
    create_issues.py     →  GitHub Issues               (write, GitHub API)
    advance_cursor.py    →  registry cursor update      (write, --approval)

See ``CONTEXT.md`` for full vocabulary and invariants.
"""
