# Wiki processing checkpoint registry

**Status:** In Progress — Design decisions resolved via grilling session 2026-06-07 and simplified via `improve-codebase-architecture` review on 2026-06-07 (Path C-prime, 4 PRs); ADR-026 and ADR-027 published; runtime implementation, schema contract, and remaining documentation cascade items pending.

This proposal adds a governed checkpoint registry under `raw/` for wiki processing. The registry tracks generated wiki artifacts/pages at item and batch granularity so partial fail-closed runs can resume and changed outputs can be re-evaluated without storing workflow state in topical wiki content.

## Design status

Design decisions for this feature were resolved in a `grill-with-docs` session on 2026-06-07. The session walked 16 decision branches across 58 sub-decisions, grounded in primary-source evidence from the codebase, ADR history, and empirical CI-3 run telemetry. Validation findings are recorded in `docs/research/wiki-processing-checkpoint-registry-implementation-status.md`.

Key resolved decisions:

- **Trigger enum reconciled.** ADR-026 was published before ADR-027 introduced the three-value trigger split; PR1 of the implementation plan amends ADR-026 in place per the repo's ADR-evolution rule (`Status: Accepted — extended by ADR-027` plus an `## Amendment` section codifying the lowercase snake_case spelling).
- **Schema contract structure.** Fresh skeleton (not a 1:1 mirror of `schema/drive-source-registry-contract.md`) because the checkpoint registry's two-scope state model (batch + item), `source_fingerprints` map, and trigger-typed transitions don't fit the per-source-entry shape of the existing registry contracts.
- **Trigger × transition matrix.** Three triggers (`intake_driven`, `infrastructure_revalidation`, `manual_rescan`) crossed against the six item states. `infrastructure_revalidation` reacts to `dependency_fingerprint` changes; `intake_driven` reacts to `source_fingerprint` changes; only `manual_rescan` can retire (`skipped`) or un-retire items.
- **Lock strategy: lock-once, hold-long.** Matches `synthesize_combined.py` (PR #115) precedent. Empirical CI-3 data (5 successful runs) shows wiki-lock-held duration is ~1 second per batch today; projected ~1.2-1.5 seconds under the checkpoint orchestrator.
- **Four-PR implementation layout (Path C-prime).** An `improve-codebase-architecture` review on 2026-06-07 simplified the earlier six-PR plan: dedicated runtime module preserved; separate render module folded into the existing `sync-knowledgebase-state` skill; `--force-*` operator commands deferred (observable via the monitors below); retention thresholds collapsed to two module-level constants; pre-commit hook deferred (covered by runtime `--verify` mode); separate bootstrap PR folded into the runtime PR. Each PR on its own branch off `main` (named `checkpoint/0N-<slug>`); strict linear merge order; full pre-commit, post-commit, and pre-merge validation per PR.

Three repo-wide backlog issues were filed during the session as side-effect findings (none block the checkpoint feature):

- [#181](https://github.com/wryenmeek/knowledgebase/issues/181) — Formalize pytest as canonical test framework + CI ratchet for unittest→pytest migration.
- [#182](https://github.com/wryenmeek/knowledgebase/issues/182) — Reconsider `--approval` flag pattern (codify, rename, or replace).
- [#183](https://github.com/wryenmeek/knowledgebase/issues/183) — Add holder-PID tracking to write lock files for better lock-unavailable UX.

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

## Registry model

> The fields below are the operative contract surface. The canonical, normative schema is authored in `schema/wiki-processing-checkpoint-registry-contract.md` (PR3 of the implementation plan), which also defines the top-level `source_fingerprints` map (path → sha256) referenced by `item.source_fingerprint`.

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

## Identity and collision rules

> Per-artifact-type derivation rules and excluded-artifact-type rationale are codified in the schema contract. The summary below captures the design intent.

- Canonical identity is `item_key`; paths are mutable projections.
- For wiki entity pages, derive `item_key` from `entity_id` when present in frontmatter, otherwise the normalized canonical slug per `schema/ontology-entity-contract.md`. Concept pages use the normalized canonical slug (concepts do not carry `entity_id`).
- For analysis pages (`wiki/analyses/<slug>-<fp16>.md`), `item_key` is the filename stem; the fingerprint is already computed by `persist_query._analysis_relative_path` and is extracted into a public `analysis_fingerprint()` helper in PR2.
- `wiki/sources/**`, governed fixed-path artifacts (`wiki/index.md`, `wiki/log.md`, `wiki/status.md`, `wiki/open-questions.md`, `wiki/backlog.md`), and `wiki/reports/**` are explicit-excluded from registry items. Sources' content hashes still appear in the top-level `source_fingerprints` map so downstream items can detect source-change-driven staleness; the other excluded surfaces have their own governance.
- Rename/move: keep `item_key`, update `output_path`, append previous path to `path_aliases`. Meaningful only for entities and concepts; analyses cannot be renamed without changing identity (filename includes the fingerprint).
- One-source-to-many-output and many-source-to-one-output cases must be represented explicitly through dependency fingerprints.
- On key collision or ambiguous mapping, fail closed and require manual resolution before advancing state.

## Bootstrap and recovery rule

- Bootstrap is an **explicit mode** of `checkpoint_registry.py` (not auto-on-first-write); the architecture review on 2026-06-07 rejected auto-bootstrap to preserve ADR-026's trust model.
- Bootstrap validates expected outputs at each stage before seeding state.
- Seed every item whose current state can be classified unambiguously from expected outputs/fingerprints.
- Leave ambiguous or contradictory cases out of the bootstrap set and flag them for manual resolution.
- Bootstrap emits a reconciliation report (item-by-item classification plus any ambiguous cases) before any write; the required runbook sequence is dry-run bootstrap -> review reconciliation report -> operator confirmation -> `--bootstrap --apply --approval approved`.
- This keeps the registry trustworthy while still letting the next run resume from the latest proven stage.

## Implementation plan

The canonical implementation plan is **four PRs (Path C-prime)** in strict linear merge order, each on its own branch off `main`. Every PR must pass pre-commit hooks, post-commit CI checks (including the `--cov-fail-under=90` gate), and pre-merge cross-functional review before merge.

1. **PR1 — `checkpoint/01-adr-and-doc-reconciliation`.** Amend ADR-026 in place to reflect the three-value trigger enum and reference ADR-027 (Status → `Accepted — extended by ADR-027`; new `## Amendment`, `## Migration`, and `## Rollback` sections); update `docs/decisions/README.md` row; land the previously-missing `docs/architecture.md` and `docs/mvp-runbook.md` cascade items called out by the research validation report. Also includes this idea-doc and the validation research report (`docs/research/wiki-processing-checkpoint-registry-implementation-status.md`) as planning artifacts of PR1.
2. **PR2 — `checkpoint/02-schema-and-contracts`.** Author `schema/wiki-processing-checkpoint-registry-contract.md` with the full normative schema (per-artifact-type identity table, `source_fingerprints` map, batch + item state machines, trigger × transition matrix, bootstrap classification rules, retention constants). Add to `scripts/kb/contracts.py`: `CHECKPOINT_REGISTRY_LOCK_PATH`, `wiki-processing-checkpoint-registry` `GovernedArtifactContract` entry, `TriggerType`/`ArtifactType` enums, `DEPENDENCY_FINGERPRINT_SOURCES` map, and two module-level retention constants (`CHECKPOINT_REGISTRY_SIZE_WARN_BYTES`, `CHECKPOINT_REGISTRY_SIZE_FAIL_BYTES`) in place of the original `CheckpointRetentionThresholds` dataclass. Extract `analysis_fingerprint()` from `scripts/kb/persist_query._analysis_relative_path` as a pure refactor (pure extraction; no behavior change). Triggers contract-test cascades in `tests/kb/test_contracts.py` and a new partial `test_checkpoint_contract_alignment.py`.
3. **PR3 — `checkpoint/03-runtime`.** Implement `scripts/kb/checkpoint_registry.py` as a **single module** with three CLI modes: `--bootstrap`, `--mutate`, `--verify`. No `--force-*` family (deferred — see "Deferred items and monitoring" below). Status snapshot is rendered inline by the existing `sync-knowledgebase-state` skill (no new render module). Refactor `synthesize_combined.run()` to accept `lock_already_held: bool = False`. Add 2 new test files (`test_checkpoint_registry.py` covering all three modes, `test_checkpoint_contract_alignment.py`). Add 1 write-surface matrix row to `AGENTS.md` (single entrypoint with all three modes documented in the row) + amend the `sync-knowledgebase-state` row to cite the new contract. Update `docs/ideas/wiki-curation-agent-framework.md` `FRAMEWORK_BOUNDARY_DOCS` entry list verbatim with `scripts/kb/checkpoint_registry.py`. `--verify` mode emits the file-size, item-count, schema-validation, and JSON-parse signals that feed the deferred-item monitors (see "Deferred items and monitoring" below).
4. **PR4 — `checkpoint/04-ci-wiring-and-bootstrap`.** Wire CI-3 to invoke `checkpoint_registry.py --mutate` per batch, followed by `--verify --warn-only` whose output is surfaced to the GitHub Actions job summary. Execute the bootstrap runbook sequence (dry-run bootstrap -> review reconciliation report -> operator confirmation -> `--bootstrap --apply --approval approved`) and commit the initial registry JSON.

PR1 is a doc-only PR (low risk, single reviewer + `documentation-engineer`). PR2 requires `documentation-engineer` + `test-engineer` review. PR3 requires `code-reviewer` + `test-engineer` + `documentation-engineer` + `security-auditor` review per the repo's post-implementation rule. PR4 additionally requires `security-auditor` review for the CI wiring.

## Verification plan

Per-PR baseline (runs unchanged from existing CI):

- `python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py`
- `python3 -m unittest tests.kb.test_framework_contracts tests.kb.test_framework_skills tests.kb.test_framework_agents tests.kb.test_framework_references tests.kb.test_framework_write_surface_matrix tests.kb.test_skill_wrappers`
- `python3 -m pytest tests/kb/ -q --cov=scripts/kb --cov-fail-under=90`

Test files added in PR3 (pytest style per adjacent `tests/drive_monitor/` and `tests/github_monitor/` precedent):

- `tests/kb/test_checkpoint_registry.py` — covers all three modes. Bootstrap: per-artifact-type classification, idempotency and replay safety, canonical JSON output, collision detection, reconciliation-report shape. Mutate: interrupted-run resume, stale-item revalidation, lock contention/fail-closed, rename/move continuity via `item_key` + `path_aliases`, 1-hour stale timeout, atomic-replace rollback, legal/illegal transitions per the trigger × transition matrix. Verify: read-only schema validation, file-size and item-count reporting, JSON-parse failure detection, exit-code semantics for `--warn-only` vs strict.
- `tests/kb/test_checkpoint_contract_alignment.py` — governed-artifact entry present; lock in `GOVERNANCE_LOCK_FILES`; matrix row declared; `DEPENDENCY_FINGERPRINT_SOURCES` symmetric with CI-3 push-trigger allowlist; trigger and artifact-type enum completeness; retention-constant sync between contract doc and code.

Test files amended in PR2/PR3 (contract-test cascades):

- `tests/kb/test_contracts.py` — `GOVERNED_ARTIFACT_IDS` and `GOVERNED_ARTIFACT_PATHS` expected tuples must include the checkpoint registry entry (amended in PR2).
- `tests/kb/test_framework_write_surface_matrix.py` — `EXPECTED_WRITE_SURFACE_MATRIX_ROWS` dict must include one new row for `scripts/kb/checkpoint_registry.py` (single entrypoint, three modes documented in the row text) (amended in PR3).
- `tests/kb/test_framework_contracts.py` — `test_boundary_docs_list_same_execution_surface` must include `scripts/kb/checkpoint_registry.py` verbatim in `docs/ideas/wiki-curation-agent-framework.md` (amended in PR3).

## Documentation cascade (implementation checklist)

ADR work (PR1):

- [x] ADR-026 published (2026-05-31).
- [x] ADR-027 published (2026-06-02) — documents `infrastructure_revalidation` trigger model.
- [x] `docs/decisions/README.md` indexes both ADRs.
- [ ] ADR-026 amended in place: `Status: Accepted — extended by ADR-027` plus `## Amendment` section codifying the three-value trigger enum (`intake_driven`, `infrastructure_revalidation`, `manual_rescan` — lowercase snake_case JSON strings; `StrEnum` Python representation per `scripts/kb/contracts.py` precedent).
- [ ] ADR-026 gains `## Migration` and `## Rollback` headings to match ADR-027 structure and the original Phase 1 ADR requirement.
- [ ] `docs/decisions/README.md` row for ADR-026 updated to match new status (enforced by pre-commit hook `check_adr_cross_ref.py`).

Architecture and runbook cascade items (PR1, identified by the research validation report as missing):

- [ ] `docs/architecture.md` updated to document checkpoint lifecycle and lock ordering.
- [ ] `docs/mvp-runbook.md` updated with: manual rescan procedure, checkpoint recovery procedure (per the rollback-scenarios decision), required bootstrap dry-run-then-apply sequence, and `gh run list --workflow=ci-3-pr-producer.yml --status in_progress` reference for the lock-unavailable case.

Schema and surface cascade (PR2-PR3):

- [ ] `schema/wiki-processing-checkpoint-registry-contract.md` authored (PR2).
- [ ] `schema/CONTEXT.md` File Roles list adds the new contract; `last_updated` bumped (PR2).
- [ ] `scripts/kb/CONTEXT.md` `last_updated` bumped when `checkpoint_registry.py` lands (PR3).
- [ ] 1 new row added to `AGENTS.md` write-surface matrix: `scripts/kb/checkpoint_registry.py` (single entrypoint with all three modes documented in the row) (PR3).
- [ ] `sync-knowledgebase-state` matrix row's Schema/artifact owners column extended to cite the new contract (PR3).
- [ ] `docs/ideas/wiki-curation-agent-framework.md` `FRAMEWORK_BOUNDARY_DOCS` entrypoint list extended verbatim with `scripts/kb/checkpoint_registry.py` — required by `tests/kb/test_framework_contracts.py::test_boundary_docs_list_same_execution_surface` (literal `assertIn`).

Related repo-wide backlog (not blocking this feature):

- [#181](https://github.com/wryenmeek/knowledgebase/issues/181) — pytest framework formalization + CI ratchet.
- [#182](https://github.com/wryenmeek/knowledgebase/issues/182) — `--approval` flag pattern reconsideration.
- [#183](https://github.com/wryenmeek/knowledgebase/issues/183) — lock holder-PID tracking for better lock-unavailable UX.

## Deferred items and monitoring

The `improve-codebase-architecture` review on 2026-06-07 deferred several surfaces that were in the original six-PR plan. Each is observable via cheap, mostly-free signals so a re-evaluation issue can be filed with concrete evidence rather than speculation.

| Deferred item | Failure signal to watch | Where to read it | Trigger threshold to file backlog issue |
|---|---|---|---|
| `--force-*` operator recovery commands (`--force-transition`, `--mark-stale-by-key`, `--force-rebootstrap`, `--dry-run-report`) | Operator manually edits `raw/wiki-processing/wiki-processing-checkpoint-registry.json` to repair state | `git log --oneline -- raw/wiki-processing/wiki-processing-checkpoint-registry.json` (count non-CI-bot commits) | ≥2 manual repair commits in a 90-day window |
| `--force-*` operator recovery commands | `--verify` mode failures in CI-3 | `gh run list --workflow=ci-3-pr-producer.yml --json conclusion,createdAt` plus the `--verify --warn-only` job-summary output | ≥3 verify-mode failures in 30 days |
| Retention dataclass with soft/hard threshold pairs | Registry file size growth | `--verify` mode prints `file_size_bytes` and compares against `CHECKPOINT_REGISTRY_SIZE_WARN_BYTES` / `CHECKPOINT_REGISTRY_SIZE_FAIL_BYTES` constants | File >5 MB warning / >10 MB hard fail |
| Retention dataclass with soft/hard threshold pairs | Item count growth | `--verify` mode prints `item_count` | >5,000 items |
| Pre-commit hook for registry JSON | Invalid JSON discovered at runtime | `--verify` mode JSON-parse failure events appended to `wiki/log.md` under event type `checkpoint_registry.verify_warning` | ≥1 corruption incident logged |
| Pre-commit hook for registry JSON | Schema validation failures | `--verify` mode schema-check failure events appended to `wiki/log.md` under event type `checkpoint_registry.verify_warning` | ≥2 schema failures from hand-edits in 90 days |
| Standalone status render module | Inline render code in `sync-knowledgebase-state` growing unwieldy | Code-review observation; LOC count of the inline render function | >50 LOC inline render |

Monitoring instrumentation lives in PR3 (`--verify` mode reports + `wiki/log.md` event taxonomy) and PR4 (CI-3 job-summary surfacing). Net cost: ~15 LOC in PR3, ~5 lines of YAML in PR4. No new GitHub Actions workflow, no per-PR size assertion, no separate monitoring schema — everything piggybacks on existing telemetry (`git log`, `gh run list`, append-only `wiki/log.md`).

Issue filing protocol: do not pre-emptively file backlog issues for deferred items. File one issue per signal only when its trigger threshold is exceeded, with the supporting evidence (git log output, CI run IDs, or log events) attached. This keeps the backlog free of speculative items and ensures any new surface added later is justified by observed failure data.
