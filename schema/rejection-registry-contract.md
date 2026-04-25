# Rejection Registry Contract

This document is the authoritative schema contract for rejection records in
`raw/rejected/`. These files provide persistent organizational memory of source material
that was evaluated for intake and rejected. See
`docs/decisions/ADR-013-rejected-source-registry.md` for the governing architectural
decision.

## Scope and authority

- Applies to all `raw/rejected/*.rejection.md` artifacts.
- Governs field semantics, filename scheme, identity key, write-once semantics, and lock
  requirements.
- Declaring a path pattern here does **not** by itself grant write permission. Writers
  remain deny-by-default until `AGENTS.md` explicitly names the surface.

## File naming convention

```
raw/rejected/<slugified-source-name>--<sha256-prefix-8>.rejection.md
```

- `slugified-source-name`: lowercase, alphanumeric, hyphen-separated. Derived from the
  original source filename or title. No underscores, slashes, or dots.
- `sha256-prefix-8`: first 8 characters of the SHA-256 hex digest of the source bytes.

### Slug validation

The slug component must satisfy all of the following:

- Match the regular expression `[a-z0-9]([a-z0-9-]*[a-z0-9])?` (starts and ends
  alphanumeric, hyphens only in the middle).
- Maximum length: 64 characters (excluding the `--<sha256-prefix-8>` suffix).
- Must not contain path separators (`/`, `\`), parent traversal (`..`), or null bytes.
- Source filenames that produce an empty or invalid slug after sanitization must fail
  closed — the operator provides a manual slug.
- Slug collisions (same slug + same sha256-prefix-8 but different full sha256) must fail
  closed. The 8-character prefix provides sufficient entropy for practical use; true
  collisions require operator resolution.

Examples:
- `raw/rejected/cms-manual-chapter-4--a1b2c3d4.rejection.md`
- `raw/rejected/provider-enrollment-guide--deadbeef.rejection.md`

## Record format

Each rejection record is a Markdown file with YAML frontmatter.

### Frontmatter (required fields)

```yaml
---
slug: <slugified-source-name>
sha256: <full-64-hex-char-sha256-of-source-bytes>
rejected_date: <ISO-8601 datetime, e.g. 2025-07-16T14:30:00Z>
source_path: <original path in raw/inbox/, e.g. raw/inbox/some-document.pdf>
rejection_reason: <brief human-readable description>
rejection_category: <one of the allowed categories>
reviewed_by: <operator username or agent identifier>
reconsidered_date: null
---
```

### Body sections (required)

```markdown
# <Source Title or Filename>

## What was attempted
<Brief description of what was submitted and what intake was expected to produce>

## What was missing
<Specific deficiencies that caused rejection — missing provenance, unsupported format, etc.>

## Notes
<Any additional context, operator comments, or references to related sources>
```

## Field semantics

| Field | Type | Required | Description |
|---|---|---|---|
| `slug` | string | Yes | Slugified source name. Lowercase, alphanumeric, hyphen-separated. |
| `sha256` | string (64 hex chars) | Yes | SHA-256 checksum of the original source bytes. Canonical identity key for deduplication. |
| `rejected_date` | ISO-8601 datetime | Yes | When the rejection decision was made. |
| `source_path` | string | Yes | Original path in `raw/inbox/` at time of evaluation. Informational only — not used for deduplication (paths change on re-submission). |
| `rejection_reason` | string | Yes | Human-readable summary of why the source was rejected. |
| `rejection_category` | enum | Yes | One of: `provenance_missing`, `format_unsupported`, `duplicate`, `out_of_scope`, `quality_insufficient`. |
| `reviewed_by` | string | Yes | Identifier of the operator or agent that made the rejection decision. |
| `reconsidered_date` | ISO-8601 datetime or null | Yes | Initially `null`. Set to a datetime when an operator invokes `reconsider-rejected-source`. The only mutable field. |

## Rejection categories

| Category | Description | Example |
|---|---|---|
| `provenance_missing` | Source lacks sufficient attribution, authorship, or chain-of-custody information. | PDF with no author, date, or publisher. |
| `format_unsupported` | Source format cannot be processed by the ingest pipeline. | Binary executable, encrypted archive. |
| `duplicate` | Source content (by sha256) already exists in `raw/processed/` or another rejected record. | Re-submission of already-ingested material. |
| `out_of_scope` | Source content is outside the knowledgebase's subject domain. | Unrelated policy document. |
| `quality_insufficient` | Source is within scope but quality is too low for reliable synthesis. | Heavily redacted document, machine-translated with errors. |

## Deduplication rules

- Identity is determined by `sha256` only — **not** by filename, slug, or path.
- Before writing a new rejection record, the writer MUST check all existing records in
  `raw/rejected/` for a matching `sha256` field.
- If a record with the same `sha256` already exists, the write MUST fail closed — do not
  overwrite, do not create a second record.
- If the same bytes arrive via a different filename or path, they match the existing
  rejection by sha256.

## Re-submission behavior

- When an operator invokes `reconsider-rejected-source`, the existing record's
  `reconsidered_date` field is updated.
- The source is moved back to `raw/inbox/` and re-enters the full intake pipeline.
- A new rejection of the same source (same sha256) after reconsideration creates a new
  rejection record only if the source bytes have changed (different sha256). If the bytes
  are identical, the writer must fail closed because the sha256 match still exists.

## Write semantics

| Property | Value |
|---|---|
| Mutability | Write-once; immutable after creation except for `reconsidered_date`. |
| Write strategy | Exclusive create (fail if file already exists) for new records; atomic field update for `reconsidered_date`. |
| Authorized creator | `log-intake-rejection` skill surface only. |
| Authorized updater | Operator following the `reconsider-rejected-source` doc-only workflow (manual frontmatter edit under `raw/.rejection-registry.lock`). |
| Deletion | Not automated. Requires explicit Human Steward sign-off and a `wiki/log.md` audit entry. |
| Schema owner | `schema/rejection-registry-contract.md` (this document). |

## Lock requirements

| Property | Value |
|---|---|
| Lock path | `raw/.rejection-registry.lock` |
| Lock semantics | Same acquire/release semantics as `wiki/.kb_write.lock` per ADR-005. |
| Scope | Must be acquired before any write to `raw/rejected/`. |
| Ordering | No ordering relationship with `wiki/.kb_write.lock` — rejection writes do not touch wiki paths. |
| Failure mode | If the lock is unavailable, the write MUST fail closed. |
