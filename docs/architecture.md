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
| `wiki/**` | Synthesized knowledge artifacts | Controlled write surface |
| `schema/**` | Page/ingest contracts | Controlled write surface |
| `scripts/kb/**` + `tests/kb/**` | Automation implementation and verification | Controlled write surface |

## Core workflow

1. Ingest source content from `raw/inbox/**`.
2. Generate/update wiki pages (`wiki/sources/**`, `wiki/entities/**`, `wiki/concepts/**`).
3. Rebuild deterministic index (`wiki/index.md`).
4. Append `wiki/log.md` only when a real state change occurred.
5. Move successfully ingested inputs to `raw/processed/**`.
6. Enforce strict lint and test gates before write-capable automation proceeds.

## Automation model (CI-1..CI-3)

| CI | Responsibility | Write capability |
|---|---|---|
| **CI-1** | Trusted-trigger gatekeeper/handoff | No |
| **CI-2** | Read-only diagnostics and analysis | No |
| **CI-3** | PR-producing write path with allowlists and preflight | Yes (allowlisted paths only) |

This split is intentional: it isolates trust checks, diagnostics, and write operations
so permission scope can stay minimal for each path.

## Wiki-curation framework MVP boundary

The wiki-curation agent framework is an **MVP control plane** over the existing
knowledgebase tooling, not a replacement runtime. The accepted layering and
packaging rule live in
[`ADR-007`](decisions/ADR-007-control-plane-layering-and-packaging.md).

| Layer | Package location | MVP role now |
|---|---|---|
| Global policy and trust boundaries | `AGENTS.md` + ADRs | Keep fail-closed, provenance, append-only log, and write-scope rules always on. |
| Agent personas | `.github/agents/**` | Define router/worker missions, handoffs, and stop conditions. |
| Skill workflows and thin wrappers | `.github/skills/**` | Hold procedural workflow docs plus narrow wrappers that invoke deterministic tooling. |
| Deterministic execution surface | `scripts/kb/**` | Remains the authoritative Python implementation for ingest, index, lint, qmd preflight, and query persistence. |
| Verification surface | `tests/kb/**` | Validates the deterministic execution layer and any framework references to it. |

### In scope for the framework MVP

- Agent and skill scaffolding under `.github/agents/**` and `.github/skills/**`.
- Thin wrapper surfaces that call existing `scripts/kb/ingest.py`,
  `scripts/kb/update_index.py`, `scripts/kb/lint_wiki.py`,
  `scripts/kb/qmd_preflight.py`, and `scripts/kb/persist_query.py`.
- Architecture, ADR, and operator documentation that explains the boundary and
  where future extensions belong.

### Deferred beyond the framework MVP

- Porting the broader cross-repository script backlog into new `scripts/**`
  trees for validation, reporting, context sync, or maintenance.
- Replacing the current `scripts/kb/**` entrypoints with agent-native logic.
- Adding heavy repository crawlers, external-service integrations, or batch
  reporting pipelines before the scaffolding and wrapper layer is in place.

## Operator lane sequencing

The implemented control plane is intentionally lane-first. Operators should treat
the following order as mandatory:

| Phase | Required order | Operator rule |
|---|---|---|
| Entry + ingest-safe gate | `knowledgebase-orchestrator` → `source-intake-steward` → `evidence-verifier` → `policy-arbiter` | No downstream wiki/content/topology lane opens before this sequence succeeds. |
| Policy-cleared drafting | `synthesis-curator` | Drafting is limited to the cleared scope and returns to `evidence-verifier` + `policy-arbiter` before durable publication. |
| Policy-cleared query/discovery | `query-synthesist` or `topology-librarian` | Query answers read the curated wiki first; durable follow-up stays on governed persistence or index-sync paths. |
| Maintenance/quality follow-up | `maintenance-auditor`, `change-patrol`, `quality-analyst` | These personas triage, audit, and recommend; any content-changing follow-up routes back through `knowledgebase-orchestrator`. |
| Human escalation | Human Steward | Required when contradictions, deletions, identity ambiguity, or policy conflicts remain unresolved. |

This sequencing is the maintainers' operative interpretation of the framework
now landed in `.github/agents/**`. It keeps governance ahead of synthesis and
prevents ADR-007 drift into a second runtime.

## Persona roster under `.github/agents/`

