# Drive Source Registry Contract

This document is the authoritative schema contract for
`raw/drive-sources/{alias}.source-registry.json` files. These files govern how the
knowledgebase monitors a specific Google Drive folder tree for source-material changes.
See `docs/decisions/ADR-021-google-drive-source-monitoring.md` for the governing
architectural decision.

## Scope and authority

- Applies to all `raw/drive-sources/*.source-registry.json` artifacts.
- Governs field semantics, the `tracking_status` state machine, the three-stage state
  fields, MIME allowlist, write semantics, and lock requirements.
- Declaring a path pattern here does **not** by itself grant write permission. Writers
  remain deny-by-default until `AGENTS.md` explicitly names the surface.

## File naming convention

```
raw/drive-sources/{alias}.source-registry.json
```

Where `alias` is the operator-assigned slug for this Drive source. Examples:

- `raw/drive-sources/cms-policies.source-registry.json`
- `raw/drive-sources/coverage-docs.source-registry.json`

Aliases must be lowercase, alphanumeric, and hyphen-separated. No underscores, slashes,
or dots other than the `.source-registry.json` suffix. No leading or trailing hyphens.

## JSON schema

```json
{
  "version": "1",
  "alias": "cms-policies",
  "credential_secret_name": "GDRIVE_SA_KEY", // pragma: allowlist secret
  "changes_page_token": "AJE...",
  "last_full_scan_at": null,
  "folder_entries": [
    {
      "folder_id": "1BxiM...",
      "folder_name": "CMS Policy Documents",
      "wiki_namespace": "cms/",
      "tracking_status": "active"
    }
  ],
  "file_entries": [
    {
      "file_id": "1A2B3...",
      "display_name": "coverage-guidance-2025.md",
      "display_path": "CMS Policy Documents/coverage-guidance-2025.md",
      "mime_type": "application/vnd.google-apps.document",
      "tracking_status": "active",
      "wiki_page": "wiki/pages/topical/cms/coverage-guidance-2025.md",
      "drive_version": 42,
      "md5_checksum_at_last_applied": null,
      "sha256_at_last_applied": "64hexchars...",
      "sha256_at_last_fetched": null,
      "last_applied_drive_version": 42,
      "last_fetched_drive_version": null,
      "md5_checksum_at_last_fetched": null,
      "last_applied_at": "2026-01-01T00:00:00Z",
      "last_fetched_at": null,
      "notes": ""
    }
  ]
}
```

## Field definitions

### Top-level fields

| Field | Type | Required | Description |
|---|---|---|---|
| `version` | `"1"` string | Yes | Schema version. Must be exactly `"1"`. |
| `alias` | string | Yes | Operator-assigned slug. Lowercase, alphanumeric, hyphen-separated only. |
| `credential_secret_name` | string | Yes | Environment variable name containing the service account JSON key. Defaults to `GDRIVE_SA_KEY`. |
| `changes_page_token` | string\|null | Yes | Google Drive Changes API page token. `null` for newly-created registries; `check_drift.py` will call `getStartPageToken()` on first run. |
| `last_full_scan_at` | ISO 8601 string\|null | Yes | Timestamp of last full folder scan (populates `file_entries` from scratch). `null` if no full scan has run. |
| `folder_entries` | array | Yes | One entry per top-level monitored folder root. |
| `file_entries` | array | Yes | One entry per tracked Drive file. Populated incrementally by `check_drift.py` as new files are discovered. |

### `folder_entries` fields

| Field | Type | Required | Description |
|---|---|---|---|
| `folder_id` | string | Yes | Google Drive folder ID (alphanumeric, no slashes or traversal sequences). |
| `folder_name` | string | Yes | Human-readable folder name (display only; not used for path construction). |
| `wiki_namespace` | string | Yes | Wiki namespace prefix for files under this folder (e.g. `cms/`). Used to construct `wiki_page` paths. |
| `tracking_status` | string enum | Yes | Monitoring state; see below. |

### `file_entries` fields

