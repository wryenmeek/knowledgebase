# Metadata and Schema Governance Contract

This document is the authoritative contract for frontmatter semantics, optional
extension fields, schema evolution, and validation severity in `wiki/**`. It
builds on [`page-template.md`](page-template.md), stays consistent with
[`AGENTS.md`](../AGENTS.md), and references
[`taxonomy-contract.md`](taxonomy-contract.md) and
[`ontology-entity-contract.md`](ontology-entity-contract.md). Reserved
process/state artifacts also follow
[`governed-artifact-contract.md`](governed-artifact-contract.md) for path
ownership and write semantics.

## Baseline schema

Current deterministic tooling treats the following frontmatter keys as the
blocking baseline for wiki pages:

| Field | Semantics |
|---|---|
| `type` | Artifact role: `entity`, `concept`, `source`, `analysis`, or `process`. Must align with namespace/purpose. |
| `title` | Canonical display title for the page. |
| `status` | Lifecycle state: `active`, `superseded`, or `archived`. |
| `sources` | Canonical SourceRef list backing the page's claims. |
| `open_questions` | Explicit unresolved contradictions, gaps, or escalation needs. |
| `confidence` | Integer `1..5` indicating evidence strength, not author preference. |
| `sensitivity` | Handling level: `public`, `internal`, or `restricted`. |
| `updated_at` | ISO-8601 UTC timestamp for the last substantive page change. |
| `tags` | Normalized discovery tags governed by `taxonomy-contract.md`. |

## Optional extension fields

These fields are reserved and allowed when their semantics are needed:

| Field | Semantics | Current validation level |
|---|---|---|
| `browse_path` | Ordered taxonomy segments excluding namespace and page title. | Advisory unless a workflow explicitly depends on it. |
| `aliases` | Alternate names for the canonical subject. | Advisory unless identity resolution depends on it. |
| `entity_id` | Stable local identity key for entity pages across title/path changes. | Advisory until identity migration work requires it. |
| `schema_version` | Explicit page schema version. Omitted pages are interpreted as schema version `1`. | Advisory in v1. |

Unknown fields are not automatically forbidden, but they must be documented here
before they are used as shared contracts across agents or scripts.

## Body-structure semantics

When present, the following body sections have stable meaning:

- `## Summary`: brief synthesis of the page subject.
- `## Aliases`: non-canonical names for the same subject only.
- `## Relationships`: controlled-vocabulary links to other canonical pages.
- `## Evidence`: SourceRef-backed support statements.
- `## Open Questions`: unresolved items that block or qualify certainty.

## Schema evolution rules

1. **Additive first.** New fields start as optional and advisory.
2. **Document before use.** Any shared field or section meaning must be added to
   this contract and, when relevant, to `page-template.md` before agents rely on
   it.
3. **Backwards-compatible rollout.** Tooling should ignore unknown optional
   fields until validators and migrations are updated deliberately.
4. **Breaking changes require an ADR.** Renaming/removing required keys, changing
   enum meaning, or making an optional field required needs an ADR, migration
   plan, and test updates before landing.
5. **No silent reinterpretation.** Existing field names must keep their meaning;
   semantic drift counts as a schema change.

## Validation severity

### Blocking validation in the current deterministic MVP gates

- Missing any baseline required field.
- Index-generation inputs leave required scalar metadata empty for `title`,
  `status`, `confidence`, or `updated_at`.

### Blocking validation in authoritative governance mode

- In authoritative mode, SourceRefs must resolve to non-symlinked,
  allowlisted repo-local raw artifacts after path resolution, reject
  placeholder/sentinel git SHAs, resolve `git_sha` to a real git revision,
  prove that revision contains the cited path, and match recomputed `sha256`
  bytes from that revision's artifact content. This stricter gate applies only
  when a workflow explicitly opts into authoritative mode after commit-bound
  provenance is available; canonical-shape validation still applies everywhere
  else, including provisional ingest-time SourceRefs.
- Machine-readable ingest outputs must make provisional provenance explicit with
  structured fields such as `provenance.status: provisional`,
  `provenance.authoritative: false`, and a review-mode marker that signals
  authoritative reconciliation is still pending. These markers describe intake
  state; they do not by themselves satisfy authoritative review mode.
- Invalid enum/value domain for `type`, `status`, `sensitivity`, or `confidence`.
- `updated_at` is missing or not a valid ISO-8601 UTC timestamp.
- Page metadata contradicts namespace or canonical identity rules.
- An unresolved schema-version migration would cause different readers to
  interpret the same field differently.

### Advisory validation

- Reserved optional fields are omitted.
- Optional fields are present but under-specified for downstream use.
- Tags, aliases, or browse paths are valid but low quality.
- A page could benefit from a `schema_version` stamp or structured relationships
  before future automation scales.

## Change-control expectations

- Keep write-capable automation fail-closed for blocking metadata errors.
- Pair metadata contract changes with deterministic validator/test updates when
  enforcement behavior changes.
- Do not mutate historical meaning in `wiki/log.md`; record schema-related state
  changes as new log events instead.
