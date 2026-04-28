# Spec: Google Drive Source Monitoring Pipeline

> **Phase:** Spec-Driven Development — Phase 1 (Specify)
> **Status:** Draft — awaiting human review
> **One-pager:** `docs/ideas/google-drive-source-monitoring.md`
> **Governing ADR to produce:** `docs/decisions/ADR-021-google-drive-source-monitoring.md`

---

## Assumptions (surface before implementation)

1. `google-api-python-client>=2.100` and `google-auth>=2.23` will be added to `pyproject.toml` dependencies.
2. Service account credential is a JSON key file (`google.oauth2.service_account.Credentials`), not P12.
3. Normalization algorithm for Markdown export SHA-256: strip trailing whitespace per line → normalize all line endings to `\n` → strip trailing blank lines → ensure single trailing newline → encode UTF-8 → SHA-256.
4. Parent-chain resolution uses `files.get(fileId, fields='id,parents')` — one API call per ancestor level (typically 2–5 hops for MVP).
5. `create_issues.py` for HITL Issues reuses `scripts/github_monitor/create_issues.py` GitHub API patterns (same `GITHUB_APP_ID` / `GITHUB_APP_PRIVATE_KEY` secrets).
6. Registry alias slug convention: lowercase, alphanumeric, hyphens only (matches `raw/github-sources/` naming).
7. `drive_version` maps directly to the Drive API `files` resource `version` integer field.
8. CI-6 workflow mirrors CI-5's 3-job structure with the addition of `GDRIVE_SA_KEY` secret.

---

## Objective

Build `scripts/drive_monitor/` — a 5-script Google Drive folder monitoring pipeline that:

1. Detects content changes in registered Google Drive root folders (Changes API + parent-chain resolution).
2. Exports changed files to `raw/assets/gdrive/{alias}/{file_id}/{version}/{filename}` with SHA-256 provenance.
3. Routes changes through the wiki's existing HITL-default ingest pipeline via diff-aware synthesis.
4. Creates HITL GitHub Issues for deletions, scope-loss events, and oversized/binary changes.

**Who:** Knowledge base operators who manage documentation in Google Drive and want changes automatically surfaced in the wiki.

**Success definition:** A registered Google Drive folder change (supported MIME type, content-only) is detected within one CI-6 run, its export is vendored at the correct path with the correct SHA-256, and the corresponding wiki page is updated via a governed write — all without operator manual intervention.

---

## Tech Stack

| Concern | Dependency |
|---|---|
| Drive API v3 | `google-api-python-client>=2.100` |
| Auth / service account | `google-auth>=2.23` |
| CLI + result envelope | `scripts/_optional_surface_common.py` (existing) |
| Safe file writes + locks | `scripts/kb/write_utils.py` (existing) |
| Status enums + reason codes | `scripts/kb/contracts.py` — add `DriveMonitorReasonCode` |
| TypedDicts + validators | `scripts/drive_monitor/_types.py` (new) |
| Registry contract | `schema/drive-source-registry-contract.md` (new) |
| Test runner | pytest (existing: `python3 -m pytest tests/`) |

---

## Commands

```bash
# Unit tests (drive monitor only)
python3 -m pytest tests/drive_monitor/ -v

# Full test suite (must not regress)
python3 -m pytest tests/

# Pipeline scripts (read-only)
python -m scripts.drive_monitor.check_drift \
    --registry raw/drive-sources/alias.source-registry.json \
    --output /tmp/drift-report.json

python -m scripts.drive_monitor.classify_drift \
    --drift-report /tmp/drift-report.json \
    --output-dir /tmp/

# Pipeline scripts (write-capable — require --approval approved)
python -m scripts.drive_monitor.fetch_content \
    --drift-report /tmp/drift-report.json \
    --approval approved

python -m scripts.drive_monitor.synthesize_diff \
    --drift-report /tmp/drift-report.json \
    --approval approved

python -m scripts.drive_monitor.create_issues \
    --drift-report /tmp/drift-report.json \
    --approval approved
```

---

## Project Structure

