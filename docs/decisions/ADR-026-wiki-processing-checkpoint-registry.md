# ADR-026: Wiki processing checkpoint registry

## Status

Accepted — extended by ADR-027; amended in-place: last_error single-slot semantics (2026-06-10, see § Amendment 2026-06-10)

## Date

2026-05-31

## Context

Wiki processing is currently evaluated from the live repository state on each run.
That keeps the MVP simple, but it also means a fail-closed partial run does not
leave behind enough structured state to resume safely. Operators can tell that a
run failed, but the pipeline cannot reliably answer:

1. Which generated wiki items were already completed?
2. Which items were in progress when the run stopped?
3. Which items need revalidation because their source or dependency set changed?

The repository already has precedent for durable mutable registries in the GitHub
and Google Drive monitoring lanes. Those registries keep source-state fields such
as `last_applied_*`, `last_fetched_*`, and cursor values under a raw lock so the
next run can resume deterministically after a partial failure.

This ADR applies the same pattern to generated wiki-artifact recovery, but with
two important constraints:

- The checkpoint registry is operational state, not curated wiki content.
- Recovery state must never override governance, policy, or write-surface rules.

Operators also need a stable place to see recovery progress. The repository
already has a governed mutable snapshot path for this kind of operator-facing
state: `wiki/status.md`, published through the existing
`sync-knowledgebase-state` wrapper.

## Decision

### Registry placement and ownership

- Add a governed checkpoint registry under `raw/` at
  `raw/wiki-processing/wiki-processing-checkpoint-registry.json`.
- Define its schema in
  `schema/wiki-processing-checkpoint-registry-contract.md`.
- Keep implementation inside the existing MVP execution boundary; do not add new
  repo-level runtime trees for this feature.

### Locking

- Use a dedicated checkpoint lock at `raw/.wiki-processing-checkpoint.lock`.
- When a run must update both wiki content and checkpoint state, acquire
  `wiki/.kb_write.lock` first, then the checkpoint lock.
- The checkpoint registry fails closed on lock contention or lock acquisition
  failure.

### State model

The registry tracks both batch-level and item-level recovery state.

Batch fields:

- `batch_id`
- `trigger` (`automatic` or `manual_rescan`) — superseded; see § Amendment for the authoritative three-value enum
- `started_at`
- `finished_at`
- `status` (`running`, `completed`, `failed`, `partial`)
- `input_fingerprint`
- `error_summary`

Item fields:

- `item_key`
- `output_path`
- `path_aliases`
- `artifact_type`
- `source_fingerprint`
- `dependency_fingerprint`
- `status` (`pending`, `in_progress`, `completed`, `stale`, `failed`, `skipped`)
- `last_attempted_at`
- `last_succeeded_at`
- `last_error`
- `last_successful_batch_id`

### Identity

- For entity and concept pages, derive `item_key` from the repository's canonical
  identity contract: use `entity_id` when present; otherwise use the normalized
  canonical slug.
- For analysis or index-derived artifacts, derive `item_key` from a stable tuple
  of artifact type plus source/query fingerprint.
- Treat paths as mutable projections. Renames and moves update `output_path` and
  append the previous path to `path_aliases`, but they do not change `item_key`.
- If canonical identity itself changes (for example, a corrected `entity_id`),
  retain the previous key as a historical alias record and mark it `skipped`
  with `last_error` documenting the replacement key. New runs continue under the
  replacement key so orphaned keys are explicit and auditable.

### State transitions

- `pending` -> `in_progress` when a run claims the item.
- `in_progress` -> `completed` only when the expected output exists and the
  relevant fingerprints match.
- `in_progress` -> `stale` when the 1-hour stale timeout expires or the expected
  state/output is missing.
- `completed` -> `stale` when source or dependency fingerprints change.
- `stale` -> `in_progress` when a new automatic run or manual rescan takes over.
- `in_progress` -> `failed` on hard processing errors (for example, write denial,
  schema mismatch, or deterministic validator failure).
- `failed` -> `in_progress` only on an explicit retry attempt in a later batch;
  retries must retain prior `last_error` history and update `last_attempted_at`.
