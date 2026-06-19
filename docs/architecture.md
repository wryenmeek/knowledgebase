# Knowledgebase Architecture

This document summarizes the implemented architecture and governance model from
[`raw/processed/SPEC.md`](../raw/processed/SPEC.md), and points to stable ADRs for key decisions.

## Goals

The system is designed to keep knowledge:

1. **Persistent** (wiki artifacts are stored in-repo, not only generated at query-time).
2. **Traceable** (claims are tied to canonical SourceRef citations).
3. **Deterministic** (policy-driven behavior with explicit failure semantics).
4. **Auditable** (state changes are visible through git history and `wiki/log.md`).

## Repository zones

| Zone | Role | Trust level |
|---|---|---|
| `raw/inbox/**` | New source inputs pending ingest | Untrusted input |
| `raw/processed/**` | Post-ingest source artifacts | Immutable source-of-truth |
| `raw/assets/**` | Vendored external assets | Authoritative only when checksummed |
| `raw/github-sources/**` | GitHub source monitor registries and pending-ingest handoffs | Mutable; governed by `schema/github-source-registry-contract.md` |
| `raw/drive-sources/**` | Google Drive source monitor registries | Mutable; governed by `schema/drive-source-registry-contract.md` |
| `raw/rejected/` | Write-once rejection records for sources that failed intake (ADR-013) | Immutable post-write |
| `wiki/**` | Synthesized knowledge artifacts | Controlled write surface |
| `schema/**` | Page/ingest contracts | Controlled write surface |
| `scripts/kb/**` + `tests/kb/**` | Automation implementation and verification | Controlled write surface |

## Canonical utility modules

Before implementing any new helper, check these five canonical modules. See ADR-011.

| Module | Scope |
|---|---|
| `scripts/kb/page_template_utils.py` | Frontmatter parsing, heading extraction, `TOPICAL_NAMESPACES`, wiki-page structural helpers. |
| `scripts/kb/write_utils.py` | Safe file writes, atomic operations, `check_no_symlink_path`, write-lock primitives, rollback helpers. |
| `scripts/kb/contracts.py` | Status enums, reason codes, governed artifact contracts, result type definitions. |
| `scripts/_optional_surface_common.py` | Optional-surface CLI framework, `SurfaceResult`, `run_surface_cli`, `JsonArgumentParser`. |
| `scripts/kb/agents_matrix_utils.py` | Agent write-surface matrix parsing and validation utilities used by pre-commit hooks. |

**Rule:** Import from canonical modules rather than re-implementing equivalent logic. Extend the canonical module if a related helper needs expanding. Local copies of module-level constants require a `# keep in sync with <module>.<CONSTANT>` drift guard.

## Core workflow

1. Ingest source content from `raw/inbox/**`.
2. Generate/update wiki pages (`wiki/sources/**`, `wiki/entities/**`, `wiki/concepts/**`).
3. Rebuild deterministic index (`wiki/index.md`).
4. Append `wiki/log.md` only when a real state change occurred.
5. Move successfully ingested inputs to `raw/processed/**`.
6. Enforce strict lint and test gates before write-capable automation proceeds.

## Automation model (CI-1..CI-6)

| CI | Responsibility | Write capability |
|---|---|---|
| **CI-1** | Trusted-trigger gatekeeper/handoff | No |
| **CI-2** | Read-only diagnostics and analysis | No |
| **CI-3** | PR-producing write path with allowlists/preflight plus split synthesis boundary: low-privilege `synthesis-curator` job performs GitHub Models extraction (`models: read`, `contents: read`) and hands off deterministic extraction bundles; write-capable `pr-producer` job applies bundles and opens/updates PR (`contents: write`, `pull-requests: write`, no `models` scope) | Yes (allowlisted paths only, including `wiki/entities/**` and `wiki/concepts/**`) |
| **CI-4** | Framework writer: staged agent-generated content for `docs/**` and `.github/skills/**` | Yes (`docs/**`, `.github/skills/**`; workflow_dispatch only; approval-gated) |
| **CI-5** | GitHub source monitor: scheduled drift detection (read-only) + PR-producing fetch/synthesize path | Drift job: No. Write jobs: Yes (`raw/assets/**`, `raw/github-sources/**`, bounded `wiki/**`) |
| **CI-6** | Google Drive source monitor: scheduled drift detection (read-only) + approval-gated fetch/synthesize/cursor-advance path | Drift job: No. Write jobs: Yes (`raw/assets/**`, `raw/drive-sources/**`, bounded `wiki/**`) |

