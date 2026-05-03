# Spec: Google Drive Source Monitoring Pipeline

> **Phase:** Spec-Driven Development — Phase 1 (Specify)
> **Status:** Implemented — ADR-021 accepted, `scripts/drive_monitor/` landed with CI-6 workflow (2026-04-29)
> **One-pager:** `docs/ideas/google-drive-source-monitoring.md`
> **Governing ADR:** `docs/decisions/ADR-021-google-drive-source-monitoring.md`

## Remaining Remediation Items

> Items found during 2026-04-29 verification review. All resolved as of 2026-05-02.

1. ~~**`advance_cursor.py` not wired into CI-6 workflow**~~ — Fixed 2026-05-02.
   Added 5th job `advance-cursor` to CI-6 with `if: always()` gating.

2. ~~**CI-6 missing from `docs/architecture.md`**~~ — Fixed 2026-04-29.
   Architecture.md now includes CI-6 row, `raw/drive-sources/**` zone,
   `scripts/drive_monitor/**` package surface, and ADR-021 reference.

---

## Assumptions (surface before implementation)

1. `google-api-python-client>=2.100` and `google-auth>=2.23` will be added to `pyproject.toml` dependencies.
2. Service account credential is a JSON key file (`google.oauth2.service_account.Credentials`), not P12.
3. Normalization algorithm for Markdown export SHA-256: strip trailing whitespace per line → normalize all line endings to `\n` → strip trailing blank lines → ensure single trailing newline → encode UTF-8 → SHA-256.
4. Parent-chain resolution uses `files.get(fileId, fields='id,parents')` — one API call per ancestor level (typically 2–5 hops for MVP).
5. `create_issues.py` for HITL Issues reuses `scripts/github_monitor/create_issues.py` GitHub API patterns (same `GITHUB_APP_ID` / `GITHUB_APP_PRIVATE_KEY` secrets).
6. Registry alias slug convention: lowercase, alphanumeric, hyphens only (matches `raw/github-sources/` naming).
7. `drive_version` maps directly to the Drive API `files` resource `version` integer field.
8. CI-6 workflow uses a 5-job structure (check-drift, fetch-and-update, classify-drift, synthesize, advance-cursor) with the addition of `GDRIVE_SA_KEY` secret.

---

## Objective

Build `scripts/drive_monitor/` — a 6-script Google Drive folder monitoring pipeline that:

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
    --hitl-entries hitl-entries.json

# Cursor advancement (terminal pipeline ACK — write-capable)
python -m scripts.drive_monitor.advance_cursor \
    --drift-report drift-report.json \
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
├── create_issues.py         # WRITE (GitHub API). Creates HITL Issues for deletions/scope-loss/
│                            #   binary. Aggregates bulk events above configurable threshold.
└── advance_cursor.py        # WRITE. Terminal pipeline ACK: advances changes_page_token in
                             #   the registry after all entries for an alias are durably handled.
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
└── CI-6-google-drive-monitor.yml   # Scheduled daily, 4-job structure (check-drift → fetch-and-update → classify-drift → synthesize)
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
create_issues.py        → GitHub Issues              (write: GitHub API)
advance_cursor.py       → registry cursor update     (write: --approval approved)
                          terminal ACK — advances changes_page_token only after
                          all entries for an alias are durably handled
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
| `AGENTS.md` write-surface matrix rows | 7 rows: one umbrella plus one per `scripts/drive_monitor/` executable script. |

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
9. **`AGENTS.md`** write-surface matrix has rows for all 6 `scripts/drive_monitor/` executable scripts plus 1 umbrella row.
10. **`DriveMonitorReasonCode`** is added to `scripts/kb/contracts.py` and exported via `__all__`.
11. **CI-6 workflow** YAML is written with a 5-job structure (check-drift, fetch-and-update, classify-drift, synthesize, advance-cursor).

---

## Open Questions

> Both resolved during implementation.

1. ~~**Changes API parent-chain validation**~~ — Resolved: `changes.list` does not include `file.parents` in its response. Implementation uses a separate `files.get(fileId, fields='id,parents')` call per new file. Cost is O(folder-depth) per new file, typically 2–5 hops. See `check_drift.py:94-98`.

