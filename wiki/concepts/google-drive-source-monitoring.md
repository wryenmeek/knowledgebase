---
type: concept
title: "Google Drive Source Monitoring"
status: active
sources:
  - "repo://local/knowledgebase/raw/processed/google-drive-source-monitoring.md@021d32778765eb6ba54644c53740f2eb2fb70473#asset?sha256=4d742b3c97eaa6a0d2b2a108f805eaec29abe45bd8b61f7d482e4efcc5ce81d5"
  - "repo://local/knowledgebase/raw/processed/spec-google-drive-source-monitoring.md@021d32778765eb6ba54644c53740f2eb2fb70473#asset?sha256=0c8f994c68b8b75b3dc7d57af051213a326eade38dd9d6ef9a57b4b574e969c9"
open_questions:
  - "When drive_version increments on a metadata-only change (rename/move), how many unnecessary export API calls does this produce in practice? Is a modifiedTime pre-filter worth adding alongside drive_version gating to reduce quota waste?"
  - "Should the initial scan of a newly registered folder_entry produce one aggregated HITL Issue for all discovered files, or should new files be registered as tracking_status: uninitialized silently and processed on the following run?"
confidence: 5
sensitivity: internal
updated_at: "2026-08-13T06:00:00Z"
tags:
  - google-drive
  - source-monitoring
  - adr-021
  - ci-6
  - pipeline
search:
  boost: 2
---

# Google Drive Source Monitoring

## Summary

The Google Drive source monitoring pipeline detects content changes in registered
Drive folders and routes those changes through the wiki's provenance-safe ingest
pipeline with the same governance guarantees as the GitHub source monitoring
system (`scripts/github_monitor/`).

**Architecture: 6-script pipeline.** The pipeline runs as CI-6, a scheduled
GitHub Actions workflow:

1. `check_drift.py` (read-only) — polls the Drive Changes API with a stored
   `changes_page_token` cursor; resolves parent chains for newly discovered files;
   produces a structured `drift-report.json`.
2. `classify_drift.py` (read-only) — routes drifted entries to AFK or HITL
   buckets based on `--afk-max-lines` threshold (default 0 = deny-by-default
   per ADR-014).
3. `fetch_content.py` (write) — exports or downloads changed files to
   `raw/assets/gdrive/{alias}/{file_id}/{version}/` using `exclusive_create_write_once()`.
4. `synthesize_diff.py` (write) — applies diff-aware updates to bounded `wiki/**`
   pages listed in the registry entry's `wiki_page` field.
5. `create_issues.py` (write, GitHub side effects) — opens HITL GitHub Issues
   for changes that exceed the AFK threshold or for deletion/scope-loss events.
6. `advance_cursor.py` (write) — advances `changes_page_token` in the registry
   only after the pipeline completes without errors for that alias.

**Registry.** Each operator-assigned alias maps to
`raw/drive-sources/{alias}.source-registry.json`, which contains `folder_entries`
(root folders explicitly registered with a `wiki_namespace` field) and
`file_entries` (auto-managed per discovered file).

**Content identity.** Native Google Docs use `drive_version` as a change gate
and SHA-256 of canonically normalized Markdown export as content identity.
Non-native files (PDF, DOCX) use `md5Checksum` directly.

**Lock ordering.** Within the CI-6 synthesize job: acquire `wiki/.kb_write.lock`
first, then `raw/.drive-sources.lock`. This ordering is consistent with ADR-012's
lock ordering rule.

**Auth.** Google Cloud service account credentials stored as `GDRIVE_SA_KEY`
GitHub Secret. Optional `credential_secret_name` field per alias enables
multi-account setups.

**Deletion handling.** All deletion and scope-loss events create HITL Issues;
no automatic wiki page archiving occurs. Registry sets
`tracking_status: "pending_review"`.

**Governing ADR.** ADR-021. Implementation status: `scripts/drive_monitor/`
landed, ADR-021 accepted, CI-6 workflow running as of 2026-05-02.

## Evidence

- `repo://local/knowledgebase/raw/processed/google-drive-source-monitoring.md@021d32778765eb6ba54644c53740f2eb2fb70473#asset?sha256=4d742b3c97eaa6a0d2b2a108f805eaec29abe45bd8b61f7d482e4efcc5ce81d5`:
  One-pager. Defines the pipeline architecture, registry structure, MIME type
  allowlist, lock ordering, auth model, and resolved design decisions.

- `repo://local/knowledgebase/raw/processed/spec-google-drive-source-monitoring.md@021d32778765eb6ba54644c53740f2eb2fb70473#asset?sha256=0c8f994c68b8b75b3dc7d57af051213a326eade38dd9d6ef9a57b4b574e969c9`:
  Full spec. Defines the 6-script project structure, tech stack, command
  interfaces, assumptions, MVP scope, not-doing decisions, and open questions.

## Open Questions

- When `drive_version` increments on a metadata-only change (rename/move), how
  many unnecessary export API calls does this produce in practice? A
  `modifiedTime` pre-filter alongside `drive_version` gating may reduce Drive
  API quota waste.
- Should the initial scan of a newly registered `folder_entry` produce one
  aggregated HITL Issue for all discovered files, or should new files be
  registered silently as `tracking_status: "uninitialized"` and processed on
  the following run?