This split is intentional: it isolates trust checks, diagnostics, and write operations
so permission scope can stay minimal for each path.

For write-capable optional-surface CLI entrypoints, write confirmation follows
[`ADR-030`](decisions/ADR-030-cli-write-confirmation.md): `--apply` is the
preferred spelling, and `--approval approved` remains a compatibility alias
during migration.

## Fleet orchestration

`scripts/fleet/` is a **separate TypeScript/Bun runtime** that integrates with the
[Jules SDK](https://www.npmjs.com/package/@google/jules-sdk) to automate issue-to-PR
dispatch and merge. It is independent of the Python `scripts/kb/` layer and is
**not covered by `pytest`**.

### Entry points

| Script | Purpose |
|---|---|
| `fleet-plan.ts` | Plans a batch of Jules tasks from open GitHub issues |
| `fleet-dispatch.ts` | Dispatches planned tasks to Jules for parallel execution |
| `fleet-merge.ts` | Merges completed Jules PRs that pass CI |
| `fleet-analyze.ts` | Analyzes dispatch/merge results for reporting |

### CI workflows

- **`fleet-dispatch.yml`** — triggered by schedule or `workflow_dispatch`; runs `fleet-dispatch.ts`
- **`fleet-merge.yml`** — triggered after CI passes on fleet PRs; runs `fleet-merge.ts`

### Build verification

After any edit to `scripts/fleet/`, verify TypeScript compiles cleanly:

```bash
cd scripts/fleet && bun build fleet-plan.ts fleet-dispatch.ts fleet-merge.ts fleet-analyze.ts
```

**Important:** `pytest` passing does **not** imply TypeScript is clean. Always run
`bun build` after editing fleet files. Fleet-produced PRs enter normal CI review
(CI-1..CI-3) and do not bypass write allowlists or the `wiki/.kb_write.lock`
concurrency model.

## Wiki-curation framework MVP boundary

The wiki-curation agent framework was originally ratified as an **MVP control
plane** over the existing knowledgebase tooling, not a replacement runtime.
That historical MVP-only boundary still defines what is implemented today. The
accepted layering and packaging rule live in
[`ADR-007`](decisions/ADR-007-control-plane-layering-and-packaging.md), which
now also approves a narrow set of post-MVP package surfaces without changing
CI permissions, source-boundary rules, concurrency guards, or deny-by-default
write behavior.

| Layer | Package location | MVP role now |
|---|---|---|
| Global policy and trust boundaries | `AGENTS.md` + ADRs | Keep fail-closed, provenance, append-only log, and write-scope rules always on. |
| Agent personas | `.github/agents/**` | Define router/worker missions, handoffs, and stop conditions. |
| Skill workflows and thin wrappers | `.github/skills/**` | Hold procedural workflow docs plus narrow wrappers that invoke deterministic tooling. |
| Deterministic execution surface | `scripts/kb/**` | Remains the authoritative Python implementation for ingest, index, lint, qmd preflight, query persistence, and batch query persistence. `scripts/kb/batch_persist_query.py` (Phase 3) adds batch write capability: single `wiki/.kb_write.lock` acquisition for the entire batch, per-entry policy evaluation, and writes bounded to `wiki/analyses/**`, `wiki/index.md`, and `wiki/log.md`. |
| Verification surface | `tests/kb/**` | Validates the deterministic execution layer and any framework references to it. |

### In scope for the framework MVP

- Agent and skill scaffolding under `.github/agents/**` and `.github/skills/**`.
- Thin wrapper surfaces around existing `scripts/kb/**` entrypoints where they
  are useful and MVP-safe. Current landed wrappers cover governance validation
  and index/state synchronization; ingest and query persistence still run
  through direct `scripts/kb/ingest.py` and `scripts/kb/persist_query.py`
  execution today.
- Architecture, ADR, and operator documentation that explains the boundary and
  where future extensions belong.

### Deferred beyond the framework MVP

- Porting the broader cross-repository script backlog into new `scripts/**`
  trees for validation, reporting, context sync, or maintenance.
- Replacing the current `scripts/kb/**` entrypoints with agent-native logic.
- Adding heavy repository crawlers, external-service integrations, or batch
  reporting pipelines before the scaffolding and wrapper layer is in place.

### Approved post-MVP package surfaces

These surfaces are approved for future framework implementation work even
though they are not all landed today:

| Surface | Approved post-MVP use | Invariants that still apply |
|---|---|---|
| `scripts/validation/**` | Deterministic validators, freshness checks, and baseline/snapshot utilities | CI-1 and CI-2 stay read-only, and CI-3 may only write through explicit allowlists plus preflight. |
| `scripts/reporting/**` | Repository-scoped quality and coverage reporting | Packaging approval does not grant new write authority; undeclared paths remain deny-by-default. Landed surfaces: content_quality_report.py, quality_runtime.py, coverage_report.py (Phase 4). |
| `scripts/context/**` + `scripts/maintenance/**` | Context-sync and maintenance orchestration invoked by thin skills | Heavy repo-wide logic still sits behind explicit wrappers and fail-closed checks. |
| `scripts/fleet/**` | TypeScript/Bun fleet orchestration for parallel Jules-based issue-to-PR dispatch | Fleet scripts are a TypeScript/Bun project orthogonal to the Python write-surface matrix. Fleet-produced PRs enter normal CI review (CI-1..CI-3). Fleet does not bypass write allowlists or the `wiki/.kb_write.lock` concurrency model. |
| `scripts/ingest/**` | Heavyweight ingest/conversion helpers | ADR-006 still limits authoritative ingest inputs to `raw/inbox/**` plus checksummed `raw/assets/**`. |
| `scripts/github_monitor/**` | GitHub source monitoring: drift detection, asset fetching, diff-aware wiki synthesis | ADR-012 governs the fetch-and-vendor cycle; `raw/assets/{owner}/{repo}/{sha}/**` assets are authoritative only when checksummed per ADR-006; write-capable surfaces must be declared in `AGENTS.md` before writing. |
| `scripts/drive_monitor/**` | Google Drive source monitoring: drift detection, asset fetching, diff-aware wiki synthesis | ADR-021 governs the fetch-and-vendor cycle; `raw/assets/gdrive/{alias}/{file_id}/{version}/**` assets are authoritative only when checksummed; write-capable surfaces must be declared in `AGENTS.md` before writing. |
| `scripts/hooks/**` | Pre-commit, PostToolUse advisory, and CI governance hook scripts | Hooks are read-only — no repository writes. They enforce local governance guardrails (ADR-016 authorizes this family; ADR-028 governs the Locality 4 advisory). |
| `scripts/init.py` | Operator-only fresh-instance initialization for template instances; resets all content directories and regenerates skeleton artifacts (`raw/processed/SPEC.md`, sample inbox doc, stub wiki artifacts) | Operator-use only — never invoke in CI automation on a live instance; requires `--fresh` flag; `--yes` flag requires `INIT_ALLOW_WIPE=1` env var; checks `wiki/.kb_write.lock` before any write (blocks if held); uses `check_no_symlink_path` from `write_utils`; sole declared exception to the append-only `wiki/log.md` guardrail (full overwrite on clean-slate reset). |

Relay HTTP wrappers for the GitHub and Drive monitors share WSGI envelope helpers
in `scripts/relay_wsgi_common.py`. Contract-specific validation and dispatch logic
remains in `scripts/github_monitor/_relay.py` and `scripts/drive_monitor/_relay.py`.

Any future post-MVP writer that touches shared wiki artifacts must keep the
ADR-005 workflow-concurrency plus `wiki/.kb_write.lock` model, and any
post-MVP runtime path must preserve the CI-1/CI-2/CI-3 split from ADR-004.

## Operator lane sequencing

The implemented control plane is intentionally lane-first. Operators should treat
the following order as mandatory:

| Phase | Required order | Operator rule |
|---|---|---|
| HITL/AFK classification | `knowledgebase-orchestrator` | Work items are classified as HITL (human-in-the-loop, full persona pipeline) or AFK (away-from-keyboard, eligible for fast-path per ADR-014 allowlist) at routing time by the orchestrator. Unmatched items default to HITL (deny-by-default). |
| Entry + ingest-safe gate | `knowledgebase-orchestrator` → `source-intake-steward` → `evidence-verifier` → `policy-arbiter` | No downstream wiki/content/topology lane opens before this sequence succeeds. |
| Policy-cleared drafting | `synthesis-curator` | Drafting is limited to the cleared scope and remains subject to governed publication checks; any richer post-draft `evidence-verifier` lane is future-state follow-on work rather than a current MVP runtime guarantee. |
| Policy-cleared query/discovery | `query-synthesist` or `topology-librarian` | Query answers read the curated wiki first; governed follow-up stays on governed persistence or index-sync paths. |
| AFK maintenance lane — Tier 1 (deterministic write) | Python scripts invoked directly in a CI workflow step | Bounded, deterministic writes on the ADR-014 allowlist (`last_updated`, `quality_assessment.freshness_date`, YAML normalization, index regeneration, redirect appends). No LLM in path. Gate: `validate_afk_output.py` (5-check inline safety net). Token: GH App. Output: PR for human merge. See ADR-022. |
| AFK maintenance lane — Tier 2 (advisory pass) | `copilot -p` skill invocations (read-only) | Read-only analysis requiring LM judgment: `suggest-backlinks`, `cross-reference-symmetry-check`, `analyze-missed-queries`, `detect-ai-tells`, and equivalent advisory skills. No governed write in this tier. Output: structured findings artifact. Human notified only when downstream aggregation threshold is exceeded. See ADR-022. |
| Maintenance/quality follow-up | `maintenance-auditor`, `change-patrol`, `quality-analyst` | These personas triage, audit, and recommend; any content-changing follow-up routes back through `knowledgebase-orchestrator`. |
| Human escalation | Human Steward | Required when contradictions, deletions, identity ambiguity, or policy conflicts remain unresolved. |

This sequencing is the maintainers' operative interpretation of the framework
now landed in `.github/agents/**`. It keeps governance ahead of synthesis and
prevents ADR-007 drift into a second runtime.

## Persona roster under `.github/agents/`

| Group | Category | Persona | Current role |
|---|---|---|---|
| Entry gate | `kb-workflow` | `knowledgebase-orchestrator` | Classifies work, enforces boundary rules, and selects the safe lane. |
| Ingest-safe gate | `kb-workflow` | `source-intake-steward` | Guards `raw/inbox/**`, provenance, and immutable intake packaging. |
| Ingest-safe gate | `kb-workflow` | `evidence-verifier` | Requires deterministic provenance/evidence completeness before policy review. |
| Ingest-safe gate | `kb-workflow` | `policy-arbiter` | Applies repository governance and blocks downstream work until cleared. |
| Policy-cleared resolution | `kb-workflow` | `entity-resolution-and-canonicalization` | Resolves canonical identity conflicts flagged by `policy-arbiter` before synthesis can proceed. |
| Downstream governed lane | `kb-workflow` | `synthesis-curator` | Produces policy-cleared draft/update packages without direct publication. |
| Downstream governed lane | `kb-workflow` | `query-synthesist` | Answers from curated wiki first and routes durable results back through governed persistence. |
| Downstream governed lane | `kb-workflow` | `topology-librarian` | Applies taxonomy/index follow-up inside the cleared scope only. |
| Review/maintenance lane | `kb-workflow` | `maintenance-auditor` | Audits stale/orphaned/semantic maintenance risk without inventing new automation. |
| Review/maintenance lane | `kb-workflow` | `change-patrol` | Routes changed-source/content risk back through the correct existing lane. |
| Review/maintenance lane | `kb-workflow` | `quality-analyst` | Turns existing repo evidence into prioritized quality/discoverability follow-up. |
| Review support | `dev-support` | `code-reviewer` | General review persona for correctness/readability/architecture/security/performance checks. |
| Review support | `dev-support` | `test-engineer` | Test-strategy and coverage specialist for framework or tooling changes. |
| Review support | `dev-support` | `security-auditor` | Security-focused review persona for hardening and threat analysis. |
| Dev support | `dev-support` | `documentation-engineer` | Authors, audits, and maintains documentation artifacts (ADRs, SKILL.md, architecture docs, README, docstrings). |
| Dev support | `dev-support` | `solutions-architect` | Identifies structural improvement opportunities and produces governed architecture proposals and refactoring plans. |
| Dev support | `dev-support` | `framework-engineer` | Authors new skills, audits framework integrity, and maintains the `.github/` engineering surface. |

## Skill layer under `.github/skills/`

| Skill slice | Status in MVP | Repo-local examples |
|---|---|---|
| Governance workflows + landed wrappers | Active, wrapper-backed | `validate-wiki-governance`, `sync-knowledgebase-state`, `validate-inbox-source`, `append-log-entry`, `check-link-topology`, `compute-kpis`, `analyze-missed-queries`, `context-engineering`, `documentation-and-adrs`, `enforce-page-template`, `enforce-repository-boundaries`, `run-deterministic-validators`, `write-sourceref-citations`, `log-intake-rejection`, `manage-redirects-and-anchors`, `suggest-backlinks`, `audit-knowledgebase-workspace` (read-only orchestrator scaffold; classifier cache, friction queries, stale generator, and redundancy generator have landed under `logic/`, and the finding schema has landed under the skill-local `schema/`, but these components are not yet wired into the orchestrator) (all wrapper-backed skills here have `logic/` Python wrappers) |
| Knowledge-structure contracts | Active, doc-only | `information-architecture-and-taxonomy`, `ontology-and-entity-modeling`, `knowledge-schema-and-metadata-governance`, `entity-resolution-and-canonicalization`, `search-and-discovery-optimization` |
| Policy/evidence/self-audit workflows | Active, doc-only | `verify-citations`, `enforce-npov`, `record-open-questions`, `log-policy-conflict`, `review-wiki-plan` |
| Ingest and query persistence wrappers | Active, doc-only | `run-ingest`, `persist-query-result` |
| Intake provenance workflows | Active, doc-only | `register-source-provenance`, `checksum-asset`, `create-intake-manifest`, `log-ingest-event` |
| Synthesis workflows | Active, mixed | `extract-entities-and-claims` (has `logic/`; calls GitHub Models API, read-only extraction bundle), `synthesize-entity-page` (has `logic/`; writes `wiki/entities/**` drafts via CI-3), `synthesize-concept-page` (has `logic/`; writes `wiki/concepts/**` drafts via CI-3), `claim-inventory` (doc-only) |
| Maintenance-arm workflows | Active, doc-only | `semantic-wiki-lint`, `freshness-audit`, `cross-reference-symmetry-check`, `propose-supersede-or-archive`, `append-maintenance-log`, `patrol-human-edits`, `route-noncompliant-edit-for-review`, `manage-redirects-and-anchors`, `detect-original-research`, `compare-against-existing-pages`, `escalate-contradictions` |
| Topology / discovery workflows | Active, has logic/ | `suggest-backlinks` — neighborhood-scoped scanner (`logic/suggest_backlinks.py`) proposes backlink candidates; no direct page mutation |
| Quality and orchestration workflows | Active, doc-only | `score-page-quality`, `compute-kpis`, `analyze-missed-queries`, `prioritize-curation-backlog`, `route-wiki-task`, `plan-wiki-job`, `fail-closed-on-errors`, `quality-pass-chain` |
| Orientation and stress-test workflows | Active, doc-only | `zoom-out`, `grill-me` |
| Agent-to-agent workflows | Active, doc-only | `caveman` |
| Prose and editorial workflows | Active, doc-only | `edit-article` |
| Rejection registry workflows | Active, mixed | `log-intake-rejection` (has `logic/` scaffold), `reconsider-rejected-source` (doc-only) |

The skill layer carries workflow procedure and thin wrapper logic while leaving
deterministic execution in `scripts/kb/**`. No framework skill should add a new
repo-level `scripts/validation/*`, `scripts/reporting/*`, `scripts/context/*`,
or `scripts/maintenance/*` tree in MVP.

## Framework verification entrypoints

Operators can validate the landed framework with these repo-local entrypoints:

| Check | Command | Primary evidence |
|---|---|---|
| Fixed governance gate | `python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py` | Wrapper over `scripts/kb/qmd_preflight.py`, `scripts/kb/update_index.py`, and `scripts/kb/lint_wiki.py`; add `--validator freshness-threshold` to opt in to page-age checking (not run by default; requires `scripts/validation/check_doc_freshness.py`) |
| Advisory freshness sweep | `.github/workflows/wiki-freshness.yml` (scheduled Monday 03:30 UTC; `workflow_dispatch` with `enforcement_mode` input) | Three-step: (1) `check_doc_freshness.py --scope wiki --max-age-days 90`; (2) `classify_stale.py` classifies stale pages as `afk-candidate` or `hitl` and writes `freshness-routing.json` (advisory artifact; a downstream `workflow_run` Tier 1 AFK workflow will consume this per ADR-022); (3) `validate_wiki_governance.py --mode signal` with all 5 validators including `freshness-threshold`. Always advisory unless `blocking` mode is selected. |
| Backlink suggestions | `python3 .github/skills/suggest-backlinks/logic/suggest_backlinks.py <page> [--wiki-root wiki]` | Neighborhood-scoped (same namespace + linked pages); returns JSON `BacklinkProposal` list; read-only |
| Read-only state-sync precheck | `python3 .github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py --check-only [--artifact wiki/index.md\|wiki/log.md\|wiki/open-questions.md\|wiki/backlog.md\|wiki/status.md]` | Confirms approved governed-artifact routing; index precheck still runs the allowlisted index/lint path |
| Write-capable governed sync | `python3 .github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py --write-index` (or the typed log/open-questions/backlog/status sync flags) | Mutates only approved governed artifacts after mode-specific checks and ADR-005 locking succeed |
| Focused framework suite | `python3 -m pytest tests/kb/test_framework_contracts.py tests/kb/test_framework_skills.py tests/kb/test_framework_agents.py tests/kb/test_framework_references.py tests/kb/test_skill_wrappers.py -v` | `tests/kb/test_framework_contracts.py`, `test_framework_skills.py`, `test_framework_agents.py`, `test_framework_references.py`, `test_skill_wrappers.py` |
| Full repository suite | `python3 -m pytest tests/ -q` | End-to-end regression safety beyond framework-specific checks |

## Write and safety controls

- Canonical write allowlist for automation: `wiki/**`, `wiki/index.md`, `wiki/log.md`, `raw/processed/**`, `raw/rejected/**`.
- CI-3 has one narrow delete-only exception outside the write allowlist: after a successful ingest handoff, it may remove `raw/inbox/**` files listed in the generated ingest manifest. No new writes under `raw/inbox/**` are allowed.
- The current CI/runtime write allowlist above is unchanged by the approved
  post-MVP package surfaces; those surfaces only widen where future code may
  live, not what automation may write by default.
- **Scanner path bounds:** any future read-only scanner that resolves file
  paths from page input must validate resolved paths with
  `Path.is_relative_to(wiki_root)` before opening them. Established in
  `suggest_backlinks.py`; `str.startswith()` is insufficient (sibling
  directories match without a separator).
- Raw immutability: `raw/processed/**` must not be mutated after ingest.
- Ingest-time SourceRefs may use provisional placeholder git SHAs; only reconciled commit-bound SourceRefs whose `git_sha` resolves to a real revision containing the cited artifact bytes count as authoritative provenance.
- Concurrency guard: workflow-level concurrency group plus local lock file (`wiki/.kb_write.lock`).
- Sibling governance locks (domain-scoped, not shared with `wiki/.kb_write.lock`):
  `raw/.github-sources.lock` (GitHub source registry writes, ADR-012),
  `raw/.drive-sources.lock` (Drive source registry writes, ADR-021),
  `raw/.rejection-registry.lock` (rejection registry writes, ADR-013),
  and `.github/.customizations.lock` (locality-ladder customization writes,
  ADR-028). Each lock guards a single registry/zone; lock-ordering rules
  for any surface that touches both `wiki/**` and a sibling registry are
  documented in that surface's row in the AGENTS.md write-surface matrix
  (acquire `wiki/.kb_write.lock` first when both are needed).
- Checkpoint registry lock:
  `raw/.wiki-processing-checkpoint.lock` guards writes to
  `raw/wiki-processing/wiki-processing-checkpoint-registry.json` (ADR-026).
  Failure mode is fail-closed on contention or acquisition failure.
- Checkpoint lock ordering: any run that updates both wiki content and
  checkpoint state acquires `wiki/.kb_write.lock` first, then
  `raw/.wiki-processing-checkpoint.lock`. Reverse order is a deadlock hazard
  and is rejected by the deterministic execution surface.
- **`wiki/log.md` append-only guardrail:** all governed surfaces must append-only; the sole declared exception is `scripts/init.py --fresh`, which performs a full overwrite as part of a clean-slate template reset. This exception is documented in `AGENTS.md` and is intentional.
- Fail-closed behavior: missing prerequisites, permission mismatches, or lock contention stop writes.
- Policy-gated query persistence: write only when `auto_persist_when_high_value` criteria pass.
- Paths outside the current MVP surfaces plus the approved post-MVP package
  surfaces remain deny-by-default for framework automation unless a narrower
  contract explicitly names them.

## Governed constants

Configuration values that affect governance decisions. Changes to these values
require documented rationale.

| Constant | Value | Used by | Rationale |
|---|---|---|---|
| `freshness_stale_days` | 90 | `check_doc_freshness.py --max-age-days`, `wiki-freshness.yml` | Pages not updated in 90+ days are flagged for review. Aligns with quarterly review cadence. |
| `freshness_afk_threshold_days` | 180 | `classify_stale.py --afk-threshold-days`, `wiki-freshness.yml` | Pages stale 90–179 days likely need only metadata refresh (AFK-candidate). Pages ≥180 days may need content review and re-sourcing (HITL). The gap between 90 and 180 catches pages that are stale enough to notice but may still need editorial judgment. |
| `missing_data_default_days` | 999 | `classify_stale.py` | Pages with missing `last_updated` frontmatter default to 999 days stale, classifying as HITL (deny-by-default). |

## Wiki processing checkpoint registry

> **Runtime landed; CI wiring/bootstrap pending.** The PR2 schema contract,
> `scripts/kb/contracts.py` constants (lock path, trigger and artifact
> enums, dependency-fingerprint dict, retention thresholds), and the
> `analysis_fingerprint()` helper landed in PR #213. The PR3 runtime
> (`scripts/kb/checkpoint_registry.py`) landed the bootstrap/mutate/verify
> entrypoint in PR #233. PR4 CI-3 wiring and the HITL bootstrap execution
> remain pending.

The wiki processing pipeline maintains a governed checkpoint registry
under `raw/` so partial fail-closed runs can resume and changed outputs can
be re-evaluated without storing workflow state in topical wiki content. The
registry is observational — no checkpoint entry can
authorize a write that governance would otherwise block.

| Aspect | Value |
|---|---|
| Registry artifact | `raw/wiki-processing/wiki-processing-checkpoint-registry.json` |
| Schema contract | `schema/wiki-processing-checkpoint-registry-contract.md` |
| Runtime entrypoint | `scripts/kb/checkpoint_registry.py` |
| Dedicated lock | `raw/.wiki-processing-checkpoint.lock` |
| Lock order with wiki writes | `wiki/.kb_write.lock` first, then the checkpoint lock (enforced by checkpoint registry runtime) |
| Operator snapshot | `wiki/status.md` via `sync-knowledgebase-state` |
| Trigger model | `intake_driven`, `infrastructure_revalidation`, `manual_rescan` (declared in ADR-027) |

The registry tracks both batch-level state (`batch_id`, `trigger`,
`started_at`, `finished_at`, `status`, `input_fingerprint`,
`error_summary`) and item-level state (`item_key`, `output_path`,
`path_aliases`, `artifact_type`, `source_fingerprint`,
`dependency_fingerprint`, `status`, `last_attempted_at`,
`last_succeeded_at`, `last_error`, `last_successful_batch_id`). Identity
keys follow the repository's canonical-identity rules (ADR-009); paths
are mutable projections recorded in `path_aliases` on rename or move.

Bootstrap is an explicit mode (never auto-on-first-write) and emits a
reconciliation report before any registry write. See
[`docs/ideas/wiki-processing-checkpoint-registry.md`](ideas/wiki-processing-checkpoint-registry.md)
for the full Path C-prime implementation plan and ADR-026/ADR-027 for
the canonical decisions.

## Decision records

Key architecture decisions are captured in ADRs:

- [`ADR-001`](decisions/ADR-001-persistent-wiki-architecture.md): persistent repository-scoped wiki model
- [`ADR-002`](decisions/ADR-002-frontmatter-and-sourceref-contract.md): required frontmatter and SourceRef provenance
- [`ADR-003`](decisions/ADR-003-policy-gated-query-persistence.md): deterministic query-persist policy and envelopes
- [`ADR-004`](decisions/ADR-004-split-ci-workflow-governance.md): split CI governance and permission profiles
- [`ADR-005`](decisions/ADR-005-write-concurrency-guards.md): workflow + local lock concurrency model
- [`ADR-006`](decisions/ADR-006-authoritative-source-boundary.md): repository-local authoritative source boundary
- [`ADR-007`](decisions/ADR-007-control-plane-layering-and-packaging.md): framework control-plane layering and packaging rule
- [`ADR-008`](decisions/ADR-008-agent-writes-to-framework-paths.md): authorize agent write paths for `.github/skills/**` and `docs/**`
- [`ADR-009`](decisions/ADR-009-canonical-identity-and-anchor-management.md): canonical identity, slug normalization, and redirect management
- [`ADR-010`](decisions/ADR-010-convert-sources-adr006-compliance-review.md): ADR-006 compliance review for `convert_sources_to_md.py`
- [`ADR-011`](decisions/ADR-011-canonical-utility-reuse.md): canonical utility modules and single-definition rule
- [`ADR-012`](decisions/ADR-012-github-source-monitoring.md): GitHub source monitoring pipeline
- [`ADR-013`](decisions/ADR-013-rejected-source-registry.md): write-once intake rejection records
- [`ADR-014`](decisions/ADR-014-hitl-afk-work-classification.md): HITL/AFK work classification and deny-by-default routing
- [`ADR-015`](decisions/ADR-015-extended-ci-trust-model.md): extended CI trust model — CI-4 framework-writer, CI-5 GitHub monitor, and CI-6 Google Drive monitor
- [`ADR-016`](decisions/ADR-016-pre-commit-hooks-governance.md): raw git hooks over pre-commit framework for local governance checks
- [`ADR-017`](decisions/ADR-017-agent-persona-category-taxonomy.md): two-category agent persona taxonomy (kb-workflow / dev-support)
- [`ADR-018`](decisions/ADR-018-context-md-vocabulary-pattern.md): CONTEXT.md files as structured agent-vocabulary artifacts
- [`ADR-019`](decisions/ADR-019-fleet-jules-orchestration.md): Jules-based fleet orchestration for parallel issue-to-PR dispatch
- [`ADR-020`](decisions/ADR-020-post-mvp-package-family-criteria.md): criteria for approving post-MVP script package families
- [`ADR-021`](decisions/ADR-021-google-drive-source-monitoring.md): Google Drive source monitoring pipeline
- [`ADR-022`](decisions/ADR-022-afk-uses-scripts-hitl-uses-copilot-cli.md): three-tier CI executor model — AFK writes use scripts, AFK advisory passes and HITL use Copilot CLI
- [`ADR-023`](decisions/ADR-023-batch-query-persistence-design.md): batch query persistence design (single lock, partial failure, and size limits)
- [`ADR-024`](decisions/ADR-024-synthesis-curator-stage-design.md): CI-3 synthesis curator stage design for entity/concept draft generation
- [`ADR-025`](decisions/ADR-025-runtime-budget-contract-scope.md): runtime-budget contract scope and schema/workflow parity requirements
- [`ADR-026`](decisions/ADR-026-wiki-processing-checkpoint-registry.md): wiki processing checkpoint registry for resumed and revalidated synthesis
- [`ADR-027`](decisions/ADR-027-infrastructure-validation-trigger-model.md): infrastructure validation trigger model for CI-3
- [`ADR-028`](decisions/ADR-028-instruction-locality-ladder.md): instruction locality ladder and Locality 4 trailer governance