```
scripts/drive_monitor/
├── __init__.py
├── CONTEXT.md               # Vocabulary, invariants, lock ordering (mirrors github_monitor/CONTEXT.md)
├── _types.py                # TypedDicts: DriveRegistryFile, FolderEntry, DriveFileEntry,
│                            #   DriveDriftReport, DriveDriftedEntry, ErrorEntry
│                            #   + validator functions for registry and API response shapes
├── _validators.py           # Path traversal checks, alias slug validation
├── _http.py                 # Drive API client factory: service account auth, retry wrapper,
│                            #   files.list, files.get, files.export, changes.list, changes.getStartPageToken
├── _normalize.py            # normalize_markdown_export(raw_bytes) → bytes
│                            #   Canonical normalization for SHA-256 computation
├── check_drift.py           # READ-ONLY. Changes API scan + parent-chain new-file discovery.
│                            #   Produces drift-report.json. No repo writes.
├── classify_drift.py        # READ-ONLY. Routes drifted entries to AFK or HITL buckets.
│                            #   Produces afk-entries.json + hitl-entries.json for CI runner.
├── fetch_content.py         # WRITE. Exports/downloads changed files to raw/assets/gdrive/.
│                            #   Normalizes native exports. Computes SHA-256. Updates last_fetched_*.
│                            #   Requires --approval approved.
├── synthesize_diff.py       # WRITE. Applies diff-aware wiki page update. Advances last_applied_*.
│                            #   Only after confirmed wiki write. Requires --approval approved.
└── create_issues.py         # WRITE (GitHub API). Creates HITL Issues for deletions/scope-loss/
                             #   binary. Aggregates bulk events above configurable threshold.
                             #   Requires --approval approved.

raw/drive-sources/           # New mutable zone (parallel to raw/github-sources/)
raw/assets/gdrive/           # New asset subtree:
                             #   raw/assets/gdrive/{alias}/{file_id}/{drive_version}/{filename}.md (native)
                             #   raw/assets/gdrive/{alias}/{file_id}/{md5checksum}/{filename}   (non-native)

schema/
└── drive-source-registry-contract.md   # New: registry JSON schema + field semantics

docs/decisions/
└── ADR-021-google-drive-source-monitoring.md  # New governing ADR

tests/drive_monitor/
├── __init__.py
├── test_types.py            # Validator round-trips, invalid shape rejection
├── test_validators.py       # Alias slug, path traversal guards
├── test_normalize.py        # Normalization byte-level assertions (fixed test vectors)
├── test_check_drift.py      # Drift detection with mock Drive API responses
├── test_classify_drift.py   # AFK/HITL routing logic
├── test_fetch_content.py    # Export + SHA-256 + raw/assets write path
└── test_synthesize_diff.py  # Diff synthesis + last_applied_* advancement gate

.github/workflows/
└── CI-6-google-drive-monitor.yml   # Scheduled daily, 3-job structure mirrors CI-5
```

---

## Code Style

Mirror `scripts/github_monitor/` exactly. Key conventions:

```python
"""Drift detection for monitored Google Drive sources (Phase 1 — read-only).

Reads every active folder_entry from ``*.source-registry.json`` files under
``raw/drive-sources/``, queries the Drive Changes API for new page tokens,
discovers new/changed file IDs via parent-chain resolution, and compares
drive_version (native) or md5Checksum (non-native) against registry values.

Produces a structured drift report (``--output drift-report.json``).
This surface performs **no repository writes** — it is read-only.

Usage::

    python -m scripts.drive_monitor.check_drift \\
        [--registry raw/drive-sources/alias.source-registry.json] \\
        [--repo-root /path/to/repo] \\
        [--output drift-report.json]

Authentication:
    Set ``GDRIVE_SA_KEY`` (JSON key file content, base64) in the environment.
    Never accepted as a CLI argument.
"""

from __future__ import annotations

from typing import TypedDict
```

- All data shapes are `TypedDict` in `_types.py`.
- All external API calls go through `_http.py`; no `httpx`/`requests` calls in business logic modules.
- Validator functions in `_types.py` raise `ValueError` with a structured message; scripts catch and map to `ErrorEntry`.
- Module-level constants in `_types.py` — no inline magic strings.
- `DriveMonitorReasonCode` added to `scripts/kb/contracts.py` (parallel to `GitHubMonitorReasonCode`).

---

## Data Shapes (key TypedDicts)

### Registry file — `DriveRegistryFile`