| Field | Type | Required | Description |
|---|---|---|---|
| `file_id` | string | Yes | Google Drive file ID. Alphanumeric, underscores, and hyphens only. No slashes or traversal. |
| `display_name` | string | Yes | Human-readable filename as returned by the Drive API. Used for asset path construction. Must not contain path separators or null bytes. |
| `display_path` | string | No | Folder-relative path (informational, may be stale after Drive renames/moves). |
| `mime_type` | string | Yes | MIME type as reported by Drive API. Must be in the MIME allowlist (see below). |
| `tracking_status` | string enum | Yes | Monitoring state; see below. |
| `wiki_page` | string\|null | Yes | Repo-relative path to the wiki page this entry maps to. `null` for `uninitialized` entries. Must resolve inside `wiki/` (bounds-checked). |
| `drive_version` | integer\|null | Yes | Latest known Drive `version` field for native Google files (Docs, Slides). `null` for non-native files and uninitialized entries. |
| `md5_checksum_at_last_applied` | 32-hex string\|null | Yes | MD5 checksum reported by Drive API for non-native files at last apply. `null` for native files and uninitialized entries. |
| `sha256_at_last_applied` | 64-hex string\|null | Yes | SHA-256 of the normalized/raw bytes that were applied to the wiki page. `null` if never applied. |
| `sha256_at_last_fetched` | 64-hex string\|null | Yes | SHA-256 of the bytes from the most recent successful fetch. `null` if no fetch since last apply. |
| `last_applied_drive_version` | integer\|null | Yes | Drive `version` at the time of last apply. `null` if never applied or if non-native file. |
| `last_fetched_drive_version` | integer\|null | Yes | Drive `version` from the most recent successful fetch. `null` if no fetch since last apply. |
| `md5_checksum_at_last_fetched` | 32-hex string\|null | Yes | MD5 checksum from the most recent fetch. `null` for native files and if no fetch since last apply. |
| `last_applied_at` | ISO 8601 string\|null | Yes | Timestamp when the last successful wiki-page update was written. `null` if never applied. |
| `last_fetched_at` | ISO 8601 string\|null | Yes | Timestamp of the most recent successful fetch. `null` if no fetch since last apply. |
| `notes` | string | No | Free-text operator notes. Not used by automation. |

## `tracking_status` enum

| Value | Meaning |
|---|---|
| `active` | Entry is actively monitored; included in drift checks. |
| `paused` | Entry is temporarily skipped during drift checks. State fields preserved. |
| `archived` | Entry will no longer be monitored. Treated as permanently inactive. |
| `unreachable` | The last drift check could not reach the file (Drive API error after retries). Operator must investigate; entry is skipped until reset to `active`. |
| `pending_review` | Entry requires human review before the next pipeline run will process it (e.g. after a HITL-classified change). Operator must investigate and set to `active` or `archived`. |
| `uninitialized` | Entry has been discovered but no wiki page exists yet. `check_drift.py` emits `UNINITIALIZED_SOURCE`. Operator must run the ingest pipeline to create the initial wiki page, then set `wiki_page` and advance status to `active`. |

## MIME allowlist

Only files with the following MIME types may be tracked. Files outside this set produce
an `out_of_scope` drift event.

| Drive MIME type | Export format | Identity key |
|---|---|---|
| `application/vnd.google-apps.document` | `text/markdown` (via `files.export`) | `drive_version` (integer) |
| `application/vnd.google-apps.presentation` | `application/pdf` (via `files.export`) | `drive_version` (integer) |
| `application/pdf` | Direct download | `md5Checksum` from Drive API |
| `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | Direct download | `md5Checksum` from Drive API |
| `text/plain` | Direct download | `md5Checksum` from Drive API |
| `text/markdown` | Direct download | `md5Checksum` from Drive API |

**Critical:** `files.export` for Google Docs is NOT byte-idempotent. Repeated exports of
unchanged content may produce different raw bytes. The canonical normalization function
`normalize_markdown_export()` in `scripts/drive_monitor/_normalize.py` MUST be applied
before computing SHA-256 of any native Doc export. Non-native files are written verbatim.

## Three-stage state machine

Mirrors the GitHub source monitoring pattern to prevent silent provenance loss when
fetching succeeds but wiki synthesis fails:

```
┌─────────────────────────────────────────────────────────────┐
│  Stage 1: check_drift.py (read-only)                        │
│  Calls Drive Changes API; resolves parent chains for new    │
│  files. Compares drive_version (native) or md5Checksum      │
│  (non-native) against last_applied_* fields.                │
│  No registry writes. Emits drift-report.json.               │
└─────────────────────────────────────────────────────────────┘
            ↓ drift detected
