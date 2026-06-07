# Wiki processing checkpoint registry — implementation status verification

**Date:** 2026-06-04
**Mode:** verified-research (read-only)
**Subject:** `docs/ideas/wiki-processing-checkpoint-registry.md`
**Method:** primary-source verification with four parallel explore subagents (ADR/doc cascade, runtime/code, schema/matrix, tests/CI) plus direct inspection of ADR-026, ADR-027, README, and the CI-3 workflow.

> **Baseline report — point-in-time snapshot (2026-06-04).** This
> document captures the codebase state **before PR1 of the C-prime 4-PR
> plan landed**. Items 1 and 2 in the Headline ("Trigger-model drift
> between ADR-026 and the idea doc" and "Documentation cascade items
> never landed") were resolved by PR #184 (this PR). The findings below
> remain accurate as historical evidence for *why* the cascade work was
> scoped; they should not be read as a description of current state.
> See `docs/ideas/wiki-processing-checkpoint-registry.md` § Implementation
> plan for what PR1 closed and what PR2/PR3/PR4 still address.

---

## Headline

The idea doc's own status line — **"In Progress — ADR-026 is published and tracked in `docs/decisions/README.md`; registry implementation remains pending (2026-06-04)"** — is **substantially accurate** but **understates two pieces of drift**:

1. **Trigger-model drift between ADR-026 and the idea doc** (the doc has evolved past the ADR without amending it).
2. **Documentation cascade items the doc itself prescribes were never landed** (`docs/architecture.md` and `docs/mvp-runbook.md` updates).

Implementation of the registry, schema, lock, runtime code, write-surface row, and tests is **0% landed**. Only ADRs (decision artifacts) and one upstream CI workflow gate (the push-trigger preflight in CI-3) are present.

---

## Lineage

- **Idea doc** `docs/ideas/wiki-processing-checkpoint-registry.md` — proposal (`Status: In Progress`).
- **ADR-026** `docs/decisions/ADR-026-wiki-processing-checkpoint-registry.md` — Accepted 2026-05-31, codifies the registry decision.
- **ADR-027** `docs/decisions/ADR-027-infrastructure-validation-trigger-model.md` — Accepted 2026-06-02, introduces the `intake_driven` / `infrastructure_revalidation` trigger naming and lists ADR-026 in "Related decisions" (but ADR-026's `## Status` was **not** updated to "extended by ADR-027" per the repo's ADR evolution rule).

The idea doc was last updated **2026-06-04** to record the ADR-027 trigger naming; ADR-026 still uses the older `automatic | manual_rescan` field values.

This is **convergence with drift**: the idea doc, ADR-027, and CI-3 workflow agree on the trigger model; ADR-026 lags behind.

---

## Confirmation table (per major claim)

| # | Claim from idea doc | Verdict | Confidence | Primary evidence |
|---|---|---|---|---|
| 1 | ADR-026 exists and is `Accepted` | **Confirmed** | Very High | `docs/decisions/ADR-026-wiki-processing-checkpoint-registry.md:3-5` |
| 2 | ADR-026 tracked in `docs/decisions/README.md` with matching status | **Confirmed** | Very High | `docs/decisions/README.md:35` |
| 3 | ADR documents the `infrastructure_revalidation` trigger model | **Drift** | High | `ADR-026:64` lists triggers as `automatic` and `manual_rescan` only; the model is in ADR-027 instead, and ADR-026's status was not amended |
| 4 | Registry artifact `raw/wiki-processing/wiki-processing-checkpoint-registry.json` exists | **Not Implemented** | Very High | Directory `raw/wiki-processing/` does not exist |
| 5 | Schema contract `schema/wiki-processing-checkpoint-registry-contract.md` exists | **Not Implemented** | Very High | Not in `schema/` listing; precedent files would be `schema/github-source-registry-contract.md`, `schema/drive-source-registry-contract.md` |
| 6 | Checkpoint lock `raw/.wiki-processing-checkpoint.lock` declared in code | **Not Implemented** | Very High | `scripts/kb/contracts.py:74-88` defines `GOVERNANCE_LOCK_FILES` from `WRITE_LOCK_PATH`, `GITHUB_SOURCES_LOCK_PATH`, `REJECTION_REGISTRY_LOCK_PATH`, `DRIVE_SOURCES_LOCK_PATH` only |
| 7 | Write-surface matrix row added in `AGENTS.md` | **Not Implemented** | Very High | No matrix row mentions `wiki-processing`, `checkpoint`, or the proposed lock path |
| 8 | Runtime helpers exist under `scripts/kb/**` | **Not Implemented** | Very High | No `scripts/kb/**` source contains the registry/checkpoint/bootstrap symbols listed in the idea doc |
| 9 | Bootstrap dry-run + apply implemented | **Not Implemented** | Very High | No `bootstrap_checkpoint*` module, no `--bootstrap` flag against `raw/wiki-processing` |
| 10 | Resume / revalidation logic wired (intake_driven + infrastructure_revalidation + manual_rescan) | **Partially Implemented (gate-only)** | High | CI-3 push-trigger gate exists at `.github/workflows/ci-3-pr-producer.yml:112-157` (path filter for CI-3 infrastructure changes); no checkpoint write-back, no trigger-type label propagation |
| 11 | Operator snapshot via `sync-knowledgebase-state` -> `wiki/status.md` | **Partially Implemented (publisher exists; no checkpoint summary)** | Very High | `.github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py:24-29` defines `STATUS_ARTIFACT = "wiki/status.md"` and supports `--write-status-from`, but no `checkpoint`, `batch_id`, or trigger-type fields are written |
| 12 | `docs/architecture.md` updated for checkpoint lifecycle and lock ordering | **Not Implemented** | Very High | No matches for `checkpoint`, `infrastructure_revalidation`, `manual_rescan`, `wiki-processing`, or `wiki-processing-checkpoint.lock` in `docs/architecture.md` |
| 13 | `docs/mvp-runbook.md` updated for manual rescan and checkpoint recovery | **Not Implemented** | Very High | No matches for the same terms in `docs/mvp-runbook.md` |
| 14 | Tests cover all required acceptance categories (resume, bootstrap classification, stale revalidation, lock fail-closed, rename continuity, replay safety) | **Not Implemented** | Very High | Exhaustive `tests/` grep returned zero matches for the required symbols/terms; framework-level test files exist but contain no checkpoint coverage |
| 15 | CI workflow runs checkpoint registry tooling | **Not Implemented** | Very High | `.github/workflows/*.yml` has no matches for `wiki-processing`, `checkpoint`, or `manual_rescan` |
| 16 | `GovernedArtifactContract` enumerates the registry | **Not Implemented** | Very High | `scripts/kb/contracts.py:138-206` enumerates `wiki-index`, `wiki-log`, `wiki-open-questions`, `wiki-backlog`, `wiki-status`, `github-source-registry`, `external-asset`, `rejection-record` — no checkpoint entry |

---

## Material findings (ordered by severity)

### F1 — Trigger-name drift between ADR-026 and idea doc (must reconcile)

**Severity:** High — this affects the contract surface a future implementer will build to.

- **Idea doc** `docs/ideas/wiki-processing-checkpoint-registry.md:48` says `trigger` ∈ `{intake_driven, infrastructure_revalidation, manual_rescan}`.
- **ADR-026** `docs/decisions/ADR-026-wiki-processing-checkpoint-registry.md:64` says `trigger` ∈ `{automatic, manual_rescan}` — only two values.
- **ADR-027** `docs/decisions/ADR-027-infrastructure-validation-trigger-model.md:27-33` introduces `intake_driven` and `infrastructure_revalidation` as separate trigger paths and explicitly says: *"Update the checkpoint registry (when implemented) with `trigger: infrastructure_revalidation`"* — implying ADR-026's `automatic` value is now subdivided.
- **ADR-027 lists ADR-026 in "Related decisions"** (lines 76-77) but ADR-026's `## Status` (line 5) is still bare `Accepted` — per the repo's ADR-evolution rule in `.github/copilot-instructions.md`, ADR-026 should be updated to `Accepted — extended by ADR-027` and a `## Amendment` section added.

**Concrete remediation needed before implementation lands:**
- Either amend ADR-026 in place to enumerate the three-value trigger field and reference ADR-027, or move the canonical trigger enumeration entirely into ADR-027 and have ADR-026 defer to it. The current state forces a future implementer to choose between two contradictory specs.

### F2 — ADR-026 lacks the `Migration` / `Rollback` headings the idea doc requires

**Severity:** Medium.

- Idea doc §Phases.1 says: *"Draft ADR and contract together: decision, alternatives, migration, rollback, and operational consequences."*
- ADR-026 has `## Decision`, `## Alternatives considered`, `## Consequences`, `## References` but **no `## Migration`, `## Rollback`, or `## Operational consequences` headings**.
- The substance partially exists inside `## Consequences` (lines 207-219) and `## Retention` (lines 136-142), but does not satisfy the structured headings the idea doc itself prescribed.
- (Counter-example: ADR-027 does include `## Migration and rollback` at line 79 — so the precedent in this codebase is to have these as explicit headings.)

### F3 — Documentation cascade prescribed by the idea doc is not landed

**Severity:** Medium.

The idea doc §"Documentation cascade (implementation checklist)" lists four required updates. Three are absent and one is partially done:

| Required cascade | State |
|---|---|
| AGENTS.md write-surface matrix row(s) | **Absent** (deferred until writes are enabled — acceptable) |
| ADR in `docs/decisions/ADR-*.md` + README update | **Done** for ADR-026; README aligned |
| `docs/architecture.md` updated for checkpoint lifecycle and lock ordering | **Absent** |
| `docs/mvp-runbook.md` operator runbooks for manual rescan and checkpoint recovery | **Absent** |

The matrix-row deferral is defensible (no writes yet), but `docs/architecture.md` should at minimum reference ADR-026/ADR-027 so the layering picture matches the accepted decisions. The runbook gap is operationally riskier — when the registry lands, the runbook will need both manual_rescan and recovery procedures.

### F4 — CI-3 push-trigger preflight is the only piece of "trigger logic" that exists

**Severity:** Informational (positive partial progress).

ADR-027 lines 70-72 claim the preflight is *"implemented in `.github/workflows/ci-3-pr-producer.yml`, lines 109–147"*. **Verified:** the gate is at lines **112-157** (slight line drift from the ADR's stated range, immaterial). The gate:

- Allows `push` events only when changed paths match: `.github/workflows/ci-3-*`, `.github/skills/extract-entities-and-claims/**`, `.github/skills/validate-wiki-governance/**`, `.github/skills/synthesize-entity-page/**`, `.github/skills/synthesize-concept-page/**`.
- Rejects mixed scopes (any non-matching path fails the preflight).
- Uses the generic `prereq_trusted_trigger_model` indicator — **no literal `infrastructure_revalidation` / `intake_driven` / `manual_rescan` string appears in any workflow YAML or downstream code.** The trigger-type label propagation that ADR-026/ADR-027 envision (so a checkpoint row can record `trigger: infrastructure_revalidation`) is not yet wired.

### F5 — `wiki/status.md` publisher exists but emits no checkpoint summary

**Severity:** Informational.

- Idea doc says: *"Primary operator snapshot: `wiki/status.md` via `sync-knowledgebase-state`."*
- ADR-026 lines 128-133 reinforce this.
- `.github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py:24-29` defines `STATUS_ARTIFACT = "wiki/status.md"` and supports `--write-status-from`.
- No `checkpoint`, `batch_id`, `infrastructure_revalidation`, or `manual_rescan` references in the skill logic file. The publisher is ready; the schema/payload for the checkpoint summary is not.

### F6 — FRAMEWORK_BOUNDARY_DOCS rule will trip when a new `scripts/kb/**` entrypoint lands

**Severity:** Procedural (must-handle-on-implementation).

Per `.github/copilot-instructions.md`, `docs/ideas/wiki-curation-agent-framework.md` is monitored by `tests/kb/test_framework_contracts.py::test_boundary_docs_list_same_execution_surface` with literal `assertIn` against the entrypoint list. Today that doc lists only: `scripts/kb/ingest.py`, `scripts/kb/update_index.py`, `scripts/kb/lint_wiki.py`, `scripts/kb/qmd_preflight.py`, `scripts/kb/persist_query.py`. **Adding any new `scripts/kb/<checkpoint>.py` entrypoint will require updating this monitored doc verbatim, or the boundary-contract test will fail in CI.** Flag for the implementation phase.

### F7 — Contract-test cascades a future implementer will hit

**Severity:** Procedural (must-handle-on-implementation).

Per AGENTS.md "Contract test cascades" and copilot-instructions.md, three tests use exhaustive expected-tuple/dict assertions:
- `tests/kb/test_contracts.py:12-40` — `GOVERNED_ARTIFACT_IDS` / `GOVERNED_ARTIFACT_PATHS` expected tuples (must add checkpoint registry entry)
- `tests/kb/test_framework_write_surface_matrix.py:12-124` — `EXPECTED_WRITE_SURFACE_MATRIX_ROWS` dict (must add matrix-row entry)
- Plus the boundary-docs test above

None reference checkpoint today — they will block any partial implementation that adds the artifact contract or matrix row without simultaneously updating expected sets.

### F8 — Sibling idea doc for ADR-027 not authored

**Severity:** Low.

ADR-027 stands alone in `docs/decisions/` with no companion `docs/ideas/infrastructure-validation-trigger-model.md`. Of 10 idea docs in `docs/ideas/`, 9 are `Implemented` (or `Implemented (Phase 1)`) and only this one is `In Progress`. The repo pattern is to back each ADR with an idea doc; ADR-027 is the only Accepted ADR in the recent set without one. Not blocking but worth noting for the documentation-cascade audit.

---

## Counter-examples checked

For each "nothing exists" claim above I searched for the actual artifact (not just the term) before reporting. Specifically:

- **"No registry artifact"** — verified `raw/wiki-processing/` does not exist on disk (not just absent from grep).
- **"No runtime helpers"** — searched all of `scripts/**` (not just `scripts/kb/**`); the only `bootstrap` hits were in `scripts/fleet/**` (unrelated TypeScript fleet tooling).
- **"No tests"** — adjacent precedent tests for `github_monitor/` and `drive_monitor/` registries were located and confirmed structurally analogous; their absence for `wiki-processing` is therefore a genuine gap, not a naming/path mismatch.
- **"No matrix row"** — searched the matrix for all four candidate substrings (`wiki-processing`, `checkpoint`, the writable path, the lock path) — none match.

No counter-examples found to overturn the "not implemented" verdicts in items 4-16.

---

## What IS in place (positive baseline)

1. **ADR-026 published and indexed** with substantive Decision, Alternatives, Consequences sections.
2. **ADR-027 published and indexed** with the trigger model and CI-3 preflight gate cross-reference.
3. **CI-3 infrastructure-revalidation push gate** working at `.github/workflows/ci-3-pr-producer.yml:112-157`.
4. **`wiki/status.md` publisher** ready to receive a checkpoint summary payload once the writer side exists.
5. **Adjacent contract templates** (`schema/github-source-registry-contract.md`, `schema/drive-source-registry-contract.md`) provide a clean precedent the new contract can mirror.
6. **Adjacent test patterns** (`tests/github_monitor/test_check_drift.py`, `tests/drive_monitor/test_registry.py`) provide a clean precedent for the new test suite.

---

## Recommended next actions (ordered)

These come from the verification, not from the implementer's plan. They mirror the idea doc's Phase ordering with the gaps filled in.

1. **Reconcile ADR-026 with ADR-027** — amend ADR-026's `## Status` to `Accepted — extended by ADR-027`, add a `## Amendment` section noting the three-value trigger field, and update the README row's status to match. This unblocks every subsequent step by removing the spec ambiguity.
2. **Add `## Migration` and `## Rollback` headings to ADR-026** to match ADR-027's structure and the idea doc's Phase 1 requirement.
3. **Land `schema/wiki-processing-checkpoint-registry-contract.md`** mirroring the structure of `schema/drive-source-registry-contract.md` (the more recent of the two precedents).
4. **Update `schema/CONTEXT.md`** File Roles list with the new contract; bump `last_updated`.
5. **Update `docs/architecture.md`** to document checkpoint lifecycle and lock ordering; cite ADR-026 and ADR-027.
6. **Update `docs/mvp-runbook.md`** with `manual_rescan` and recovery procedures.
7. **Only then** open the runtime work: add `scripts/kb/<checkpoint>.py`, the matrix row, the lock declaration in `contracts.py`, and the test suite — in lockstep with the boundary-docs and expected-tuple cascades (F6, F7).

---

## Analytical framing labels (for transparency)

- *"Drift" verdicts* are this report's characterization based on comparing the idea doc, ADR-026, and ADR-027 line-by-line. The repo's own ADR-evolution rule (in `.github/copilot-instructions.md`) is the cited authority.
- *"Partially Implemented"* is reserved for surfaces where part of the proposed wiring is live and verified (CI-3 push gate; `wiki/status.md` publisher) but the checkpoint payload is absent. Calling these "Implemented" would be misleading; calling them "Not Implemented" would obscure the real partial progress.
- *"Not Implemented"* is binary: no file, no symbol, no reference found by exhaustive grep. Each such verdict is backed by either a directory listing or a grep result with the patterns documented inline above.

---

## Verification trail

- **Subagent A** (verify-adr-doc-cascade): confirmed ADR-026/027 + README rows + architecture/runbook absence + idea-doc `Status` field.
- **Subagent B** (verify-runtime-implementation): confirmed absence of `raw/wiki-processing/`, lock file references, runtime helpers, bootstrap, and `wiki/status.md` checkpoint payload.
- **Subagent C** (verify-schema-and-matrix): confirmed absence of contract, matrix row, governed-artifact contract entry, and lock-file-registry entry; located precedent templates.
- **Subagent D** (verify-tests-and-validation): confirmed absence of acceptance tests, located contract-test cascade locations, and located adjacent test templates.
- **Direct primary-source reads** by the orchestrator: ADR-026 (full file), ADR-027 (full file), `docs/decisions/README.md` (relevant lines), `.github/workflows/ci-3-pr-producer.yml` (lines 100-160 + grep over trigger-term variants).

All factual statements above trace to either a file:line citation, a directory-listing result, or a documented grep pattern that returned zero matches.
