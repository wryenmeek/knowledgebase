# GitHub Source Registry Contract

This document is the authoritative schema contract for
`raw/github-sources/{owner}-{repo}.source-registry.json` files. These files govern
how the knowledgebase monitors a specific external GitHub repository for source-material
changes. See `docs/decisions/ADR-012-github-source-monitoring.md` for the governing
architectural decision.

## Scope and authority

- Applies to all `raw/github-sources/*.source-registry.json` artifacts.
- Governs field semantics, the `tracking_status` state machine, the three-stage state
  fields, write semantics, and lock requirements.
- Declaring a path pattern here does **not** by itself grant write permission. Writers
  remain deny-by-default until `AGENTS.md` explicitly names the surface.

## File naming convention

```
raw/github-sources/{owner}-{repo}.source-registry.json
```

Examples:
- `raw/github-sources/cms-gov-regulations-and-guidance.source-registry.json`
- `raw/github-sources/some-org-policy-docs.source-registry.json`

Slugs must be lowercase, alphanumeric, and hyphen-separated. No underscores, slashes,
or dots other than the `.source-registry.json` suffix.

## JSON schema

```json
{
  "version": "1",
  "owner": "some-org",
  "repo": "some-repo",
  "github_app_installation_id": 12345678,
  "entries": [
    {
      "path": "path/to/file.md",
      "tracking_status": "active",
      "last_applied_commit_sha": "abc123def456...",
      "last_applied_blob_sha": "deadbeef...",
      "last_applied_at": "2024-01-01T00:00:00Z",
      "last_fetched_commit_sha": null,
      "last_fetched_blob_sha": null,
      "sha256_at_last_fetched": null,
      "sha256_at_last_applied": "64hexchars...",
      "wiki_page": "wiki/pages/topical/my-source-page.md",
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
| `owner` | string | Yes | GitHub organization or user name that owns the external repo. |
| `repo` | string | Yes | GitHub repository name (no slashes). |
| `github_app_installation_id` | integer | Yes | Installation ID of the GitHub App authorized for this owner. |
| `entries` | array | Yes | One entry per tracked file path. |

### Entry fields

| Field | Type | Required | Description |
|---|---|---|---|
| `path` | string | Yes | Repo-relative file path within the external repo (e.g. `docs/guidance.md`). Must not start with `/`, contain `..`, or contain URL-encoded traversal sequences. |
| `tracking_status` | string enum | Yes | Current monitoring state; see below. |
| `last_applied_commit_sha` | string\|null | Yes | Full commit SHA of the last upstream commit whose content was applied to the wiki page. `null` if this entry has never been applied. |
| `last_applied_blob_sha` | string\|null | Yes | Git blob SHA of the file at `last_applied_commit_sha`. Used as the primary drift-detection key. `null` if never applied. |
| `last_applied_at` | ISO 8601 string\|null | Yes | Timestamp when the last successful wiki-page update was written. `null` if never applied. |
| `last_fetched_commit_sha` | string\|null | Yes | Full commit SHA from the most recent successful `fetch_content.py` run. Differs from `last_applied_commit_sha` when a fetch succeeded but synthesis has not yet run. `null` if no fetch has occurred since last applied. |
| `last_fetched_blob_sha` | string\|null | Yes | Blob SHA from the most recent successful fetch. `null` if no fetch since last applied. |
| `sha256_at_last_fetched` | 64-hex string\|null | Yes | SHA-256 of the raw bytes fetched during the last successful fetch. `null` if no fetch since last applied. |
| `sha256_at_last_applied` | 64-hex string\|null | Yes | SHA-256 of the raw bytes that were applied to the wiki page. `null` if never applied. |
| `wiki_page` | string\|null | Yes | Repo-relative path to the wiki page this entry maps to (e.g. `wiki/pages/topical/my-page.md`). `null` for `uninitialized` entries awaiting first ingest. |
| `notes` | string | No | Free-text operator notes. Not used by automation. |

## `tracking_status` enum

| Value | Meaning |
|---|---|
| `active` | Entry is actively monitored; included in drift checks. |
| `paused` | Entry is temporarily skipped during drift checks. `last_applied_*` and `last_fetched_*` are preserved. |
| `archived` | Entry will no longer be monitored; treated as permanently inactive. |
| `unreachable` | The last drift check could not reach the upstream file (API 404/403/5xx after retries). Operator must investigate; entry is skipped until manually reset to `active`. |
| `uninitialized` | Entry has been added to the registry but no wiki page exists yet. `check_drift.py` emits `UNINITIALIZED_SOURCE` for these entries and writes a handoff artifact to `raw/github-sources/.pending-ingest/`. Operator must run the file-based ingest pipeline to create the initial wiki page, then set `wiki_page` and advance `tracking_status` to `active`. |

## Three-stage state machine

The three-stage state prevents silent provenance loss if fetching succeeds but wiki
synthesis fails:

```
┌─────────────────────────────────────────────────────────┐
│  Stage 1: check_drift.py (read-only)                    │
│  Compares current blob SHA vs last_applied_blob_sha.    │
│  No registry writes.                                    │
└─────────────────────────────────────────────────────────┘
            ↓ drift detected
┌─────────────────────────────────────────────────────────┐
│  Stage 2: fetch_content.py                              │
│  Fetches bytes → raw/assets/{owner}/{repo}/{sha}/{path} │
│  Advances: last_fetched_commit_sha                      │
│            last_fetched_blob_sha                        │
│            sha256_at_last_fetched                       │
│  Does NOT touch: last_applied_* fields                  │
└─────────────────────────────────────────────────────────┘
            ↓ fetch succeeded
┌─────────────────────────────────────────────────────────┐
│  Stage 3: synthesize_diff.py                            │
│  Applies diff-aware update to wiki page.                │
│  Only on success: advances last_applied_commit_sha      │
│                              last_applied_blob_sha      │
│                              last_applied_at            │
│                              sha256_at_last_applied     │
│  Resets: last_fetched_* to null                         │
└─────────────────────────────────────────────────────────┘
```

If synthesis fails mid-run, the next CI-5 run sees `last_fetched_blob_sha ≠ null` and
`last_applied_blob_sha ≠ last_fetched_blob_sha`, so it can retry synthesis using the
already-fetched asset rather than re-fetching.

## Write semantics

| Property | Value |
|---|---|
| Mutability | Mutable; may be updated by `fetch_content.py` and `synthesize_diff.py` |
| Write strategy | Atomic replace under lock |
| Lock path | `raw/.github-sources.lock` |
| Lock requirement | Lock must be acquired before any write; fail closed on lock unavailability |
| Schema owner | `schema/github-source-registry-contract.md` (this document) |
| Governed artifact contract | `scripts/kb/contracts.py` → artifact ID `github-source-registry` |

Writers must:
1. Read the full registry JSON under the lock.
2. Mutate only the target entry's relevant fields.
3. Write the full updated JSON as an atomic replace (not in-place patch).
4. Release the lock.

## Lock ordering

When `synthesize_diff.py` requires both `wiki/.kb_write.lock` AND `raw/.github-sources.lock`,
always acquire in this order to prevent deadlocks:

1. Acquire `wiki/.kb_write.lock` first.
2. Acquire `raw/.github-sources.lock` second.

## Extension rules

New registry fields must:
1. Add a row to the entry field table above.
2. Be backward-compatible (add-only; no field removals or renames).
3. Include `null` as an allowed value for optional fields.
4. Bump schema `version` only for breaking changes.