2. ~~**`raw/drive-sources/` directory creation**~~ — Resolved: directory is created on first registry file commit (e.g., `raw/drive-sources/sof-session-notes.source-registry.json`). No `.gitkeep` needed.

---

*Spec status: implemented — all P0–P3 findings remediated (2026-05-02). Remaining low-priority items deferred to GitHub issues #84–#88.*

---

## Cross-Functional Review Findings (Remediation Complete)

> **Review date:** 2025-07-15 (initial) · 2026-07-22 (re-verification) · 2026-05-02 (remediation)
> **Reviewers:** code-reviewer, security-auditor, test-engineer, solutions-architect, documentation-engineer, framework-engineer
> **Scope:** All `scripts/drive_monitor/` code, tests, governance artifacts, and documentation against this spec.
> **Re-verification summary:** All 35 original findings resolved. 10 new findings identified during re-verification; all P0–P3 remediated in commit `2b2b463` (2026-05-02). 5 low-priority items deferred to GitHub issues #84–#88.

#### Re-Verification Status Summary

| Finding | Status | Evidence |
|---------|--------|---------|
| CR-1 | ✅ Resolved | `advance-cursor` job added to CI-6 workflow (`2b2b463`) |
| CR-2 | ✅ Resolved | Compensating rollback at `synthesize_diff.py:407-431` |
| CR-3 | ✅ Resolved | `test_create_issues.py` exists with 30 tests |
| HI-1 | ✅ Resolved | `ValueError` caught, re-raised with `from None` |
| HI-2 | ✅ Resolved | `synthesize_diff.py` now calls `safe_filename()` from `_validators.py` (`2b2b463`) |
| HI-3 | ✅ Resolved | `_sanitize_for_md()` added for heading + change-note body; title uses `json.dumps` (`2b2b463`) |
| HI-4 | ✅ Resolved | `httplib2.Http(timeout=30)` at `_http.py:129` |
| HI-5 | ✅ Resolved | `test_http.py` exists with 11 tests |
| HI-6 | ✅ Resolved | `test_registry.py` exists with 10 tests |
| HI-7 | ✅ Resolved | `binascii`/`struct` imports removed |
| ME-1 | ✅ Resolved | Flag is `--drift-report`, not `--afk-entries` |
| ME-2 | ✅ Resolved | `DRIVE_MONITOR = "tp-drive-monitor"` at `contracts.py:39` |
| ME-3 | ✅ Resolved | CI-6 entry at `test_ci_permission_asserts.py:84` |
| ME-4 | ✅ Resolved | Field names aligned; `unreachable` added to code frozensets (`2b2b463`) |
| ME-5 | ✅ Resolved | 5-job structure documented in spec + ADR-021 |
| ME-6 | ✅ Resolved | `--hitl-entries`, no `--approval` |
| ME-7 | ✅ Resolved | `ghp_*`, `github_pat_*`, `gho_*`, `Authorization`, base64 covered |
| ME-8 | ✅ Resolved | All docs agree: `advance_cursor.py` owns cursor |
| ME-9 | ✅ Resolved | `__init__.py` no longer shows `--approval` for `create_issues.py` |
| ME-10 | ✅ Resolved | `${{}}` replaced with `[expr]` |
| HK-1 | ✅ Resolved | `_is_binary()` only in `synthesize_diff.py` where used |
| HK-2 | ✅ Resolved | Unused imports removed from `synthesize_diff.py` |
| HK-3 | ✅ Resolved | Dead code removed from `_validators.py` (`2b2b463`) |
| HK-4 | ✅ Resolved | `MIME_EXPORT_MAP` not imported in `classify_drift.py` |
| HK-5 | ✅ Resolved | `update_last_applied()` docstring fixed (`2b2b463`) |
| HK-6 | ✅ Resolved | Inline `import re` moved to module level in `_registry.py`; inline regex in `synthesize_diff.py` replaced by `safe_filename()` (`2b2b463`) |
| HK-7 | Deferred | Cross-module private import; acceptable per current conventions |
| HK-8 | ✅ Resolved | `min(attempt, len(_RETRY_DELAYS) - 1)` clamp at `_http.py:153` |
| HK-9 | ✅ Resolved | Iterates all parents before ascending at `check_drift.py:94-98` |
| HK-10 | ✅ Resolved | `_LEADING_DOTS_RE.sub` at `_validators.py:152` |
| HK-11 | ✅ Resolved | `files.list` removed from CONTEXT.md |
| HK-12 | ✅ Resolved | `add_file_entry()` added to CONTEXT.md |
| HK-13 | Deferred | Numpydoc gaps — tracked in GitHub issue #84 |
| HK-14 | ✅ Resolved | Dual-input documented at `synthesize_diff.py:283-289` |
| HK-15 | Deferred | Floor-only pins — tracked in GitHub issue #85 |

