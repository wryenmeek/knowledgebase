# Wiki Processing Checkpoint Registry Contract

This document is the authoritative schema contract for
`raw/wiki-processing/wiki-processing-checkpoint-registry.json`. The registry records
batch-level and item-level recovery state for generated wiki processing artifacts.
See `docs/decisions/ADR-026-wiki-processing-checkpoint-registry.md` and
`docs/decisions/ADR-027-infrastructure-validation-trigger-model.md` for the governing
architecture.

## Scope and authority

- Applies only to `raw/wiki-processing/wiki-processing-checkpoint-registry.json`.
- Governs field semantics, artifact identity, `source_fingerprints`, batch and item
  state machines, trigger-specific transitions, bootstrap classification, retention
  constants, lock ordering, and fail-closed behavior.
- Declaring this artifact here does not grant write permission. Writers remain
  deny-by-default until `AGENTS.md` declares the runtime surface.
- Checkpoint state is observational, not authoritative. No registry entry may authorize
  a write that policy, validation, provenance, or write-surface rules would block.

## JSON schema

```json
{
  "version": "1",
  "source_fingerprints": {
    "wiki/sources/example.md": "64hexchars..."
  },
  "batches": [
    {
      "batch_id": "2026-06-08T00:00:00Z-ci3",
      "trigger": "intake_driven",
      "triggered_by": "commit-sha-or-workflow-run-id-placeholder",
      "started_at": "2026-06-08T00:00:00Z",
      "finished_at": null,
      "status": "running",
      "input_fingerprint": "64hexchars...",
      "error_summary": null
    }
  ],
  "items": [
    {
      "item_key": "wiki_entity_page:entity:example",
      "output_path": "wiki/entities/example.md",
      "path_aliases": [],
      "artifact_type": "wiki_entity_page",
      "source_fingerprint": "64hexchars...",
      "dependency_fingerprint": "64hexchars...",
      "status": "pending",
      "last_attempted_at": null,
      "last_succeeded_at": null,
      "last_error": null,
      "last_successful_batch_id": null
    }
  ]
}
```

## Top-level fields

| Field | Type | Required | Description |
|---|---|---|---|
| `version` | `"1"` string | Yes | Schema version. Must be exactly `"1"`. |
| `source_fingerprints` | object map | Yes | Map of source path to SHA-256 digest. Keys are repo-relative source paths. Values are 64-hex SHA-256 strings over the source bytes or normalized source representation used by the producing stage. |
| `batches` | array | Yes | Batch records in chronological append order. |
| `items` | array | Yes | One entry per tracked generated artifact item. |

`source_fingerprints` is the canonical source-change input for item
`source_fingerprint` values. Source pages and raw source artifacts may appear in this
map even when they are excluded from checkpoint `items`.

## Batch fields

| Field | Type | Required | Description |
|---|---|---|---|
| `batch_id` | string | Yes | Stable run identifier. Must be unique within `batches`. |
| `trigger` | string enum | Yes | One of `intake_driven`, `infrastructure_revalidation`, or `manual_rescan`. This three-value enum is the authoritative trigger vocabulary per ADR-026 § Amendment and ADR-027; the original ADR-026 Decision text listing `automatic` is superseded. |
| `triggered_by` | string | Yes | Commit SHA, workflow run identifier, or operator-supplied trigger source for diagnostics. Introduced by this PR2 schema — the original ADR-026 `### State model` Batch-fields list did not enumerate it; this addition is non-breaking and is recorded under ADR-026 § Amendment. For batches that retry, resume, or rescan prior work, set `triggered_by` to `retry-of:<prior-batch-id>`, `resume-of:<prior-batch-id>`, or `rescan-of:<prior-batch-id>` respectively so that lineage is recoverable from diagnostic text. Structured `parent_batch_id` linkage is intentionally deferred (MVP records only `last_successful_batch_id` for items); revisit if MVP feedback shows the prose convention is insufficient. |
| `started_at` | ISO 8601 string | Yes | Timestamp when the batch started. |
| `finished_at` | ISO 8601 string or null | Yes | Timestamp when the batch reached a terminal batch status. `null` while running. |
| `status` | string enum | Yes | Batch state. See Batch state machine. |
| `input_fingerprint` | 64-hex string | Yes | Digest over the source and dependency set relevant to the batch. |
| `error_summary` | string or null | Yes | Required diagnostic text for `failed` or `partial`; `null` for `running` and `completed`. |

