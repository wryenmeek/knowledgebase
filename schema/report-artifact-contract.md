# Report Artifact Contract

This document is the authoritative schema contract for durable report artifacts
written to `wiki/reports/`. It governs the JSON envelope, required and
type-specific fields, filename convention, and write semantics for all
approval-gated reporting surfaces.

Scripts in `scripts/reporting/**` must satisfy this contract before any
`wiki/reports/**` write is permitted. Path ownership and lock rules are
inherited from [`governed-artifact-contract.md`](governed-artifact-contract.md).

## Scope and authority

- Applies to every JSON artifact written under `wiki/reports/`.
- Script surfaces that write report artifacts must list this file as their
  schema owner in the AGENTS.md write-surface matrix row.
- Report artifacts are write-once: each approved run creates a new
  timestamped file; prior runs are never mutated.
- No artifact under `wiki/reports/**` may be created outside an explicitly
  declared narrower script/workflow contract (deny-by-default).

## Filename convention

```
wiki/reports/<report_type>-<YYYY-MM-DD>.json
```

`report_type` must be a lowercase, hyphen-separated identifier matching the
value of the `report_type` field in the artifact. Example:

```
wiki/reports/quality-scores-2026-04-19.json
wiki/reports/content-quality-2026-04-19.json
```

Multiple runs on the same calendar day append a suffix counter:
`wiki/reports/<report_type>-<YYYY-MM-DD>-<n>.json` where `<n>` starts at `2`.

## Common envelope (all report types)

Every artifact written under `wiki/reports/` must include these top-level
fields:

| Field | Type | Required | Semantics |
|---|---|---|---|
| `report_type` | string | yes | Identifier for the report class. Must match the filename prefix. One of: `quality-scores`, `content-quality`. |
| `generated_at` | string | yes | ISO-8601 UTC timestamp of when the report was produced (e.g., `"2026-04-19T01:23:00Z"`). |
| `scope` | array of strings | yes | Repo-relative glob patterns or explicit paths that were analyzed (e.g., `["wiki/**/*.md"]`). |
| `surface` | string | yes | The script surface that produced this artifact (e.g., `"scripts/reporting/quality_runtime.py"`). |
| `findings` | array of objects | yes | Per-item findings. May be empty (`[]`) when no pages matched scope. Shape varies by `report_type` — see type-specific sections below. |
| `summary` | object | yes | Aggregate counts and metadata for the run. Shape varies by `report_type`. |

An artifact with any missing required field is malformed and must not be
written; the producing script must fail closed.

## Type-specific schemas

### `quality-scores` (from `quality_runtime.py score-update`)

Produced by `scripts/reporting/quality_runtime.py` in `score-update` mode.
Captures computed priority scores and quality signals per wiki page.

**`findings` item fields:**

| Field | Type | Required | Semantics |
|---|---|---|---|
| `page_path` | string | yes | Repo-relative path to the analyzed wiki page. |
| `priority_score` | integer | yes | Computed prioritization score (higher = higher curation priority). Non-negative. |
| `confidence` | integer or null | yes | Raw `confidence` frontmatter value, or `null` if absent. |
| `missing_sources` | boolean | yes | Whether the page lacks a `sources` frontmatter field. |
| `missing_updated_at` | boolean | yes | Whether the page lacks an `updated_at` frontmatter field. |
| `placeholder_count` | integer | yes | Number of unresolved placeholder markers in the page body. |
| `missed_query_count` | integer | yes | Number of queries that targeted this page but got no result. |
| `missed_query_demand` | integer | yes | Aggregate demand weight from missed queries targeting this page. |
| `recommended_next_step` | string | yes | Human-readable recommendation for the highest-value curation action. |

**`summary` fields:**

| Field | Type | Required | Semantics |
|---|---|---|---|
| `selected_count` | integer | yes | Number of pages included in the analysis. |
| `prioritized_count` | integer | yes | Number of pages with `priority_score > 0`. |
| `query_evidence_count` | integer | yes | Number of query-evidence entries consumed. |
| `recommendation_only` | boolean | yes | Must be `false` for `score-update` artifacts. |
| `scoring_mode` | string | yes | Must be `"score-update"` for this report type. |

### `content-quality` (from `content_quality_report.py persist`)

Produced by `scripts/reporting/content_quality_report.py` in `persist` mode.
Captures structural quality signals per wiki page.

**`findings` item fields:**

| Field | Type | Required | Semantics |
|---|---|---|---|
| `path` | string | yes | Repo-relative path to the analyzed wiki page. |
| `missing_sources` | boolean | yes | Whether the page lacks a `sources` frontmatter field. |
| `missing_updated_at` | boolean | yes | Whether the page lacks an `updated_at` frontmatter field. |
| `placeholder_count` | integer | yes | Number of unresolved placeholder markers in the page body. |

**`summary` fields:**

| Field | Type | Required | Semantics |
|---|---|---|---|
| `selected_count` | integer | yes | Number of pages included in the analysis. |
| `missing_sources_count` | integer | yes | Number of pages missing `sources`. |
| `missing_updated_at_count` | integer | yes | Number of pages missing `updated_at`. |
| `placeholder_file_count` | integer | yes | Number of pages with at least one placeholder. |

## Write semantics

- **Write-once**: each approved run produces a new timestamped file; existing
  report artifacts are never mutated.
- **Lock required**: `wiki/.kb_write.lock` must be held before writing any
  artifact (ADR-005 concurrency rules apply).
- **Fail closed**: if the computed artifact would be malformed (missing required
  fields, type mismatch), the script must abort without writing.
- **Empty findings permitted**: an artifact with `"findings": []` is valid and
  may be written when the scope contains no matching pages; this is a normal
  no-findings outcome, not an error.

## Validation expectations

Scripts must validate the outgoing artifact against this contract before
writing. At minimum:

1. All common envelope fields are present and correctly typed.
2. `report_type` matches the filename prefix.
3. Every `findings` item contains all required type-specific fields.
4. `summary` contains all required type-specific fields.
5. `generated_at` is a valid ISO-8601 timestamp string.

Validators in `tests/kb/` must assert that persisted artifacts conform to this
contract and that scripts fail closed on malformed output.