### Status Key

| Status | Meaning |
|--------|---------|
| 🔴 NOT IMPLEMENTED | Spec-required feature is missing from the codebase |
| 🟡 PARTIALLY IMPLEMENTED | Feature exists but has gaps or deviations from spec |
| 🟠 MISALIGNED | Implementation contradicts spec, ADR, or governance docs |
| ⚪ HOUSEKEEPING | Dead code, style, or documentation-only fix |

---

### Critical Findings

#### CR-1: Changes API cursor is never advanced 🔴

**Affected files:** `check_drift.py:218`, `fetch_content.py` (entire), `_registry.py:188-210`
**Detected by:** code-reviewer, solutions-architect, documentation-engineer

`check_drift.py` discards `_new_token` from `list_changes()`. `update_changes_cursor()` exists in `_registry.py` but has zero callers. Every CI-6 run re-processes all changes since the last manually-saved cursor, causing unbounded API growth and eventual quota exhaustion.

Additionally, on first run (uninitialized cursor), `get_changes_start_page_token()` result is also discarded — the cursor can never bootstrap.

**Remediation:**
1. Add `new_page_token` per-alias to the drift report JSON output from `check_drift.py`
2. `fetch_content.py` calls `update_changes_cursor(repo_root, registry_path, new_page_token)` after all entries for an alias are successfully fetched
3. First-run path in `check_drift.py` must include the start page token in the report

#### CR-2: Non-atomic wiki + registry write in `synthesize_diff.py` 🟡

**Affected files:** `synthesize_diff.py:369-402`
**Detected by:** code-reviewer, security-auditor

Wiki page is written (line 384) before `update_last_applied()` (line 392). If registry update fails, the wiki page is already mutated but `last_applied_*` never advances — next run re-appends the identical change note (non-idempotent).

**Remediation:** Either (a) write wiki page to temp file first, commit only after registry update succeeds, or (b) capture original wiki content before modification and restore on registry failure.

#### CR-3: Missing `test_create_issues.py` 🔴

**Affected files:** `tests/drive_monitor/` (missing file)
**Detected by:** test-engineer

Spec success criterion #5 requires tests for deletion, out-of-scope, and bulk aggregation Issues. No test file exists. This is the single largest test coverage gap.

**Remediation:** Create `tests/drive_monitor/test_create_issues.py` with ≥10 tests covering: 3 spec scenarios, dedup via `_search_existing_issue()`, `gh` CLI failure, `_sanitize_gh_md()` injection prevention, `_redact_stderr()`, empty input, malformed JSON.

---

### High Findings

#### HI-1: Credential fragment leakage via `ValueError` traceback 🟡

**Affected files:** `_http.py:78-80`
**Detected by:** security-auditor

`service_account.Credentials.from_service_account_info()` can raise `ValueError` with key fragments in the message. This `ValueError` is not caught — only `ImportError` and `json.JSONDecodeError` are handled.

**Remediation:** Wrap `from_service_account_info()` in `try/except (ValueError, KeyError)` and re-raise as `DriveAPIRequestError` with `from None` to suppress `__cause__`.

#### HI-2: Filename construction diverges between `fetch_content.py` and `synthesize_diff.py` 🟡

**Affected files:** `fetch_content.py:88-102`, `synthesize_diff.py:128-170`
**Detected by:** code-reviewer, solutions-architect

`synthesize_diff.py` inlines equivalent filename logic but omits the `"untitled"` fallback. If a display name sanitizes to empty, `fetch_content` writes to `untitled.md` but `synthesize_diff` looks for `.md` — silent lookup failure.

**Remediation:** Extract `safe_filename(display_name, mime_type) → str` into `_validators.py`. Import from both modules.