┌─────────────────────────────────────────────────────────────┐
│  Stage 2: fetch_content.py                                  │
│  Exports/downloads to:                                      │
│    raw/assets/gdrive/{alias}/{file_id}/{version_or_md5}/    │
│  Normalizes native Docs exports before writing.             │
│  Advances: sha256_at_last_fetched                           │
│            last_fetched_drive_version (native only)          │
│            md5_checksum_at_last_fetched (non-native only)   │
│            last_fetched_at                                  │
│  Does NOT touch: last_applied_* fields or cursor            │
└─────────────────────────────────────────────────────────────┘
            ↓ fetch succeeded
┌─────────────────────────────────────────────────────────────┐
│  Stage 3: synthesize_diff.py                                │
│  Applies diff-aware update to wiki page.                    │
│  Only on confirmed wiki write:                              │
│    advances last_applied_at                                 │
│              sha256_at_last_applied                         │
│              last_applied_drive_version (native)            │
│              md5_checksum_at_last_applied (non-native)      │
│    resets last_fetched_* to null                            │
└─────────────────────────────────────────────────────────────┘
            ↓ all entries for alias durably handled
┌─────────────────────────────────────────────────────────────┐
│  Stage 4: advance_cursor.py                                 │
│  Terminal pipeline-level ACK. Advances changes_page_token   │
│  to newStartPageToken from the drift report.                │
│  Only runs after ALL entries for the alias have been        │
│  processed (synthesized, issued, or skipped).               │
└─────────────────────────────────────────────────────────────┘
```

If synthesis fails mid-run, the next CI-6 run sees `sha256_at_last_fetched ≠ null` and
`sha256_at_last_applied ≠ sha256_at_last_fetched`, so it can retry synthesis using the
already-fetched asset without re-fetching.

## Asset path convention

```
raw/assets/gdrive/{alias}/{file_id}/{version_segment}/{display_name}
```

Where `version_segment` is:

- For native files (Docs, Slides): the integer `drive_version` as a string (e.g. `42`).
- For non-native files: the `md5Checksum` hex string from the Drive API.

Assets are written write-once via `exclusive_create_write_once()`. `FileExistsError` is
silently ignored (idempotent). The path encodes content identity, so any content change
produces a new path rather than mutating the existing asset.

## Write semantics

| Property | Value |
|---|---|
| Mutability | Mutable; updated by `fetch_content.py` and `synthesize_diff.py` |
| Write strategy | Atomic replace under lock |
| Lock path | `raw/.drive-sources.lock` |
| Lock requirement | Lock must be acquired before any write; fail closed on lock unavailability |
| Schema owner | `schema/drive-source-registry-contract.md` (this document) |
| Governed artifact contract | `scripts/kb/contracts.py` → `DRIVE_SOURCES_LOCK_PATH` |

Writers must:
1. Read the full registry JSON under the lock.
2. Mutate only the target entry's relevant fields.
3. Write the full updated JSON as an atomic replace (not in-place patch).
4. Release the lock.

## Lock ordering

When `synthesize_diff.py` requires both `wiki/.kb_write.lock` AND `raw/.drive-sources.lock`,
always acquire in this order to prevent deadlocks:

1. Acquire `wiki/.kb_write.lock` first.
2. Acquire `raw/.drive-sources.lock` second.

`fetch_content.py` acquires only `raw/.drive-sources.lock` (no wiki write).

## Extension rules

New registry fields must:
1. Add a row to the appropriate field table above.
2. Be backward-compatible (add-only; no field removals or renames).
3. Include `null` as an allowed value for optional fields.
4. Bump schema `version` only for breaking changes.
