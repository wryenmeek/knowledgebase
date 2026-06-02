# Wiki processing checkpoint registry

**Status:** Proposed

This proposal adds a governed checkpoint registry under `raw/` for wiki processing. The registry tracks generated wiki artifacts/pages at item and batch granularity so partial fail-closed runs can resume and changed outputs can be re-evaluated without storing workflow state in topical wiki content.

## Goals

- Resume incomplete wiki-processing work after fail-closed runs.
- Revalidate completed items when their source or dependencies change.
- Bootstrap the current wiki state before enabling recovery.
- Keep workflow state outside curated wiki pages and record the rationale in ADR-026.
- Keep execution inside the existing MVP runtime boundary (`scripts/kb/**`, `tests/kb/**`, `schema/**`, and `docs/**`).

## Non-goals

- Do not store process state in topical wiki content.
- Do not replace existing fail-closed validation.
- Do not introduce an append-only event stream unless the ADR later requires it.
- Do not introduce new runtime trees under `scripts/validation/**`, `scripts/reporting/**`, `scripts/context/**`, or `scripts/maintenance/**` for this feature.
- Do not use checkpoint state to gate infrastructure_revalidation triggers; trigger model is independent of checkpoint completeness.

## Governance and execution invariants

1. Governance order remains explicit: `intake_driven` runs flow intake -> verification -> policy -> synthesis/query/topology. `infrastructure_revalidation` runs bypass intake and directly validate topology/synthesis layers after control-plane changes (ADR-007). Both trigger types are gated by their respective lock ordering.
2. Checkpoint state is observational, not authoritative: no checkpoint entry can authorize a write that governance would otherwise block.
3. Checkpoint updates remain fail-closed: write/read/lock or schema validation failure keeps affected items non-terminal and requires re-evaluation.
4. Helpers remain deterministic and typed; no shell glue, eval, or dynamic dispatch.
5. Operator-visible progress is summarized in governed status/report artifacts, not embedded in topical entity/concept pages.

## Proposed placement and contracts

- Registry artifact (proposed): `raw/wiki-processing/wiki-processing-checkpoint-registry.json`
- Contract (new): `schema/wiki-processing-checkpoint-registry-contract.md`
- Surface ownership (proposed): existing `scripts/kb/**` entrypoints only
- Checkpoint lock (decision): `raw/.wiki-processing-checkpoint.lock`
- Primary operator snapshot: `wiki/status.md` via `sync-knowledgebase-state`
- Write-surface declaration (required in implementation): add row(s) to the `AGENTS.md` write-surface matrix before enabling writes

If a run updates both wiki artifacts and checkpoint state, lock ordering is deterministic: acquire `wiki/.kb_write.lock` first, then `raw/.wiki-processing-checkpoint.lock`.

## Registry model (draft)

### Batch-level fields

- `batch_id` (stable run identifier)
- `trigger` (`intake_driven`, `infrastructure_revalidation`, or `manual_rescan`)
- `triggered_by` (commit SHA or trigger source, for diagnostics)
- `started_at`, `finished_at`
- `status` (`running`, `completed`, `failed`, `partial`)
- `input_fingerprint` (digest over the run's relevant source/dependency set)
- `error_summary` (if non-terminal)

### Item-level fields

- `item_key` (canonical identity key; not equal to path)
- `output_path` (current materialized path)
- `path_aliases` (prior paths for rename/move continuity)
- `artifact_type` (for example: entity, concept, analysis, index-derived artifact)
- `source_fingerprint` and `dependency_fingerprint`
- `status` (`pending`, `in_progress`, `completed`, `stale`, `failed`, `skipped`)
- `last_attempted_at`, `last_succeeded_at`, `last_error`
- `last_successful_batch_id`

### State transitions

- `pending` -> `in_progress` when a run claims the item.
- `in_progress` -> `completed` when the expected final output exists and fingerprints match.
- `in_progress` -> `stale` when the 1-hour stale timeout expires or the expected state/output is missing.
- `completed` -> `stale` when source or dependency fingerprints change.
- `stale` -> `in_progress` on a new automatic run or manual rescan takeover.
- `failed` is reserved for hard processing errors.
- `skipped` is reserved for intentionally retired or out-of-scope items.

## Identity and collision rules (draft)

- Canonical identity is `item_key`; paths are mutable projections.
- For wiki entity/concept pages, derive `item_key` from the repository's canonical identity contract (`entity_id` when present, otherwise normalized canonical slug).
- For analysis/index-derived artifacts, derive `item_key` from a stable tuple of artifact type plus source/query fingerprint.
- Rename/move: keep `item_key`, update `output_path`, append previous path to `path_aliases`.
- One-source-to-many-output and many-source-to-one-output cases must be represented explicitly through dependency fingerprints.
- On key collision or ambiguous mapping, fail closed and require manual resolution before advancing state.

## Bootstrap and recovery rule

- Bootstrap validates expected outputs at each stage before seeding state.
- Seed every item whose current state can be classified unambiguously from expected outputs/fingerprints.
- Leave ambiguous or contradictory cases out of the bootstrap set and flag them for manual resolution.
- This keeps the registry trustworthy while still letting the next run resume from the latest proven stage.

## Phases

1. Draft ADR and contract together: decision, alternatives, migration, rollback, and operational consequences. Document infrastructure_revalidation trigger model and its interaction with checkpoint state.
2. Define checkpoint schema, identity model, lock ordering, and legal state transitions. Account for runs triggered by different sources (intake_driven vs. infrastructure_revalidation) and their fingerprint contexts.
3. Add write-surface matrix entries and runtime guardrails for checkpoint read/write paths. Define allowed writers per trigger type and phase.
4. Bootstrap current generated artifacts into the registry (dry-run + apply) with explicit reconciliation reporting.
5. Wire resume and revalidation logic (intake_driven automatic run + infrastructure_revalidation trigger + manual_rescan). Ensure each trigger type correctly classifies stale items and skips non-applicable recovery steps.
6. Add operator-facing progress summary in governed status/report artifacts only.
7. Land tests and docs before enabling checkpoint writes in CI.

## Verification plan (required for implementation)

- `python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py`
- `python3 -m unittest tests.kb.test_framework_contracts tests.kb.test_framework_skills tests.kb.test_framework_agents tests.kb.test_framework_references tests.kb.test_skill_wrappers`
- `python3 -m pytest tests/kb/`

Implementation acceptance must include explicit tests for:

- interrupted-run resume behavior
- stage-by-stage bootstrap classification against expected outputs/fingerprints
- stale-item revalidation detection
- lock contention/failure fail-closed behavior
- rename/move continuity via `item_key` + `path_aliases`
- bootstrap idempotency and replay safety

## Documentation cascade (implementation checklist)

- Add/update the relevant row(s) in `AGENTS.md` write-surface matrix.
- Add ADR in `docs/decisions/ADR-*.md` and update `docs/decisions/README.md`.
- Update `docs/architecture.md` for checkpoint lifecycle and lock ordering.
- Update `docs/mvp-runbook.md` operator runbooks for manual rescan and checkpoint recovery.
