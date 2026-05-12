# Google Drive Source Monitoring

**Status:** Implemented — `scripts/drive_monitor/` landed, ADR-021 accepted, CI-6 workflow running, cross-functional review remediated (2026-05-02)

## Problem Statement
How might we monitor registered Google Drive root folders recursively for file changes, and automatically route those changes through the wiki's provenance-safe ingest pipeline — with the same governance guarantees as the existing GitHub source monitoring pipeline (`scripts/github_monitor/`)?

---

## Recommended Direction
**Two-level alias registry with Drive Changes API and parent-chain resolution.**

Structural commitments:

1. **Registry per operator-assigned alias** at `raw/drive-sources/{alias}.source-registry.json` — two-level: `folder_entries` (root folders explicitly registered, each with a `wiki_namespace` field) + `file_entries` (auto-managed per discovered file). Multiple disconnected root folders live in one alias registry.

2. **Initial run = full recursive folder walk** to populate `file_entries` from scratch. Subsequent runs use Drive's `changes.list` API with a stored `startPageToken`:
   - File_ids already in `file_entries`: O(1) lookup — update normally.
   - File_ids **not** in `file_entries` (newly added files): resolve parent chain (O(folder-depth) API calls) to check ancestry against registered root folder IDs. If matched, add to `file_entries`.
   - Falls back to a full walk on token expiry (30-day default window).
   - *Upgrade path (Phase 2):* Add configurable periodic full walk (e.g., weekly) as a safety net alongside parent-chain resolution.

3. **Content identity** — two fields per file entry, mirroring `github_monitor`'s `last_applied_blob_sha` / `sha256_at_last_applied` pattern:
   - `drive_version` (integer) — cheap per-file metadata field; used as the change gate (skip export if unchanged)
   - `sha256_at_last_applied` — SHA-256 of the **canonically normalized** Markdown or PDF export; confirms real content drift after a version increment. Normalization: strip trailing whitespace per line, normalize line endings to `\n`, collapse trailing blank lines. Schema contract must define normalization algorithm precisely.
   - Non-native files (PDF, DOCX, etc.): `md5Checksum` as direct content identity; no export needed for gating

4. **MIME type allowlist** — only files matching the include list are added to `file_entries`. Everything else is silently skipped; skipped MIME type counts are logged per scan run.
   - **Included:** `application/vnd.google-apps.document` (export to Markdown), `application/pdf` (vendor as-is), `application/vnd.openxmlformats-officedocument.wordprocessingml.document` (vendor as-is), `text/plain`, `text/markdown`, `application/vnd.google-apps.presentation` (export to PDF for MVP; Markdown export in Phase 2)
   - **Excluded:** Sheets, images, video, audio, `application/vnd.google-apps.shortcut` (shortcuts skipped; follow-with-deduplication as Phase 2)

5. **`wiki_page` auto-assignment** — each `folder_entry` declares a `wiki_namespace` field (e.g., `"wiki/cms/"`) at registration time. Auto-discovered files get `wiki_page = wiki_namespace + slugified-filename`. Subfolder path is included in the slug as a collision tiebreaker (e.g., two files named `policy.gdoc` in different subfolders produce `wiki/cms/procedures/policy.md` and `wiki/cms/guidelines/policy.md`).

6. **Asset path convention:**
   - Native Google Docs: `raw/assets/gdrive/{alias}/{file_id}/{drive_version}/{filename}.md`
   - Google Slides: `raw/assets/gdrive/{alias}/{file_id}/{drive_version}/{filename}.pdf`
   - Non-native (PDF, DOCX, etc.): `raw/assets/gdrive/{alias}/{file_id}/{md5_checksum}/{filename}`
   - All paths are write-once (version-addressed or content-addressed)

7. **New package surface** `scripts/drive_monitor/` — 6-script pipeline: `check_drift.py → classify_drift.py → fetch_content.py → synthesize_diff.py / create_issues.py`, plus `advance_cursor.py` for post-pipeline cursor advancement.