- `skipped` is reserved for intentionally retired or out-of-scope items.
- `pending`/`stale` -> `skipped` when policy marks the item retired or replaced.
- `skipped` is terminal for automatic runs; only a manual rescan may move
  `skipped` -> `pending`.

### Bootstrap and recovery

- Bootstrap validates expected outputs at each stage before seeding state.
- Seed every item that can be classified unambiguously from those expected
  outputs and fingerprints.
- Leave ambiguous or contradictory items out of the bootstrap set and require
  manual resolution.
- This keeps the registry trustworthy while still allowing the next run to pick
  up from the latest proven stage.

### Operator snapshot

- Publish recovery progress in `wiki/status.md` through the existing
  `sync-knowledgebase-state` wrapper.
- Do not make `wiki/reports/` the primary recovery surface for this feature.
- The checkpoint registry remains the source of truth; `wiki/status.md` is a
  derived operator snapshot.

### Retention

- Retain completed batch records indefinitely for MVP.
- If the registry later needs compaction or archival, record that in a separate
  ADR rather than pruning the source of truth now.
- Add a guardrail metric in the owning implementation: if checkpoint history
  growth exceeds the agreed operational threshold, open a follow-up issue and
  route compaction to a dedicated ADR instead of silent pruning.

## Alternatives considered

### Store recovery state in topical wiki content

- **Pros:** easy to discover alongside the content being processed.
- **Cons:** mixes operational state with curated knowledge, creates noisy diffs,
  and makes recovery logic depend on topical content shape.
- **Rejected:** operational state belongs in a governed raw registry, not in the
  knowledge pages it helps produce.

### Use a write-once report artifact as the primary recovery record

- **Pros:** simple to reason about as a snapshot.
- **Cons:** a write-once artifact cannot represent mutable recovery state well;
  it is a history record, not a live checkpoint model.
- **Rejected:** the feature needs resumable state, not just an audit snapshot.

### Use opaque UUIDs for item identity

- **Pros:** easy to generate and collision-resistant.
- **Cons:** renames and moves would sever recovery continuity, and identity would
  drift away from the repository's canonical wiki identity rules.
- **Rejected:** recovery must follow the durable referent, not just the path that
  happened to exist at bootstrap time.

### Reuse only `wiki/.kb_write.lock`

- **Pros:** fewer lock files.
- **Cons:** checkpoint writes would be coupled too tightly to wiki writes and the
  deadlock analysis would be less explicit.
- **Rejected:** a dedicated checkpoint lock keeps the recovery state domain clear
  while preserving deterministic lock ordering.

### Add dedicated `removed` or `retired` states

- **Pros:** more explicit semantics for intentionally gone items.
- **Cons:** expands the state machine without adding real capability; `stale`
  already covers missing outputs and `skipped` already covers intentional
  retirement or out-of-scope items.
- **Rejected:** keep the state machine small until evidence demands more states.

### Prune completed batches after a fixed window

- **Pros:** bounds registry growth.
- **Cons:** removes audit history and makes replay/debugging harder.
- **Rejected:** retain records indefinitely for MVP and revisit compaction later
  if the registry becomes too large.

### Publish recovery progress in `wiki/reports/` as the primary surface

- **Pros:** JSON reports are easy to consume.
- **Cons:** the repository already has a governed mutable status snapshot path,
  and recovery progress is operational state rather than a durable report.
- **Rejected:** `wiki/status.md` is the operator-facing surface; reports can stay
  secondary if a future need appears.

### Auto-seed ambiguous bootstrap items

- **Pros:** fewer manual follow-up steps.
- **Cons:** imports unverified junk state and weakens trust in the registry.
- **Rejected:** only unambiguous items are auto-seeded.

## Consequences

- Wiki recovery becomes resumable without embedding process state in curated
  wiki pages.
- The registry is now a governed raw artifact that needs a schema contract, a
  dedicated lock, and a write-surface matrix row before writes are enabled.
- Recovery is still fail-closed: incomplete or contradictory state does not
  silently advance.
- `wiki/status.md` becomes the operator-facing recovery snapshot, while the raw
  registry remains the source of truth.
- Existing pages and artifact identities continue to follow the repository's
  canonical identity rules.
- Batch records are retained indefinitely unless a later ADR defines a separate
  archival policy.

## Amendment