```python
class DriveRegistryFile(TypedDict):
    version: str                      # "1"
    alias: str                        # operator-assigned slug
    credential_secret_name: str       # default "GDRIVE_SA_KEY"
    changes_page_token: str | None    # Drive Changes API cursor
    last_full_scan_at: str | None     # ISO 8601; periodic safety-net timestamp
    folder_entries: list[FolderEntry]
    file_entries: list[DriveFileEntry]

class FolderEntry(TypedDict):
    folder_id: str
    folder_name: str          # display only; may be stale after Drive rename
    wiki_namespace: str       # e.g. "cms/" → maps to wiki/cms/{slug}.md
    tracking_status: str      # "active" | "paused" | "archived"

class DriveFileEntry(TypedDict, total=False):
    file_id: str              # required; stable across renames/moves
    display_name: str         # filename at last fetch (informational)
    display_path: str         # folder-relative path (informational, may be stale)
    mime_type: str            # MIME type at last fetch
    tracking_status: str      # "active" | "paused" | "archived" | "pending_review" | "uninitialized"
    wiki_page: str | None     # auto-assigned: wiki_namespace + slugified display_name
    notes: str

    # Three-stage state machine (mirrors github_monitor)
    drive_version: int | None           # integer at last applied (native formats)
    last_applied_drive_version: int | None
    last_applied_at: str | None         # ISO 8601
    sha256_at_last_applied: str | None  # SHA-256 of normalized export
    last_fetched_drive_version: int | None
    last_fetched_at: str | None
    sha256_at_last_fetched: str | None

    # Non-native formats use md5Checksum as identity
    md5_checksum_at_last_applied: str | None
    md5_checksum_at_last_fetched: str | None
```

### MIME allowlist and export map

```python
DRIVE_MIME_ALLOWLIST: frozenset[str] = frozenset({
    "application/vnd.google-apps.document",        # → text/markdown export
    "application/pdf",                             # download directly
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # download
    "text/plain",                                  # download directly
    "text/markdown",                               # download directly
    "application/vnd.google-apps.presentation",   # → application/pdf export
})

MIME_EXPORT_MAP: dict[str, str] = {
    "application/vnd.google-apps.document": "text/markdown",
    "application/vnd.google-apps.presentation": "application/pdf",
}
# MIME types not in MIME_EXPORT_MAP are downloaded directly (no export needed).
```

### Asset path convention

```
# Native formats (Google Docs, Slides) — version-stamped:
raw/assets/gdrive/{alias}/{file_id}/{drive_version}/{display_name}.md
raw/assets/gdrive/{alias}/{file_id}/{drive_version}/{display_name}.pdf  (Slides)

# Non-native formats (PDF, DOCX, text/plain, text/markdown) — checksum-stamped:
raw/assets/gdrive/{alias}/{file_id}/{md5_checksum}/{display_name}
```

---

## Normalization Algorithm (`_normalize.py`)

Required because `files.export` is **not byte-idempotent** for native Google Docs:

```python
def normalize_markdown_export(raw_bytes: bytes) -> bytes:
    """
    Canonical normalization for SHA-256 computation of Google Docs Markdown exports.

    Steps (in order):
    1. Decode as UTF-8 with errors='replace'
    2. Normalize all line endings to \\n (handle \\r\\n, \\r)
    3. Strip trailing whitespace from each line
    4. Strip leading and trailing blank lines from the document
    5. Ensure exactly one trailing newline
    6. Re-encode as UTF-8

    The resulting bytes are the canonical form for SHA-256 comparison.
    Non-native formats (PDF, DOCX, text/plain, text/markdown) use raw md5Checksum
    from the Drive API — no normalization needed.
    """
```

Test vectors for `test_normalize.py` must cover:
- `\r\n` → `\n` conversion
- Trailing spaces on lines stripped
- Multiple trailing blank lines collapsed to one newline
- Pure blank document → single `\n`
- Already-normalized input is idempotent

---

## Pipeline Flow

```
check_drift.py          → drift-report.json       (read-only)
classify_drift.py       → afk-entries.json         (read-only; AFK deny-by-default)
                          hitl-entries.json
fetch_content.py        → raw/assets/gdrive/        (write: --approval approved)
                          updates last_fetched_*
synthesize_diff.py      → wiki/{namespace}/{page}   (write: --approval approved)
                          advances last_applied_* only on confirmed wiki write
create_issues.py        → GitHub Issues              (write: --approval approved)
```