8. **Auth** — Google Cloud service account for all account types (personal and Workspace). Operator creates a GCP service account and grants folder-level access by sharing each Drive folder with the service account email. Service account JSON key stored as GitHub Secret `GDRIVE_SA_KEY`. Optional `credential_secret_name` field in the registry schema allows per-alias credential override (defaults to `GDRIVE_SA_KEY`); enables multi-account setups without a schema change.

9. **Deletion and scope-loss handling** — all three event types create a HITL Issue; registry marks `tracking_status: "pending_review"` in all cases:
   - **File trashed:** *"Source file was trashed — restore it to resume monitoring, or close this issue to archive the wiki page."*
   - **File permanently deleted:** *"Source file was permanently deleted — wiki page should be reviewed for archiving."*
   - **File moved out of registered folder:** *"Source file moved outside all registered root folders — update registry roots or close this issue to archive the wiki page."*
   - **Bulk scope-loss:** When ≥ N files (configurable, default 3) lose scope from the same parent folder in a single run, one aggregated HITL Issue is created listing all affected files and wiki pages.

10. **Lock ordering** — within the CI-6 synthesize job: acquire `wiki/.kb_write.lock` first, then `raw/.drive-sources.lock`. Consistent with ADR-012's ordering rule.

11. **`synthesize_diff.py` strategy** — identical mechanism to `github_monitor` for MVP (raw text diff → wiki update). Markdown-structured (heading-level) synthesis noted as Phase 2 upgrade in ADR-021.

12. **CI-6 workflow** — new scheduled workflow (multi-hour or daily cadence + `workflow_dispatch`), 5-job structure: `check-drift` (read-only) → `fetch-and-update` (write, protected env) → `classify-drift` (read-only) → `synthesize` (write, protected env) → `advance-cursor` (write, `if: always()`). Shares the same concurrency group as CI-5 to prevent parallel wiki writes.

13. **Governance artifacts** — new ADR (ADR-021), new lock `raw/.drive-sources.lock` (same `fcntl` advisory pattern), new schema contract `schema/drive-source-registry-contract.md`, new AGENTS.md write-surface matrix rows.

---

## Validated Assumptions (pre-spec research, 2026-04-27)

- ✅ **Markdown export MIME type** — confirmed `text/markdown` (not `text/x-markdown`). Drive API v3 `files.export` with `mimeType=text/markdown` is officially supported for Google Docs as of 2024.
- ✅ **`version` field semantics** — confirmed content-change only. Rename, move, and permission changes do **not** increment `version`. The gate is reliable with zero metadata false positives.
- ⚠️ **Export byte-determinism** — Google does **not** guarantee byte-identical output from repeated `files.export` calls on unchanged content (whitespace, formatting, export engine updates can vary). **Consequence:** raw SHA-256 of the export is not a stable identity hash. The export must be **canonically normalized** before hashing (strip trailing whitespace per line, normalize line endings to `\n`, collapse trailing blank lines). The schema contract must define the normalization algorithm precisely.
- 🔲 **Changes API parent-chain resolution** — not yet validated; confirm that change entries include sufficient metadata (file ID + parent IDs) to perform efficient parent-chain lookup before committing to spec.

---

## MVP Scope
**In:**
- Registry schema + validation (`_types.py`, `schema/drive-source-registry-contract.md`), including `folder_entries.wiki_namespace`, `folder_entries.last_scan_at`, `file_entries` list, `credential_secret_name` optional field
- Full recursive folder walk for initial `file_entries` population
- MIME type allowlist filtering (Google Docs, PDF, DOCX, text, Markdown, Google Slides as PDF); shortcut skipping with logged counts
- Changes API integration + parent-chain resolution for new file discovery on subsequent runs
- `wiki_page` auto-assignment via folder-to-namespace mapping + slugified filename with subfolder tiebreaker
- Google Docs → Markdown export + SHA-256 as content hash
- Non-native files (PDF, DOCX) and Google Slides (PDF) vendored as-is into `raw/assets/`
- HITL-default classification (all changes → GitHub Issue until AFK threshold enabled, per ADR-014)
- Three distinct HITL Issue types for deletion/scope-loss events; bulk aggregation at configurable threshold (default 3)
- Service account auth via `GDRIVE_SA_KEY` GitHub Secret; optional `credential_secret_name` per-alias override
- CI-6 scheduled workflow with `wiki/.kb_write.lock` → `raw/.drive-sources.lock` ordering
- ADR-021 and AGENTS.md write-surface matrix rows
- `raw/.drive-sources.lock` (new lock, same pattern as `raw/.github-sources.lock`)

