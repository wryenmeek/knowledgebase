# Drift Report Contract

**Schema version:** 1  
**Produced by:** `scripts/github_monitor/check_drift.py`  
**Consumed by:** `scripts/github_monitor/fetch_content.py`, `scripts/github_monitor/synthesize_diff.py`  
**Governed by:** ADR-012 GitHub Source Monitoring

---

## Purpose

The drift report is the machine-readable handoff artifact between the Phase 1
read-only detection job and the Phase 2/3 write jobs in CI-5.  It records
which monitored files have changed (drifted) since their last applied ingest,
which are up-to-date, which are awaiting first ingest (uninitialized), and
which could not be checked due to API or configuration errors.

The report is a transient CI artifact (uploaded as a GitHub Actions artifact
with 7-day retention) — it is **not** a governed repository write.

---

## Top-level JSON schema

```json
{
  "version": "1",
  "generated_at": "2024-01-01T00:00:00.000000+00:00",
  "registry": "raw/github-sources/some-org-some-repo.source-registry.json",
  "has_drift": true,
  "drifted": [...],
  "up_to_date": [...],
  "uninitialized": [...],
  "errors": [...]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `version` | string | ✅ | Schema version; must equal `"1"`. |
| `generated_at` | string (ISO 8601) | ✅ | UTC timestamp when the report was produced. |
| `registry` | string | ✅ | Repo-relative path of the registry file (or a summary when multiple). |
| `has_drift` | boolean | ✅ | `true` if the `drifted` array is non-empty. |
| `drifted` | array of DriftedEntry | ✅ | Entries where current blob SHA ≠ last applied blob SHA. |
| `up_to_date` | array of UpToDateEntry | ✅ | Entries where current blob SHA matches last applied blob SHA. |
| `uninitialized` | array of UninitializedEntry | ✅ | Entries with `tracking_status: uninitialized` (never ingested). |
| `errors` | array of ErrorEntry | ✅ | Entries that could not be checked; report status is `fail` when non-empty. |

---

## DriftedEntry

```json
{
  "owner": "some-org",
  "repo": "some-repo",
  "path": "path/to/file.md",
  "current_commit_sha": "abc123def456...",
  "current_blob_sha": "deadbeef...",
  "last_applied_commit_sha": "old123...",
  "last_applied_blob_sha": "oldblob...",
  "compare_url": "https://github.com/some-org/some-repo/compare/old123...abc123d",
  "lines_added": 5,
  "lines_removed": 2,
  "is_binary": false,
  "file_size_bytes": 1234
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `owner` | string | ✅ | GitHub organisation or user name. |
| `repo` | string | ✅ | GitHub repository name. |
| `path` | string | ✅ | Repo-relative file path in the external repo. |
| `current_commit_sha` | string (40-char hex) | ✅ | HEAD commit SHA for this file. |
| `current_blob_sha` | string | ✅ | Blob SHA from the GitHub contents API. |
| `last_applied_commit_sha` | string \| null | ✅ | Commit SHA at last successful wiki update; null if unknown. |
| `last_applied_blob_sha` | string \| null | ✅ | Blob SHA at last successful wiki update. |
| `compare_url` | string \| null | ✅ | GitHub compare URL (`old...new`) for human review; null if no prior SHA. |
| `lines_added` | integer \| null | ⚪ optional | Lines added vs. last applied asset. Null if metrics unavailable (binary, missing prior asset, oversized, or decode failure). |
| `lines_removed` | integer \| null | ⚪ optional | Lines removed vs. last applied asset. Same null semantics as `lines_added`. |
| `is_binary` | boolean \| null | ⚪ optional | `true` if the *current* file appears binary (null byte in first 8000 bytes); `false` if current is text (even if prior was binary). Null if content unavailable. |
| `file_size_bytes` | integer \| null | ⚪ optional | Current file size in bytes. Null if content was not available. |

---

## UpToDateEntry

```json
{
  "owner": "some-org",
  "repo": "some-repo",
  "path": "path/to/file.md",
  "blob_sha": "deadbeef..."
}
```

| Field | Type | Description |
|---|---|---|
| `owner` | string | GitHub organisation or user name. |
| `repo` | string | GitHub repository name. |
| `path` | string | Repo-relative file path. |
| `blob_sha` | string | Current blob SHA (matches `last_applied_blob_sha`). |

---

## UninitializedEntry

```json
{
  "owner": "some-org",
  "repo": "some-repo",
  "path": "path/to/new-file.md",
  "tracking_status": "uninitialized"
}
```

These entries require manual operator action: complete the initial ingest via
the `raw/inbox/ → raw/processed/` pipeline, then set `tracking_status: active`
and populate `last_applied_*` fields in the registry.

| Field | Type | Description |
|---|---|---|
| `owner` | string | GitHub organisation or user name. |
| `repo` | string | GitHub repository name. |
| `path` | string | Repo-relative file path. |
| `tracking_status` | string | Always `"uninitialized"`. |

---

## ErrorEntry

```json
{
  "path": "path/to/file.md",
  "reason_code": "unreachable",
  "message": "GitHub API request failed: 404 Not Found"
}
```

| Field | Type | Description |
|---|---|---|
| `path` | string | File path from the registry entry (or the registry path on parse error). |
| `reason_code` | string | A value from `GitHubMonitorReasonCode`; see `scripts/kb/contracts.py`. |
| `message` | string | Human-readable description of the error. |

### Reason codes for errors

| Code | Meaning |
|---|---|
| `unreachable` | GitHub API returned 401, 403, or 404 for this file. |
| `fetch_failed` | Network error, 5xx after retries, invalid API shape, or path validation failure. |

---

## Validation

`validate_drift_report(data)` in `scripts/github_monitor/_types.py` checks:

- All required top-level keys are present.
- `version == "1"`.
- `has_drift` is a boolean.
- `drifted`, `up_to_date`, `uninitialized`, `errors` are arrays.

Callers that consume the report (Phase 2/3 scripts) must call
`validate_drift_report()` before using any field.  A malformed report is a
hard failure — do not process a partial report.

---

## Governance

- This is a **transient artifact** — it is not committed to the repository.
- It is uploaded as a GitHub Actions artifact with 7-day retention.
- It does not require a write lock or approval because it is not a governed
  repository path.
- The `scripts/github_monitor/check_drift.py` write-surface matrix row in
  `AGENTS.md` is declared as `read-only only` because the output file is
  written to a caller-specified CI workspace path, not to a governed path.
