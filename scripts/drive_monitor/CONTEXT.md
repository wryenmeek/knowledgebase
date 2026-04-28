---
scope: module
last_updated: 2026-04-28
---

# CONTEXT — scripts/drive_monitor/

Vocabulary for the Google Drive source-monitoring pipeline. `AGENTS.md` takes precedence on any conflict.

## Terms

| Term | Definition |
|------|------------|
| DriveDriftedEntry | A registry file_entry whose current `drive_version` (native) or `md5Checksum` (non-native) differs from the last-applied value, or a newly-discovered file under a monitored folder. |
| DriveFileEntry | A single entry in a `*.source-registry.json` `file_entries` list describing a monitored Drive file, its current fetch/apply state, and its target wiki page. |
| FolderEntry | A registered Google Drive root folder (by folder_id). All files discovered under it recursively are eligible for monitoring, subject to MIME allowlist. |
| drift report | The JSON artifact produced by `check_drift.py` listing all DriveDriftedEntries detected in the current run. |
| AFK lane | Entries classified as AFK by `classify_drift.py` (small text diff below `--afk-max-lines` threshold, native Doc MIME type, `tracking_status: active`). Default threshold is 0 (deny-by-default). |
| HITL lane | Entries classified as HITL by `classify_drift.py`. These generate GitHub Issues for human review instead of running `synthesize_diff.py`. Default for all entries until AFK is explicitly enabled. |
| Changes API cursor | The `changes_page_token` field in the registry file. Stores the Drive `changes.list` page token for incremental change detection. `null` on first run — initialised by calling `changes.getStartPageToken()`. |
| parent-chain resolution | For a changed file_id not yet in `file_entries`, iteratively calls `files.get(fileId, fields='id,parents')` ascending until a `folder_id` matching a FolderEntry is found (or the root is reached). Used for new-file discovery. |
| native format | A file whose MIME type is `application/vnd.google-apps.document` or `application/vnd.google-apps.presentation`. Content identity is tracked via `drive_version` integer. Export is requested via `files.export`. |
| non-native format | A file whose MIME type is one of: `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `text/plain`, `text/markdown`. Content identity is tracked via `md5Checksum`. Downloaded directly via `files.get(alt=media)`. |
| export normalization | Before computing SHA-256 of a native Markdown export, the bytes are normalized: strip trailing whitespace per line, normalize all line endings to `\n`, strip trailing blank lines, ensure single trailing newline. Required because `files.export` is not byte-idempotent. |
| `last_applied_*` fields | Fields in a DriveFileEntry recording the state of the last successful wiki write. Must NOT advance speculatively — only after confirmed wiki write. |
| `last_fetched_*` fields | Fields in a DriveFileEntry recording what was fetched/exported from Drive. Set by `fetch_content.py` after downloading and SHA-256-verifying content. |
| raw/assets/gdrive boundary | Assets stored at `raw/assets/gdrive/{alias}/{file_id}/{drive_version}/{filename}.md` (native) or `raw/assets/gdrive/{alias}/{file_id}/{md5_checksum}/{filename}` (non-native). Write-once via `exclusive_create_write_once()`. |
| bulk aggregation | When `≥ bulk_hitl_threshold` (default 3) deletion/scope-loss events share the same parent folder, `create_issues.py` combines them into a single HITL Issue instead of individual issues. |

## Invariants

| Invariant | Description |
|-----------|-------------|
| Lock ordering per ADR-021 | When acquiring both wiki and drive-sources locks: always acquire `wiki/.kb_write.lock` first, then `raw/.drive-sources.lock`. Reverse order causes deadlock. |
| Write-once assets | Assets in `raw/assets/gdrive/` are written exactly once via `exclusive_create_write_once()`. The version/checksum segment in the path prevents inter-run races. Never overwrite an existing asset. |
| `last_applied_*` only advances after confirmed wiki write | `synthesize_diff.py` must not update `last_applied_*` in the registry unless the wiki page write has been confirmed. If the wiki write fails, the registry update must be rolled back or skipped. |
| AFK deny-by-default | `classify_drift.py` defaults `--afk-max-lines 0`, routing all entries to HITL. AFK routing is only enabled when the operator explicitly passes a positive threshold. |
| Export normalization is mandatory | Always call `normalize_markdown_export()` before computing SHA-256 for any native Google Doc export. Raw export bytes are NOT stored — only normalized bytes are vendored. |
| Changes API cursor must be saved | After each successful `check_drift.py` run, the `newStartPageToken` from the final changes page must be written back to `changes_page_token` in the registry. Without this, the next run re-processes all changes since the last saved cursor. |

## File Roles

| File | Role |
|------|------|
| `check_drift.py` | Reads drive source registries, calls Changes API and parent-chain resolution, produces drift report JSON. Read-only. |
| `classify_drift.py` | Reads drift report, classifies entries as AFK or HITL. Read-only (outputs are transient CI artifacts). |
| `fetch_content.py` | Exports/downloads drifted content to `raw/assets/gdrive/`, normalizes, computes SHA-256, updates `last_fetched_*` in registry under `raw/.drive-sources.lock`. |
| `synthesize_diff.py` | Diffs old and new assets, updates wiki page, advances `last_applied_*` under both locks (wiki first, then drive). |
| `create_issues.py` | Creates GitHub Issues for HITL-classified entries: deletions, scope-loss, binary/oversize. |
| `_types.py` | TypedDicts for registry entries, drift report structure, MIME constants, and API response validators. |
| `_validators.py` | Alias slug validation, path traversal guards, bounds checks for asset paths and wiki paths. |
| `_http.py` | Drive API v3 client factory: service account auth, retry wrapper, `files.list`, `files.get`, `files.export`, `changes.list`, `changes.getStartPageToken`. |
| `_normalize.py` | `normalize_markdown_export(raw_bytes) → bytes` — canonical normalization for SHA-256. |
| `_registry.py` | Registry read/update helpers: `find_registry_files()`, `update_last_fetched()`, `update_last_applied()`, `update_changes_cursor()`. |