## Item fields

| Field | Type | Required | Description |
|---|---|---|---|
| `item_key` | string | Yes | Canonical identity key. This is not equal to `output_path`. |
| `output_path` | string | Yes | Current repo-relative materialized output path. Must resolve inside an allowed wiki namespace for the artifact type. |
| `path_aliases` | array of strings | Yes | Prior output paths retained for rename and move continuity. |
| `artifact_type` | string enum | Yes | One of `wiki_entity_page`, `wiki_concept_page`, or `wiki_analysis_page`. |
| `source_fingerprint` | 64-hex string | Yes | Digest derived from `source_fingerprints` entries that materially support the item. |
| `dependency_fingerprint` | 64-hex string | Yes | Digest over non-source dependencies that can affect the item's generated output. |
| `status` | string enum | Yes | Item state. See Item state machine. |
| `last_attempted_at` | ISO 8601 string or null | Yes | Last time a batch attempted this item. |
| `last_succeeded_at` | ISO 8601 string or null | Yes | Last time the item completed successfully. |
| `last_error` | string or null | Yes | Most recent processing error or manual retirement rationale. Only the most recent error is retained; older errors are overwritten on each new attempt. This single-slot semantic supersedes ADR-026 § State transitions ("retries must retain prior `last_error` history"). Cross-batch error provenance is preserved through the immutable batch records (each batch's `error_summary` plus its `started_at`/`finished_at` window) and the per-item `last_attempted_at`/`last_successful_batch_id` pair, so historical errors remain recoverable from the registry without per-item error arrays. |
| `last_successful_batch_id` | string or null | Yes | Batch ID that last moved the item to `completed`. |

## Artifact identity

| artifact_type | Included paths | item_key derivation | Rename and move behavior | Exclusions |
|---|---|---|---|---|
| `wiki_entity_page` | `wiki/entities/*.md` | Use frontmatter `entity_id` when present; otherwise use the normalized canonical slug per `schema/ontology-entity-contract.md`. Prefix the key with `wiki_entity_page:`. | Keep `item_key`, update `output_path`, append the previous path to `path_aliases`. | Ambiguous entity IDs, duplicate aliases, or unresolved split/merge candidates fail closed. |
| `wiki_concept_page` | `wiki/concepts/*.md` | Use the normalized canonical slug. Prefix the key with `wiki_concept_page:`. | Keep `item_key`, update `output_path`, append the previous path to `path_aliases`. | Concepts do not use `entity_id`; conflicting slugs fail closed. |
| `wiki_analysis_page` | `wiki/analyses/*.md` | Use the filename stem, including the 16-character query fingerprint produced by `scripts.kb.persist_query.analysis_fingerprint()`. Prefix the key with `wiki_analysis_page:`. | Analyses are not renamed in place; changing the filename changes identity. | Analysis paths without the required fingerprint suffix fail closed. |

If the canonical identity itself changes (for example, a corrected `entity_id` or a
re-slugged concept), do not mutate `item_key` in place. Instead:

1. Create a new item under the replacement `item_key` (with its own `output_path` and
   fingerprints) so future runs continue under the corrected identity.
2. Mark the prior item `skipped` with `last_error` documenting the replacement key
   (for example, `"superseded by wiki_entity_page:medicare-part-c-mapd"`).
3. Leave the prior key in the registry as the historical alias record so orphaned
   identities are explicit and auditable.

This rule applies to identity changes; pure path renames continue to use the
"keep `item_key`, update `output_path`, append the previous path to `path_aliases`"
behavior in the table above.

Excluded artifact families:

- `wiki/sources/**` are source projections, not generated checkpoint items. Their content
  hashes may still appear in `source_fingerprints`.
- Fixed governed artifacts such as `wiki/index.md`, `wiki/log.md`, `wiki/status.md`,
  `wiki/open-questions.md`, and `wiki/backlog.md` have separate contracts.
- `wiki/reports/**` are governed report artifacts with separate persistence rules.

On key collision, path escape, source mismatch, or ambiguous mapping, runtime must fail
closed and require manual resolution before advancing affected item state.

## Batch state machine

| Current | Allowed next | Condition |
|---|---|---|
| `running` | `completed` | Every planned item reached a terminal successful or intentionally skipped state and no batch-level failure occurred. |
| `running` | `partial` | At least one item completed, but at least one planned item remains non-terminal or failed. |
| `running` | `failed` | Batch-level prerequisite, lock, schema, parse, provenance, or write failure prevents reliable continuation. |

`completed`, `partial`, and `failed` are terminal for the batch record they describe.
No runtime may silently rewrite a terminal batch record, and no in-place transition
back to `running` is permitted. Retry, resume, and rescan are represented by
appending a new batch record with `status: running` (linked to prior batches via
`triggered_by` or `error_summary` diagnostic text where useful) and updating only
item-level state.

## Item state machine

| Current | Allowed next | Condition |
|---|---|---|
| `pending` | `in_progress` | A batch claims the item under the required lock. |
| `in_progress` | `completed` | Expected final output exists, validates, and source/dependency fingerprints match. |
| `in_progress` | `stale` | One-hour stale timeout expires, expected state is missing, or output no longer matches expected fingerprints. |
| `in_progress` | `failed` | Hard processing error, write denial, schema mismatch, deterministic validator failure, or rollback failure. |
| `completed` | `stale` | Source or dependency fingerprints changed. |
| `stale` | `in_progress` | A new automatic run or manual rescan takes over the item. |
| `failed` | `in_progress` | A later retry explicitly attempts the item. The `last_error` field is overwritten with the new attempt's error (or cleared on success); only the most recent error is retained. |
| `pending` | `skipped` | Manual policy or bootstrap classification marks the item intentionally retired or out of scope. |
| `stale` | `skipped` | Manual policy marks the stale item intentionally retired or replaced. |
| `skipped` | `pending` | Only `manual_rescan` may un-retire an item after operator review. |

`skipped` is terminal for automatic triggers. `failed` is not terminal, but retry must be
explicitly represented by a later batch.

## Trigger x transition matrix

| Trigger | Fingerprint driver | Allowed automatic state movement | Disallowed movement |
|---|---|---|---|
| `intake_driven` | `source_fingerprint` changes from source intake or source projection updates. | `completed` -> `stale`, `stale` -> `in_progress`, `pending` -> `in_progress`, `failed` -> `in_progress`. | Must not move `skipped` -> `pending`; must not retire items to `skipped`. |
| `infrastructure_revalidation` | `dependency_fingerprint` changes from CI-3 infrastructure files listed in `DEPENDENCY_FINGERPRINT_SOURCES`. | `completed` -> `stale`, `stale` -> `in_progress`, `pending` -> `in_progress`, `failed` -> `in_progress`. | Must not use source changes as its trigger; must not move `skipped` -> `pending`; must not retire items to `skipped`. |
| `manual_rescan` | Operator-selected source and dependency set. | May claim `pending`, `stale`, or `failed`; may move `skipped` -> `pending` after operator review; may also drive any fingerprint-driven transition (notably `completed` -> `stale` when the operator's selected source or dependency set has changed). | Must not bypass provenance, policy, validation, or write-surface gates. |

Fingerprint-driven transitions (`completed` -> `stale`, `stale` -> `in_progress`,
`failed` -> `in_progress`) are governed by the item state machine and apply across
trigger types. The matrix above enumerates which trigger may *claim* an item; once
claimed, the resulting state move is bounded by the item state machine, not by the
trigger row.

`DEPENDENCY_FINGERPRINT_SOURCES` is declared in `scripts/kb/contracts.py` as
`dict[str, tuple[str, ...]]` keyed by trigger value; the `infrastructure_revalidation`
key holds the path tuple below, which must stay aligned with the CI-3 `push.paths`
allowlist:

- `.github/workflows/ci-3-pr-producer.yml`
- `.github/skills/extract-entities-and-claims/**`
- `.github/skills/validate-wiki-governance/**`
- `.github/skills/synthesize-entity-page/**`
- `.github/skills/synthesize-concept-page/**`

## Bootstrap classification rules

Bootstrap is explicit; it is never triggered automatically by a missing registry file.

1. Dry-run bootstrap reads existing wiki artifacts, source fingerprints, and dependency
   fingerprints without writing the registry.
2. For every candidate item, derive `artifact_type`, `item_key`, `output_path`,
   `source_fingerprint`, and `dependency_fingerprint`.
3. Classify an item as `completed` only when the expected output exists, validates
   against the relevant wiki/page contract, and has unambiguous identity and matching
   fingerprints.
4. Classify an item as `pending` only when the item is expected but no output exists yet
   and identity is unambiguous.
5. Classify an item as `skipped` only when an explicit operator or policy rule marks it
   retired or out of scope.
6. Leave ambiguous, contradictory, colliding, or path-escaping candidates out of the
   registry and include them in the reconciliation report.
7. Apply-mode bootstrap requires operator approval after reviewing the reconciliation
   report. The runtime sequence is dry-run bootstrap, review report, then apply with
   approval.

`failed`, `stale`, and `in_progress` are not bootstrap-classifiable states; they
emerge only from in-flight or post-claim runs. Bootstrap derives state strictly from
expected-output existence and unambiguous identity (yielding `completed`, `pending`,
or `skipped`). Items that would otherwise require run-derived state stay out of the
bootstrap set and surface in the reconciliation report for operator handling.

## Retention constants

Completed batch records are retained indefinitely for MVP. Compaction or archival
requires a later ADR.

Runtime must expose exactly these module-level constants in `scripts/kb/contracts.py`:

| Constant | Value | Required behavior |
|---|---:|---|
| `CHECKPOINT_REGISTRY_SIZE_WARN_BYTES = 5 MB` | `5 * 1024 * 1024` bytes | Verification emits a warning signal when the registry exceeds this size. |
| `CHECKPOINT_REGISTRY_SIZE_FAIL_BYTES = 10 MB` | `10 * 1024 * 1024` bytes | Strict verification fails closed when the registry exceeds this size. |

## Write semantics

| Property | Value |
|---|---|
| Mutability | Mutable |
| Write strategy | Atomic replace under lock |
| Lock path | `raw/.wiki-processing-checkpoint.lock` |
| Lock requirement | Lock must be acquired before any registry write; fail closed on lock unavailability |
| Schema owner | `schema/wiki-processing-checkpoint-registry-contract.md` |
| Governed artifact contract | `scripts/kb/contracts.py` -> artifact ID `wiki-processing-checkpoint-registry` |

Writers must read, validate, mutate, and atomically replace the full registry JSON under
the checkpoint lock. In-place patching is forbidden.

## Lock ordering

If a run updates both wiki artifacts and checkpoint state, acquire locks in this order:

1. `wiki/.kb_write.lock`
2. `raw/.wiki-processing-checkpoint.lock`

Runtime must not acquire these locks in the opposite order. A registry-only operation
may acquire only `raw/.wiki-processing-checkpoint.lock`.

## Fail-closed behavior

The checkpoint registry must fail closed for:

- Missing, unreadable, unparsable, or schema-invalid registry JSON.
- Lock acquisition failure or lock contention.
- Path traversal or output path outside the artifact type's allowed namespace.
- Missing expected output when a transition requires it.
- Source fingerprint or dependency fingerprint mismatch.
- Ambiguous identity, duplicate `item_key`, duplicate current `output_path`, or
  contradictory `path_aliases`.
- Transition not allowed by the batch state machine, item state machine, or Trigger x
  transition matrix.
- Any attempted write outside `raw/wiki-processing/wiki-processing-checkpoint-registry.json`.

Fail-closed means no state is advanced for affected items, the batch remains non-terminal
or failed as appropriate, and the operator receives a deterministic diagnostic.

## Extension rules

New registry fields must:

1. Add a row to the relevant field table above.
2. Be backward-compatible unless an ADR explicitly approves a breaking change.
3. Include `null` as an allowed value for optional fields.
4. Keep code constants in `scripts/kb/contracts.py` and this document synchronized.
5. Bump schema `version` only for breaking changes.
