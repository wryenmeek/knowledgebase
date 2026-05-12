# ADR-021: Google Drive source monitoring pipeline

## Status
Accepted

## Date
2026-05-06

## Context

The knowledgebase needs a way to monitor Google Drive folder trees and incorporate
changes to their contents as versioned source material in the wiki, without abandoning the
provenance controls established by ADR-006.

ADR-006 already allows external assets as authoritative sources when "vendored and
checksummed under `raw/assets/**`". However, no tooling existed for Drive-sourced content,
and no CI workflow existed to detect when Drive file contents changed.

ADR-012 established the GitHub source monitoring pipeline (`scripts/github_monitor/**`).
This ADR extends the same pattern to Google Drive, keeping the architecture as parallel and
consistent as possible.

ADR-007 lists approved post-MVP package surfaces. `scripts/drive_monitor/**` is not yet
listed; this ADR approves that addition.

The Drive Changes API provides a cursor-based mechanism (`changes.list` with
`pageToken`) that returns per-file change events across an entire Drive, making it
significantly more efficient than polling individual file metadata.

### API behavior validated before this decision

Before authoring this ADR the following Drive API behaviors were confirmed:
- `text/markdown` is the correct export MIME type for `files.export` on Google Docs (not
  `text/x-markdown`).
- `version` increments on content changes only (not on permission or metadata-only changes).
- `files.export` is **NOT byte-idempotent**: repeated exports of unchanged content may
  produce different raw bytes. A normalization pass is mandatory before hashing native
  Doc exports.

## Decision

Implement a Google Drive source monitoring pipeline as a new parallel automation lane that
does not replace or modify the existing `raw/inbox/` → `raw/processed/` ingest pipeline.

### Authoritative source boundary extension (extends ADR-006)

`raw/assets/gdrive/{alias}/{file_id}/{version_or_md5_segment}/{filename}` paths are
authoritative source inputs when:

1. Content was fetched via the Drive API v3 using a service account credential.
2. For native exports (Google Docs, Slides): SHA-256 was computed from **normalized**
   bytes (after `normalize_markdown_export()`) before any write to `raw/assets/`.
3. For non-native files (PDF, DOCX, text): SHA-256 was computed from the raw bytes before
   write; `md5Checksum` from the Drive API was verified to match immediately after download.
4. The file is tracked in a registry entry at `raw/drive-sources/{alias}.source-registry.json`
   with a matching `sha256_at_last_applied` field.

Content is immutable post-write: the path encodes the version/checksum, so any content
change produces a new path rather than mutating the existing asset.

### Registry governance (new mutable artifact type)

`raw/drive-sources/{alias}.source-registry.json` is a new mutable artifact with:

- **Write strategy:** atomic replace under `raw/.drive-sources.lock`
- **Lock:** `raw/.drive-sources.lock` (separate from `wiki/.kb_write.lock` to avoid
  contention; when both are needed, acquire `wiki/.kb_write.lock` first — see Lock ordering)
- **Schema owner:** `schema/drive-source-registry-contract.md`
- **Three-stage state per file_entry:**
  - `last_applied_*` — advanced only after wiki page is successfully updated
  - `last_fetched_*` — advanced after successful asset fetch; if synthesis fails,
    the next run retries synthesis from the already-fetched asset
  - Drift detection uses `drive_version` (native) or `md5Checksum` (non-native) as
    identity keys, not timestamps

### Authentication model

All Drive API access uses a **service account** (not personal OAuth):

- Service account JSON key stored in environment variable `GDRIVE_SA_KEY`.
- Per-registry `credential_secret_name` field overrides `GDRIVE_SA_KEY` if set.
- The key is never accepted as a CLI argument — environment variable only.
- Required scopes: `https://www.googleapis.com/auth/drive.readonly`.
- Secrets required: `GDRIVE_SA_KEY` (stored as repo secret, never committed).

The service account must be granted at least `Viewer` access to each monitored folder
tree. Access management is the operator's responsibility; the pipeline fails closed
(produces `AUTH_FAILED` or `FETCH_FAILED` reason codes) if credentials are missing or
unauthorized.

### Drive Changes API cursor management

- `changes_page_token: null` in a registry → call `getStartPageToken()` on first run;
  all file_entries for that registry are treated as `UNINITIALIZED_SOURCE`.