#### HI-3: YAML frontmatter injection via unsanitized `display_name` 🟡

**Affected files:** `synthesize_diff.py:377-380`
**Detected by:** security-auditor

`display_name` from Drive file metadata is interpolated directly into YAML frontmatter without validation. A file named `test\ntags: [malicious]` could inject arbitrary YAML fields.

**Remediation:** Call `validate_display_name()` before wiki write, or use `json.dumps()` for YAML-safe quoting of the title field.

#### HI-4: No HTTP transport timeout on Drive API client 🟡

**Affected files:** `_http.py:108`
**Detected by:** security-auditor

`build("drive", "v3", ...)` creates an HTTP client with no socket-level timeout. A stuck connection hangs CI until the job-level timeout (6 hours).

**Remediation:** Add `httplib2.Http(timeout=30)` and pass via `google_auth_httplib2.AuthorizedHttp`.

#### HI-5: No dedicated tests for `_http.py` retry logic 🔴

**Affected files:** `tests/drive_monitor/` (no `test_http.py`)
**Detected by:** test-engineer

`_with_retry()` is security-and-reliability-critical. No test validates 429 backoff, 500 retry-then-fail, permanent 403 no-retry, or `retry-after` header handling.

**Remediation:** Create targeted tests for `_with_retry()` covering all retry/no-retry paths.

#### HI-6: No dedicated tests for `_registry.py` 🔴

**Affected files:** `tests/drive_monitor/` (no `test_registry.py`)
**Detected by:** test-engineer

`_atomic_replace_registry()` failure path, `update_last_applied()` resetting `last_fetched_*`, `add_file_entry()` deduplication, and `update_changes_cursor()` are untested.

**Remediation:** Create `tests/drive_monitor/test_registry.py` covering atomic replace failure, state machine transitions, dedup, and cursor persistence.

#### HI-7: Dead imports in `fetch_content.py` 🟡

**Affected files:** `fetch_content.py:155-157`
**Detected by:** code-reviewer

`import binascii as _bi` and `import struct as _st` are imported but never used. Only `hashlib.md5()` is called.

**Remediation:** Delete lines 155-157.

---

### Medium Findings

#### ME-1: CI-6 YAML passes non-existent `--afk-entries` flag 🟠

**Affected files:** `.github/workflows/ci-6-google-drive-monitor.yml:241`
**Detected by:** documentation-engineer

`synthesize_diff.py` parser accepts `--drift-report`, not `--afk-entries`. This would cause a **runtime failure in CI**.

**Remediation:** Change YAML to `--drift-report afk-entries.json`.

#### ME-2: Missing `TokenProfileId.DRIVE_MONITOR` enum member 🔴

**Affected files:** `scripts/kb/contracts.py`
**Detected by:** framework-engineer

CI-6 declares `TOKEN_PROFILE: tp-drive-monitor` but this profile is not registered in the `TokenProfileId` enum.

**Remediation:** Add `DRIVE_MONITOR = "tp-drive-monitor"` to `TokenProfileId`.

#### ME-3: Missing CI-6 entry in `test_ci_permission_asserts.py` 🔴

**Affected files:** `tests/kb/test_ci_permission_asserts.py`
**Detected by:** framework-engineer

CI-6 workflow comment says it's machine-checked by this test — that promise is unfulfilled. Depends on ME-2.

**Remediation:** Add `WorkflowPolicyExpectation` entry for CI-6 to `WORKFLOW_POLICY_MATRIX`.

#### ME-4: Schema contract `tracking_status` enum mismatches code 🟠

**Affected files:** `schema/drive-source-registry-contract.md`
**Detected by:** documentation-engineer

Contract lists `unreachable` (not in code), omits `pending_review` (is in code). Field names use `drive_version_at_last_applied` vs code's `last_applied_drive_version`. `parent_folder_id` listed as file_entry field but absent from TypedDict. `display_path` present in code but absent from contract.

**Remediation:** Align contract field names, enum values, and field lists with `_types.py` TypedDicts.

#### ME-5: Spec and ADR say "3-job CI structure" — implementation has 4 jobs 🟠