**Lock ordering** (consistent with ADR-012):
1. `wiki/.kb_write.lock` — acquired first for any wiki write
2. `raw/.drive-sources.lock` — acquired second for registry update

Never held simultaneously for non-wiki writes. `fetch_content.py` acquires only `raw/.drive-sources.lock` (no wiki write). `synthesize_diff.py` acquires `wiki/.kb_write.lock` first, then `raw/.drive-sources.lock`.

---

## `check_drift.py` — Detection Logic

**Phase 1: Changes API scan**
1. Load registry for each `raw/drive-sources/*.source-registry.json`.
2. If `changes_page_token` is `None`: call `changes.getStartPageToken()` to initialize; record current state as uninitialized for all file_entries; save token; exit this alias with `uninitialized_source` entries.
3. Call `changes.list(pageToken=..., includeItemsFromAllDrives=True, supportsAllDrives=True, fields='nextPageToken,newStartPageToken,changes(fileId,file/id,file/name,file/mimeType,file/version,file/md5Checksum,file/parents,file/trashed,file/explicitlyTrashed)')`.
4. Page through all change pages; collect all changed `fileId` values.

**Phase 2: Parent-chain resolution**
5. For each changed `fileId`:
   - If already in `file_entries`: check MIME type, compare `drive_version` / `md5Checksum`. If changed → `DriveDriftedEntry(event_type="content_changed")`.
   - If NOT in `file_entries`: resolve parent chain via `files.get(fileId, fields='id,parents')` ascending until a `folder_id` matching a `FolderEntry.folder_id` is found. If found → `DriveDriftedEntry(event_type="new_file")`. If not under any registered folder → skip.
6. For `trashed=true` or `explicitlyTrashed=true` → `event_type="trashed"` or `event_type="deleted"`.
7. For MIME types not in allowlist → `event_type="out_of_scope"`.

**Phase 3: Produce drift report**
8. Write `DriveDriftReport` JSON to `--output`.

---

## `classify_drift.py` — AFK/HITL Classification

Default behavior: **AFK deny-by-default** (all entries → HITL).

AFK eligibility conditions (all must be true):
- `event_type == "content_changed"`
- MIME type is native Doc (→ Markdown export)
- `lines_added + lines_removed <= afk_max_lines` (default 0 = all HITL, must be explicitly set to allow AFK)
- `tracking_status == "active"`
- No bulk deletion threshold exceeded

Bulk aggregation: if `≥ bulk_hitl_threshold` (default 3) `event_type in {"trashed", "deleted", "out_of_scope"}` entries share the same parent folder → aggregate into a single HITL Issue.

---

## Governance Artifacts to Produce

| Artifact | Description |
|---|---|
| `schema/drive-source-registry-contract.md` | JSON schema + field semantics for `*.source-registry.json` files in `raw/drive-sources/`. Mirrors `schema/github-source-registry-contract.md`. |
| `docs/decisions/ADR-021-google-drive-source-monitoring.md` | Governing ADR. Covers auth model, CI-6 structure, lock ordering, asset path convention, Changes API cursor semantics, normalization requirement. |
| `raw/.drive-sources.lock` | New lock file (not committed — created at runtime by `write_utils`). |
| `scripts/kb/contracts.py` — `DriveMonitorReasonCode` | New `StrEnum` parallel to `GitHubMonitorReasonCode`. |
| `AGENTS.md` write-surface matrix rows | 5 rows: one per `scripts/drive_monitor/` executable script. |

---

## Testing Strategy

**Framework:** pytest (existing runner: `python3 -m pytest tests/`)

**Test locations:** `tests/drive_monitor/` mirrors `tests/github_monitor/` structure.

**Coverage requirements:**
- All validator functions: exhaustive valid/invalid shape tests
- `_normalize.py`: fixed byte-level test vectors (idempotent, `\r\n`, trailing spaces, blank doc)
- `check_drift.py`: mock Drive API responses for all event types (new, changed, trashed, deleted, out_of_scope, uninitialized)
- `classify_drift.py`: AFK/HITL routing for all event types; bulk aggregation threshold logic
- `fetch_content.py`: export path + SHA-256; lock acquisition order; non-native download path; `--approval` gate
- `synthesize_diff.py`: `last_applied_*` advancement gated on confirmed wiki write; lock ordering; `--approval` gate
- All tests must mock Drive API calls — no real API calls in test suite