- After all entries for an alias are durably handled (synthesized, issued, or skipped):
  `advance_cursor.py` advances `changes_page_token` to the `newStartPageToken` from the
  drift report. The cursor is a terminal pipeline-level ACK — it advances only after the
  entire alias is processed, not as an intermediate step.
- `check_drift.py` is read-only: it reads the cursor but does NOT write it back.
- `fetch_content.py` advances `last_fetched_*` fields but does NOT advance the cursor.

### MIME allowlist and export strategy

Only six MIME types are tracked. Files outside this set produce `out_of_scope` drift events.
Google Drive shortcuts are skipped in MVP.

| MIME type | Export method | Identity key |
|---|---|---|
| `application/vnd.google-apps.document` | `files.export` → `text/markdown` | `drive_version` |
| `application/vnd.google-apps.presentation` | `files.export` → `application/pdf` | `drive_version` |
| `application/pdf` | Direct download | `md5Checksum` |
| `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | Direct download | `md5Checksum` |
| `text/plain` | Direct download | `md5Checksum` |
| `text/markdown` | Direct download | `md5Checksum` |

### Normalization requirement for native exports

Because `files.export` is not byte-idempotent, `normalize_markdown_export()` (in
`scripts/drive_monitor/_normalize.py`) MUST be applied to every native Google Doc export
before computing SHA-256 or writing to `raw/assets/`. The algorithm:

1. Decode bytes as UTF-8.
2. Normalize all line endings to `\n`.
3. Strip trailing whitespace from each line.
4. Strip leading and trailing blank lines.
5. Ensure exactly one trailing newline.
6. Re-encode as UTF-8.

This function is idempotent: applying it twice yields the same result.

### Parent-chain resolution for new files

When the Changes API reports a file that is not yet in `file_entries`, the pipeline
resolves its ancestry by walking parent IDs via `files.get?fields=parents` until it
either reaches a registered `folder_id` or exhausts the chain (O(folder-depth) API calls).
Files that cannot be traced to a registered folder produce `out_of_scope` drift events.

### HITL event types and bulk aggregation

Three distinct HITL Issue types are generated by `create_issues.py`:

1. **Content changed** (`event_type: content_changed`) — a tracked file's content changed
   and synthesis produced a wiki diff. One Issue per file.
2. **File trashed or deleted** (`event_type: trashed | deleted`) — Drive reported the file
   was trashed or permanently deleted. Requires operator review before wiki page removal.
3. **Out of scope** (`event_type: out_of_scope`) — file MIME type is not in the allowlist,
   or file could not be traced to a registered folder.

Bulk aggregation: when 3 or more entries share the same `(event_type, parent_folder_id)`
and `event_type ∈ {trashed, deleted, out_of_scope}`, `classify_drift.py` groups them into
one aggregated HITL entry with `is_bulk_aggregation: True`. This prevents Issues flood for
mass-deletion events.

### AFK eligibility (all conditions must hold)

1. `afk_max_lines > 0` (default: 0 = deny-by-default).
2. `event_type == "content_changed"`.
3. `tracking_status == "active"`.
4. `mime_type == "application/vnd.google-apps.document"` (native Docs only, not Slides).
5. `lines_added + lines_removed <= afk_max_lines`.

### New package surface (extends ADR-007)

`scripts/drive_monitor/**` is approved as a new post-MVP package surface for:
- Drift detection, asset fetching, diff-aware wiki synthesis, CI orchestration helpers, and
  GitHub Issues creation for the Google Drive source monitoring pipeline.

Invariants that still apply:
- CI-1 through CI-5 are unchanged; CI-6 is a new additive workflow.
- All write-capable surfaces must be declared in the `AGENTS.md` write-surface matrix.
- ADR-005 concurrency model applies: `wiki/.kb_write.lock` for all wiki writes.
- Paths outside `raw/assets/gdrive/**`, `raw/drive-sources/**`, and bounded `wiki/**`
  remain deny-by-default.

### Lock ordering

When any step requires both `wiki/.kb_write.lock` AND `raw/.drive-sources.lock`:

1. Acquire `wiki/.kb_write.lock` first.
2. Acquire `raw/.drive-sources.lock` second.

`fetch_content.py` acquires only `raw/.drive-sources.lock`. `synthesize_diff.py` acquires
both in the order above.

### CI-6 workflow structure

A new scheduled workflow (daily at 08:00 UTC — two hours offset from CI-5's 06:00 UTC to
avoid lock contention), plus `workflow_dispatch`:

1. **`check-drift` job** (`contents: read`): reads registry files, calls Drive Changes API,
   emits JSON drift report. Exits nonzero if any API call fails.
2. **`fetch-and-update` job** (`contents: write`, `pull-requests: write`, protected
   environment): runs only when drift is detected; fetches assets, normalizes, updates
   registry and cursor.
3. **`classify-drift` job** (read-only): classifies drift entries into AFK/HITL lists.
4. **`synthesize` job** (same permissions, protected environment): applies diff-aware wiki
   updates for AFK entries; opens HITL Issues for non-AFK entries.

All write jobs use the same `concurrency.group` as CI-3 and CI-5 to prevent parallel writes.

## Alternatives considered

### Webhook / push-based real-time monitoring via Drive push notifications

- **Pros:** lower latency.
- **Cons:** requires a running HTTPS endpoint to receive push notifications; significantly
  more infra; harder to audit; higher attack surface; notifications expire and require
  periodic renewal.
- **Rejected:** scheduled polling via GitHub Actions is sufficient for the required latency
  and is fully self-contained in the repository.

### Google Drive API v2 instead of v3

- **Pros:** slightly different but equally capable API.
- **Cons:** v2 is deprecated; migration risk; newer features like Changes API enhancements
  are v3-only.
- **Rejected:** v3 is current and fully supported.

### Per-file polling instead of Changes API

- **Pros:** simpler; no cursor state required.
- **Cons:** O(N) API calls where N = number of tracked files; may hit rate limits for
  large folders; does not detect deleted files efficiently.
- **Rejected:** Drive Changes API cursor is O(1) per run regardless of folder size.

### Personal OAuth instead of service account

- **Pros:** simpler credential setup.
- **Cons:** tokens tied to a personal account; expire and require interactive renewal; not
  suitable for unattended CI workflows.
- **Rejected:** service accounts do not expire and support headless CI authentication.

### Reuse `raw/inbox/` ingest pipeline for Drive files

- **Pros:** no new code; reuses existing ingest logic.
- **Cons:** loses version/checksum provenance from Drive; breaks diff-aware synthesis;
  requires manual operator intervention on every change.
- **Rejected:** the automated vendor-into-raw/assets approach preserves full provenance.

## Consequences

- `raw/drive-sources/` becomes a new mutable zone alongside `wiki/**`, `raw/processed/**`,
  and `raw/github-sources/**`.
- `raw/assets/gdrive/**` gains a new vendor sub-path convention.
- `scripts/drive_monitor/**` is an approved package location; write-capable scripts must
  declare surfaces in `AGENTS.md` before writing.
- `schema/drive-source-registry-contract.md` is added as the registry schema owner.
- A new lock path `raw/.drive-sources.lock` follows the same `fcntl`-based advisory lock
  pattern as `wiki/.kb_write.lock` and `raw/.github-sources.lock`.
- `scripts/kb/contracts.py` gains `DRIVE_SOURCES_LOCK_PATH`, `DriveMonitorReasonCode`,
  and `DRIVE_MONITOR_WRITE_ALLOWLIST_PATHS`.
- The `docs/architecture.md` automation model table gains a CI-6 row.
- `pyproject.toml` gains a `drive-monitor` optional dependency group with
  `google-api-python-client>=2.100` and `google-auth>=2.23`.

## References

- `ADR-004-split-ci-workflow-governance.md`
- `ADR-005-write-concurrency-guards.md`
- `ADR-006-authoritative-source-boundary.md`
- `ADR-007-control-plane-layering-and-packaging.md`
- `ADR-012-github-source-monitoring.md`
- `raw/processed/SPEC.md`
- `schema/drive-source-registry-contract.md`
- `scripts/kb/contracts.py` (`DRIVE_SOURCES_LOCK_PATH`, `DriveMonitorReasonCode`)
- `AGENTS.md` (write-surface matrix)
- `docs/ideas/google-drive-source-monitoring.md` (idea one-pager + design decisions Q1–Q11)
- `docs/ideas/spec-google-drive-source-monitoring.md` (implementation spec)
