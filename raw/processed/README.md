# Inbox source queue

Files in this directory are untrusted incoming sources awaiting intake.
CI-1 Gatekeeper triggers on pushes here and hands off to CI-3 for processing.

## Accepted formats

- `.md` — Markdown (preferred)
- `.html` — HTML (converted to Markdown during ingest)
- `.pdf` — PDF documents (converted to Markdown during ingest)
- `.txt` — Plain text

## Source requirements

- Descriptive filename (e.g., `policy-guidance-2025.md`)
- `# Title` heading as the first line of content
- Plain Markdown body — no custom shortcodes or front matter required

## Pipeline status

CI-3 processes all files in this directory on each run. After ingest, files are
moved to `raw/processed/` and wiki source pages are created under `wiki/sources/`.
If CI-3 is not triggering automatically, push a change to any file in this directory
to re-trigger CI-1 → CI-3.

> Last pipeline re-trigger: 2026-05-12 (unblocking after CI-3 lint fix for CONTEXT.md)

<!-- re-trigger 2026-05-12T04:08:48Z -->