**Out of MVP:**
- Wiki page archiving on file deletion (HITL Issue created instead; no auto-mutation)
- Google Sheets synthesis (excluded from MIME allowlist entirely)
- Google Slides Markdown export (PDF only in MVP; Markdown export in Phase 2)
- Heading-level Markdown-structured synthesis (Phase 2 upgrade path noted in ADR-021)
- Personal OAuth refresh token auth (replaced by service account model)
- Drive shortcut following (skipped in MVP; follow-with-deduplication as Phase 2)
- Periodic supplemental full walk safety net (Phase 2 upgrade from parent-chain-only approach)

---

## Not Doing (and Why)
- **Webhooks / Google Workspace Events API push notifications** — requires external HTTP receiver infra; ADR-012 rejected this for `github_monitor` for the same reason; "a few hours" latency makes it unnecessary; confirmed via research that no native recursive folder subscription exists in the Drive API
- **Auto-deleting wiki pages on file deletion** — irreversible; HITL review must precede any wiki deletion
- **Google Sheets wiki synthesis** — tabular data doesn't map to wiki prose without a dedicated format strategy; excluded from MIME allowlist
- **Personal OAuth user credentials for CI** — replaced by service account model; personal refresh tokens lapse after 6 months of non-use and require browser re-authorization, making them fragile for CI
- **Drive shortcuts following in MVP** — same Drive file reachable via shortcuts in two registered folders would produce duplicate wiki pages (provenance violation); deduplication logic deferred to Phase 2
- **Changes API as sole detection (no initial walk)** — fatal cold-start: files that predate monitoring registration are invisible until they happen to be modified

---

## Open Questions
- When `drive_version` increments on a metadata-only change (rename/move), how many unnecessary export API calls does this produce in practice? Is a `modifiedTime` pre-filter worth adding alongside `drive_version` gating to reduce quota waste?
- Should the initial scan of a newly registered `folder_entry` produce one aggregated HITL Issue for all discovered files (applying Q8 bulk aggregation logic), or should new files be registered as `tracking_status: "uninitialized"` silently and processed on the following run?

---

## Resolved Design Decisions (grill-me session, 2026-04-27)

| # | Question | Resolution |
|---|---|---|
| Q1 | New file discovery on subsequent Changes API runs | Parent-chain resolution for file_ids not in `file_entries` (Approach 1 for MVP); Approach 3 (+ periodic full walk safety net) as documented upgrade path |
| Q2 | Auth model | Service account for all account types; drop personal OAuth refresh tokens |
| Q3 | `account_slug` naming | Operator-assigned human-readable alias |
| Q4 | Lock acquisition order | `wiki/.kb_write.lock` first, then `raw/.drive-sources.lock` (consistent with ADR-012) |
| Q5 | Deletion event types | Three distinct HITL Issue bodies (trashed / permanently deleted / out of scope); `tracking_status: "pending_review"` |
| Q6 | Credential binding | Single `GDRIVE_SA_KEY` default; optional `credential_secret_name` override field in registry schema |
| Q7 | `synthesize_diff.py` strategy | Identical to `github_monitor` for MVP; Markdown-structured synthesis as Phase 2 upgrade |
| Q8 | Bulk HITL aggregation for scope-loss events | Aggregate when ≥ N files lose scope from same parent folder in one run; configurable threshold (default 3) |
| Q9 | `wiki_page` assignment for auto-discovered files | Folder-to-namespace mapping; `wiki_namespace` field per `folder_entry`; subfolder path as collision tiebreaker |
| Q10 | MIME type allowlist | Google Docs (→ Markdown), PDF, DOCX, text/plain, text/markdown, Google Slides (→ PDF for MVP); Sheets and shortcuts excluded |
| Q11 | Drive shortcuts | Skip in MVP (log skipped count per scan); follow-with-deduplication as Phase 2 |