| Group | Persona | Current role |
|---|---|---|
| Entry gate | `knowledgebase-orchestrator` | Classifies work, enforces boundary rules, and selects the safe lane. |
| Ingest-safe gate | `source-intake-steward` | Guards `raw/inbox/**`, provenance, and immutable intake packaging. |
| Ingest-safe gate | `evidence-verifier` | Requires deterministic provenance/evidence completeness before policy review. |
| Ingest-safe gate | `policy-arbiter` | Applies repository governance and blocks downstream work until cleared. |
| Downstream governed lane | `synthesis-curator` | Produces policy-cleared draft/update packages without direct publication. |
| Downstream governed lane | `query-synthesist` | Answers from curated wiki first and routes durable results back through governed persistence. |
| Downstream governed lane | `topology-librarian` | Applies taxonomy/index follow-up inside the cleared scope only. |
| Review/maintenance lane | `maintenance-auditor` | Audits stale/orphaned/semantic maintenance risk without inventing new automation. |
| Review/maintenance lane | `change-patrol` | Routes changed-source/content risk back through the correct existing lane. |
| Review/maintenance lane | `quality-analyst` | Turns existing repo evidence into prioritized quality/discoverability follow-up. |
| Review support | `code-reviewer` | General review persona for correctness/readability/architecture/security/performance checks. |
| Review support | `test-engineer` | Test-strategy and coverage specialist for framework or tooling changes. |
| Review support | `security-auditor` | Security-focused review persona for hardening and threat analysis. |

## Skill layer under `.github/skills/`

| Skill slice | Status in MVP | Repo-local examples |
|---|---|---|
| Governance + wrappers | Active | `validate-wiki-governance`, `sync-knowledgebase-state`, `review-wiki-plan` |
| Knowledge-structure contracts | Active, doc-only | `information-architecture-and-taxonomy`, `ontology-and-entity-modeling`, `knowledge-schema-and-metadata-governance` |
| Deferred scaffolding | Present but recommendation-only | `entity-resolution-and-canonicalization`, `search-and-discovery-optimization` |

The skill layer carries workflow procedure and thin wrapper logic while leaving
deterministic execution in `scripts/kb/**`. No framework skill should add a new
repo-level `scripts/validation/*`, `scripts/reporting/*`, `scripts/context/*`,
or `scripts/maintenance/*` tree in MVP.

## Framework verification entrypoints

Operators can validate the landed framework with these repo-local entrypoints:

| Check | Command | Primary evidence |
|---|---|---|
| Fixed governance gate | `python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py` | Wrapper over `scripts/kb/qmd_preflight.py`, `scripts/kb/update_index.py`, and `scripts/kb/lint_wiki.py` |
| Read-only state-sync precheck | `python3 .github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py --check-only` | Confirms the allowlisted index/lint path before write mode |
| Write-capable index sync | `python3 .github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py --write-index` | Refreshes `wiki/index.md` only after prechecks pass |
| Focused framework suite | `python3 -m unittest tests.kb.test_framework_contracts tests.kb.test_framework_skills tests.kb.test_framework_agents tests.kb.test_framework_references tests.kb.test_skill_wrappers` | `tests/kb/test_framework_contracts.py`, `test_framework_skills.py`, `test_framework_agents.py`, `test_framework_references.py`, `test_skill_wrappers.py` |
| Full repository suite | `python3 -m unittest discover -s tests -p "test_*.py"` | End-to-end regression safety beyond framework-specific checks |

## Write and safety controls

- Canonical write allowlist for automation: `wiki/**`, `wiki/index.md`, `wiki/log.md`, `raw/processed/**`.
- Raw immutability: `raw/processed/**` must not be mutated after ingest.
- Ingest-time SourceRefs may use provisional placeholder git SHAs; only reconciled commit-bound SourceRefs whose `git_sha` resolves to a real revision containing the cited artifact bytes count as authoritative provenance.
- Concurrency guard: workflow-level concurrency group plus local lock file (`wiki/.kb_write.lock`).
- Fail-closed behavior: missing prerequisites, permission mismatches, or lock contention stop writes.
- Policy-gated query persistence: write only when `auto_persist_when_high_value` criteria pass.

## Decision records

Key architecture decisions are captured in ADRs:

- [`ADR-001`](decisions/ADR-001-persistent-wiki-architecture.md): persistent repository-scoped wiki model
- [`ADR-002`](decisions/ADR-002-frontmatter-and-sourceref-contract.md): required frontmatter and SourceRef provenance
- [`ADR-003`](decisions/ADR-003-policy-gated-query-persistence.md): deterministic query-persist policy and envelopes
- [`ADR-004`](decisions/ADR-004-split-ci-workflow-governance.md): split CI governance and permission profiles
- [`ADR-005`](decisions/ADR-005-write-concurrency-guards.md): workflow + local lock concurrency model
- [`ADR-006`](decisions/ADR-006-authoritative-source-boundary.md): repository-local authoritative source boundary
- [`ADR-007`](decisions/ADR-007-control-plane-layering-and-packaging.md): framework control-plane layering and packaging rule