- Date: 2026-06-07.
- What changed: the original Decision `### State model` lists `trigger`
  values as `(automatic or manual_rescan)`. ADR-027 introduced a third
  trigger value, `infrastructure_revalidation`, and renamed `automatic` to
  `intake_driven`. The authoritative trigger enum is now the three-value set:
  `intake_driven`, `infrastructure_revalidation`, and `manual_rescan`, written
  as lowercase snake_case strings in JSON and represented as a `StrEnum` in
  Python per the precedent in `scripts/kb/contracts.py`.
- What did not change: the rest of the State model, including batch and item
  fields, item-level state transitions, identity rules, locking decisions, the
  retention rule, and the operator snapshot via `wiki/status.md`. In
  `### State transitions`, the descriptor "automatic run" now refers to any
  non-manual trigger (`intake_driven` or `infrastructure_revalidation`); the
  transition graph itself is unchanged.
- Cross-reference: see ADR-027 for the trigger model rationale and CI-3 trigger
  paths.

### Amendment 2026-06-10 (PR2 schema clarifications)

- Date: 2026-06-10.
- What changed: the `last_error` field uses single-slot semantics — only the
  most recent error is retained, and older errors are overwritten on each new
  attempt. This supersedes the prior `### State transitions` clause that said
  "retries must retain prior `last_error` history" on the `failed -> in_progress`
  edge. Cross-batch error provenance is preserved through the immutable batch
  records (each batch's `error_summary` plus its `started_at`/`finished_at`
  window) plus the per-item `last_attempted_at` and `last_successful_batch_id`
  fields, so historical errors remain recoverable from the registry without
  per-item error arrays. The schema contract at
  `schema/wiki-processing-checkpoint-registry-contract.md` is the authoritative
  source for this field's semantics and pins the supersession explicitly.
- What did not change: the `failed -> in_progress` edge itself, the requirement
  to update `last_attempted_at` on every retry, the immutability of completed
  batch records, and every other field and state machine rule.
- Cross-reference: see `schema/wiki-processing-checkpoint-registry-contract.md`
  § Item fields (`last_error` row) and § Item state machine
  (`failed -> in_progress` row) for the authoritative wording.

## Migration

- New batch records written by `scripts/kb/checkpoint_registry.py` in PR3 use
  the three-value enum from initial bootstrap.
- No legacy registry records exist today because the registry artifact has not
  been written yet, so no rewrite of historical batch JSON is required.
- If any pre-amendment batch records ever appear, for example from a vendored
  snapshot, bootstrap performs a one-shot rewrite from `trigger: automatic` to
  `trigger: intake_driven`. The bootstrap reconciliation report must list every
  normalized record before any registry write.
- The CI-3 workflow's path-filter allowlist for `infrastructure_revalidation`
  runs is the authoritative dependency set. ADR-027 documents these paths, and
  the schema contract in PR2 cross-references the same allowlist via
  `DEPENDENCY_FINGERPRINT_SOURCES`.

## Rollback

- Remove the `infrastructure_revalidation` value from `scripts/kb/contracts.py`
  `TriggerType`, then rename `intake_driven` back to `automatic` in code and in
  the schema contract.
- Revert the CI-3 `push:` trigger added by ADR-027, specifically the `push:`
  section in `.github/workflows/ci-3-pr-producer.yml`.
- Rewrite registry records with `trigger: intake_driven` to
  `trigger: automatic`. Reject records with `trigger: infrastructure_revalidation`
  for manual triage because the two-value enum has no equivalent.
- Rollback impact: infrastructure changes lose end-to-end auto-validation;
  manual `workflow_dispatch` remains the recovery path.

## References

- `docs/ideas/wiki-processing-checkpoint-registry.md`
- `AGENTS.md`
- `docs/decisions/ADR-005-write-concurrency-guards.md`
- `docs/decisions/ADR-009-canonical-identity-and-anchor-management.md`
- `docs/decisions/ADR-023-batch-query-persistence-design.md`
- `schema/ontology-entity-contract.md`
- `schema/governed-artifact-contract.md`
- `schema/report-artifact-contract.md`
- `.github/skills/sync-knowledgebase-state/SKILL.md`
- `scripts/context/manage_context_pages.py`
