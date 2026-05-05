# Inbox source queue

Files in this directory are untrusted incoming sources awaiting intake.
CI-1 Gatekeeper triggers on pushes here and hands off to CI-3 for processing.

## Accepted formats

- `.md` — Markdown (preferred)
- `.html` — HTML (converted to Markdown during ingest)
- `.pdf` — PDF documents (converted to Markdown during ingest)
- `.txt` — Plain text

## Source requirements

- Descriptive filename (e.g., `medicare-part-d-overview.md`)
- `# Title` heading as the first line of content
- Plain Markdown body — no custom shortcodes or front matter required