**Affected files:** Spec L19 (assumption #8), L420 (criterion #11), ADR-021
**Detected by:** documentation-engineer, solutions-architect

The 4-job design (splitting `classify-drift` from `synthesize`) is correct but undocumented.

**Remediation:** Update spec assumption #8, success criterion #11, and ADR-021 to reflect 4-job structure with rationale.

#### ME-6: Spec shows wrong CLI flags for `create_issues.py` 🟠

**Affected files:** Spec L80-82
**Detected by:** documentation-engineer

Spec shows `--drift-report` flag and `--approval approved`. Actual CLI uses `--hitl-entries` and has no approval gate.

**Remediation:** Update spec command examples.

#### ME-7: `_redact_stderr()` misses modern token formats 🟡

**Affected files:** `create_issues.py:56-60`
**Detected by:** security-auditor

Regex only catches hex strings. Misses `ghp_*`, `github_pat_*`, base64 blobs, and `Authorization` header values.

**Remediation:** Expand regex to cover fine-grained tokens, bearer headers, and base64 blobs.

#### ME-8: CONTEXT.md and ADR-021 disagree on cursor ownership 🟠

**Affected files:** `scripts/drive_monitor/CONTEXT.md:39`, ADR-021
**Detected by:** documentation-engineer

CONTEXT.md says `check_drift.py` saves cursor. ADR-021 says `fetch_content.py` advances it. Neither does.

**Remediation:** After CR-1 fix, update both documents to reflect the actual cursor ownership.

#### ME-9: `__init__.py` declares `--approval` for `create_issues.py` — no gate exists 🟠

**Affected files:** `scripts/drive_monitor/__init__.py:12`, `create_issues.py`
**Detected by:** solutions-architect

Consistent with `github_monitor` pattern (which also lacks an approval gate on `create_issues.py`), but the docstring is aspirational.

**Remediation:** Correct `__init__.py` docstring to remove `--approval` from the `create_issues.py` line.

#### ME-10: `_sanitize_gh_md()` doesn't strip `${{}}` expressions 🟡

**Affected files:** `create_issues.py:63-74`
**Detected by:** code-reviewer

If Issue body is consumed in a workflow `run:` block via `${{ github.event.issue.body }}`, template expressions could trigger Actions expression injection.

**Remediation:** Add `s = s.replace("${{", "").replace("}}", "")`.

---

### Housekeeping Findings

| ID | Finding | Files | Detected by |
|----|---------|-------|-------------|
| HK-1 | `_is_binary()` duplicated; dead in `check_drift.py` | `check_drift.py:77`, `synthesize_diff.py:84` | code-reviewer, architect |
| HK-2 | Unused imports: `tempfile`, `contextlib`, `DRIVE_SOURCES_LOCK_PATH` in `synthesize_diff.py` | `synthesize_diff.py:25,28,47` | code-reviewer |
| HK-3 | Unused imports/constants in `_validators.py`: `urllib.parse`, `PurePosixPath`, `_FORBIDDEN_COMPONENTS`, `_MAX_PATH_DEPTH` | `_validators.py:11-17` | code-reviewer |
| HK-4 | Unused import `MIME_EXPORT_MAP` in `classify_drift.py` | `classify_drift.py:39` | code-reviewer |
| HK-5 | `update_last_applied()` docstring contradicts behavior | `_registry.py:146-148` | code-reviewer, architect |
| HK-6 | Inline `import re` and `import hashlib` in function bodies | `_registry.py:229`, `synthesize_diff.py:128,164,389` | code-reviewer |
| HK-7 | `_validators.py` imports `_`-prefixed private symbols from `_types.py` | `_validators.py:14` | architect |
| HK-8 | `_RETRY_DELAYS` index can `IndexError` if `_MAX_RETRIES` changes independently | `_http.py:29-30,131` | code-reviewer |
| HK-9 | `_resolve_parent_folder` follows last parent not first (missing `break`) | `check_drift.py:101` | code-reviewer |
| HK-10 | `_safe_filename()` can produce leading-dot hidden files | `fetch_content.py:88-102` | security-auditor |
| HK-11 | CONTEXT.md `_http.py` role lists non-existent `files.list` | `CONTEXT.md` | documentation-engineer |
| HK-12 | CONTEXT.md missing `add_file_entry()` in `_registry.py` role | `CONTEXT.md` | documentation-engineer |
| HK-13 | Multiple functions missing numpydoc Parameters/Returns sections | Various | documentation-engineer |
| HK-14 | Undocumented dual-input contract (`entries` vs `drifted`) in `synthesize_diff.py` | `synthesize_diff.py:285-290` | architect |
| HK-15 | Floor-only dependency pins — no upper bounds or lock file | `pyproject.toml:15-18` | security-auditor |

---

### Spec Corrections Required

| Location | Current text | Correction |
|----------|-------------|------------|
| L19 (assumption #8) | "CI-6 workflow mirrors CI-5's 3-job structure" | Change to "4-job structure" |
| L80-82 | `create_issues.py --drift-report ... --approval approved` | Change to `--hitl-entries ...` and remove `--approval` |
| L420 (criterion #11) | "mirrors CI-5's 3-job structure" | Change to "4-job structure with rationale in ADR-021" |

---

### New Findings (2026-07-22 Re-Verification)

> All P0–P3 items remediated in commit `2b2b463` (2026-05-02). Low-priority items deferred to GitHub issues.

#### NEW-1: ~~Missing `advance_cursor.py` CI-6 job~~ ✅ Resolved

**Remediation:** Added 5th job `advance-cursor` to CI-6 with `if: always()` gating (`2b2b463`).

#### NEW-2: ~~AGENTS.md missing per-script rows for `create_issues.py` and `advance_cursor.py`~~ ✅ Resolved

**Remediation:** Added 2 per-script rows; fixed `fetch_content.py` row (`2b2b463`).

#### NEW-3: ~~Unsanitized `display_name` in Markdown body~~ ✅ Resolved

**Remediation:** Added `_sanitize_for_md()` helper to escape backticks and strip control characters (`2b2b463`).

#### NEW-4: ~~`unreachable` tracking_status — contract vs code mismatch~~ ✅ Resolved

**Remediation:** Added `"unreachable"` to both `_VALID_FILE_TRACKING_STATUSES` and `_VALID_FOLDER_TRACKING_STATUSES` (`2b2b463`).

#### NEW-5: ~~Spec success criterion #9 says "5 scripts" but pipeline has 6~~ ✅ Resolved

**Remediation:** Updated to "6 scripts plus 1 umbrella row" (`2b2b463`).

#### NEW-6: `version_segment` validation accepts hex for native format versions — Deferred

Defense-in-depth improvement. Tracked in GitHub issue #86.

#### NEW-7: No pagination limit on `list_changes` — Deferred

Low risk at current scale. Tracked in GitHub issue #87.

#### NEW-8: ~~`update_changes_cursor()` docstring ownership~~ ✅ Resolved

**Remediation:** Docstring updated to reference `advance_cursor.py` (`2b2b463`).

#### NEW-9: Concurrency group omits `${{ github.ref }}` suffix — Deferred

Low risk for schedule-only trigger. Tracked in GitHub issue #88.

#### NEW-10: ~~Filename logic duplicated between `_find_old_asset` and `_find_new_asset`~~ ✅ Resolved

**Remediation:** Replaced inline regex with `safe_filename()` import from `_validators.py` (`2b2b463`).

---

### Remediation Priority Order (Final — 2026-05-02)

All P0–P3 items resolved. Remaining deferred items tracked in GitHub issues:

| Priority | Items | Status |
|----------|-------|--------|
| P0 — Blocking | NEW-1, NEW-2 | ✅ All resolved |
| P1 — Security | HI-2 + NEW-10, HI-3 + NEW-3 | ✅ All resolved |
| P2 — Alignment | NEW-4, NEW-5 | ✅ All resolved |
| P3 — Housekeeping | HK-3, HK-5, HK-6, NEW-8, NEW-10 | ✅ All resolved |
| Deferred | HK-13 (#84), HK-15 (#85), NEW-6 (#86), NEW-7 (#87), NEW-9 (#88) | Tracked in GitHub issues |

> **All original P0–P2 items from 2025-07-15 were resolved previously** (CR-1 cursor code, CR-2 atomicity, CR-3 + HI-5 + HI-6 test files, ME-1 CI flags, ME-2 + ME-3 contracts, HI-1 credential leakage, ME-7 redaction, ME-10 injection).