**No real API calls in tests.** All `_http.py` interactions are replaced with fixtures returning mock Drive API response dicts.

**Regression gate:** `python3 -m pytest tests/` (full suite) must pass before any commit.

---

## Boundaries

**Always:**
- Run `python3 -m pytest tests/` before every commit
- Use `write_utils.py` for all file writes (atomic, lock-aware)
- Validate registry JSON against `schema/drive-source-registry-contract.md` before any write
- Acquire locks in the declared order: `wiki/.kb_write.lock` first, `raw/.drive-sources.lock` second
- Advance `last_applied_*` only after the wiki write is confirmed
- Use `normalize_markdown_export()` before computing SHA-256 for any native Google Doc export
- Add a `AGENTS.md` write-surface matrix row before any new executable surface writes to governed paths

**Ask first:**
- Adding or changing Python dependencies in `pyproject.toml`
- Modifying the normalization algorithm (SHA-256 hashes become incompatible with existing records)
- Adding new `tracking_status` enum values
- Changing the MIME type allowlist
- Changing asset path convention (affects existing raw/assets/gdrive/ entries)
- Modifying lock ordering rules

**Never:**
- Commit `GDRIVE_SA_KEY` or any credential material to the repository
- Call the Drive API in unit tests (use mocks)
- Advance `last_applied_commit_sha` / `last_applied_drive_version` before a confirmed wiki write
- Write outside declared write-surface paths (see AGENTS.md matrix)
- Skip `--approval approved` flag for any write-capable script
- Use inline magic strings — all constants belong in `_types.py`

---

## Success Criteria

The feature is **done** when all of the following are true:

1. **`check_drift.py`** reads a mock registry with 3 folder entries, calls mock Drive API (Changes + parent-chain), and produces a valid `DriveDriftReport` covering all five event types.
2. **`classify_drift.py`** routes all entries to HITL by default; routes a `content_changed` native-Doc entry to AFK when `--afk-max-lines 50` and change is ≤ 50 lines.
3. **`fetch_content.py`** exports a mock Google Doc to Markdown, normalizes it, SHA-256s it, writes to `raw/assets/gdrive/{alias}/{file_id}/{version}/{name}.md`, and updates `last_fetched_*` in the registry under `raw/.drive-sources.lock`.
4. **`synthesize_diff.py`** applies a diff to a mock wiki page, writes the updated page under `wiki/.kb_write.lock`, then advances `last_applied_*` under `raw/.drive-sources.lock`, and aborts without advancing if the wiki write fails.
5. **`create_issues.py`** creates HITL Issues for: a single deletion, a single out-of-scope event, and a bulk aggregation of 4 trashed events in the same parent folder.
6. **`python3 -m pytest tests/`** (full suite, including all existing tests) passes with no regressions.
7. **`schema/drive-source-registry-contract.md`** is written and referenced by `_types.py` validators.
8. **`ADR-021`** is written and reflects all design decisions from the one-pager + grill-me session.
9. **`AGENTS.md`** write-surface matrix has rows for all 5 `scripts/drive_monitor/` executable scripts.
10. **`DriveMonitorReasonCode`** is added to `scripts/kb/contracts.py` and exported via `__all__`.
11. **CI-6 workflow** YAML is written and mirrors CI-5's 3-job structure.

---

## Open Questions

1. **Changes API parent-chain validation** — Not yet confirmed that `changes.list` response entries include `file.parents` in a single call (may require a separate `files.get` for parents). The detection logic above assumes `parents` can be requested in the `fields` mask of `changes.list`. If not, each new-file change requires a separate `files.get(fields='id,parents')` call — cost is the same (O(1) per changed file), but the implementation in `check_drift.py` changes slightly.

2. **`raw/drive-sources/` directory creation** — Should the CI-6 workflow create this directory if it doesn't exist, or should it be committed as an empty directory with a `.gitkeep`? (Preference: `.gitkeep` committed, consistent with `raw/github-sources/`.)

---

*Spec status: draft. Awaiting human review and approval before Phase 2 (Plan).*
