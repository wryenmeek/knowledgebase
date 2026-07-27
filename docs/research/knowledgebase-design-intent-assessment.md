# Knowledgebase Design-Intent Assessment

**Assessment date:** 2026-07-27
**Repository revision:** `f4d46dc65e5da156bc6087ce5ab1a61508fefdd9` on `main`
**Worktree state at capture:** Dirty; the assessment plan under `docs/plans/` was untracked.
**Evidence state:** Static-verified. This assessment establishes checked-in design, implementation, tests, and workflow wiring. It does not establish local execution, successful CI runs, deployed service availability, or production operation.

## Executive assessment

Knowledgebase is intended to be a production-usable, repository-scoped knowledgebase where humans curate sources, agents perform governed maintenance, knowledge persists as auditable Markdown, and every write is provenance-bound and fail-closed. The current instance is Medicare-focused: `mkdocs.yml` names it "Medicare Coverage Tools - Knowledgebase" and the maintained style guide defines Medicare coverage vocabulary and CMS-first sourcing. It achieves the general intent well at the deterministic governance layer: the source boundary, controlled artifacts, executable ingest/index/lint/query-persistence surfaces, lock model, and verification architecture are concrete and mutually reinforcing.

It achieves the intent partially as an operating knowledge service. Several system capabilities are configured or implemented but not composed into their planned automated workflow, and the checked-in wiki is largely a framework corpus rather than a substantive Medicare coverage corpus. The distinction matters: this is a Medicare-focused deployment of a reusable knowledgebase framework, but it is not yet evidence of a mature Medicare coverage knowledge product.

## Intended operating model

The normative specification defines four outcomes: human-curated source inputs, agent-assisted ingest/query/lint maintenance, persistent Markdown knowledge, and auditability through Git history plus `wiki/log.md` (`raw/processed/SPEC.md`, Objective). The architecture turns those outcomes into a controlled workflow:

1. Untrusted material enters `raw/inbox/**`.
2. Governed ingest produces or updates source, entity, and concept pages.
3. Deterministic indexing and strict linting validate the curated corpus.
4. State-changing writes use declared allowlists, locks, and append-only audit logging.
5. Agent and skill layers route work while `scripts/kb/**` remains the authoritative deterministic runtime.

This is intentionally a governance-first design. The architecture separates read-only diagnostics from limited write paths, retains immutable processed source artifacts, and treats the agent framework as a control plane rather than a replacement runtime (`docs/architecture.md`, Core workflow; Automation model; Wiki-curation framework MVP boundary).

The framework is still domain-neutral by design. `TEMPLATE.md` identifies the repository as a GitHub Template Repository, requires users to replace the content layer with their own domain, and labels the scripts, tests, schemas, and agent infrastructure reusable across any domain. The current repository is therefore not a Medicare-only framework; it is a Medicare-branded instance with reusable infrastructure.

## Capability assessment

| Intended capability | Evidence | State | Assessment |
|---|---|---|---|
| Provenance-safe ingest and durable knowledge artifacts | `raw/processed/SPEC.md` command and interface contracts; `scripts/kb/ingest.py`; `tests/kb/test_ingest.py` | Static-verified | Strong. The design has a specific untrusted-to-governed path, state-change semantics, and testable failure behavior. |
| Deterministic cataloging and integrity validation | `scripts/kb/update_index.py`; `scripts/kb/lint_wiki.py`; `tests/kb/` | Static-verified | Strong. The index is generated from curated content and strict lint is read-only, deterministic, and bounded to the wiki surface. |
| Policy-gated durable query output | `scripts/kb/persist_query.py`; `raw/processed/SPEC.md` query-persist contract | Static-verified | Strong. Persistence requires confidence, sufficient sources, and no unresolved contradiction rather than treating every query as publishable knowledge. |
| Controlled automation | `.github/workflows/ci-1-trusted-trigger.yml`, `.github/workflows/ci-2-analyst-diagnostics.yml`, `.github/workflows/ci-3-pr-producer.yml`; `tests/kb/test_ci1_workflow.py`, `tests/kb/test_ci2_workflow.py`, `tests/kb/test_ci3_workflow.py`; declared write-surface matrix in `AGENTS.md` | Static-verified | Strong checked-in wiring and contract-test evidence. Actual workflow execution and credential availability are unassessed. |
| Governed agent control plane | `.github/agents/knowledgebase-orchestrator.md`; `.github/agents/query-synthesist.md`; `tests/kb/test_framework_agents.py`; `docs/architecture.md` operator lane sequencing | Static-verified | Strong checked-in boundary evidence. The framework directs work through policy gates and preserves the Python runtime as the execution authority. |
| Local and browser-facing discovery | `docs/user-guide.md`; `wiki/search.md`; `docs/mvp-runbook.md` semantic API contract | Static-verified | Partial. Local qmd search and Pagefind are documented; the semantic browser lane is only an optional client contract with no repository-owned endpoint. |
| Resumable processing visibility | `scripts/kb/checkpoint_registry.py`; `tests/kb/test_checkpoint_registry.py`; `.github/workflows/ci-3-pr-producer.yml` | Static-verified | Partially wired. The registry runtime and CI-3 verification report exist, but per-batch mutation input wiring remains deferred. |

## Gap analysis

| Priority | Gap state | Gap | Why it matters | Evidence |
|---|---|---|---|---|
| High | Deferred | CI-3 does not create the fully formed mutation input needed to update the checkpoint registry for each processing batch. | The registry can verify and report state but cannot represent the normal automated batch lifecycle end-to-end. | `docs/ideas/wiki-processing-checkpoint-registry.md` marks CI-3 `--mutate` wiring deferred to issue #377; CI-3 invokes `checkpoint_registry.py --verify --warn-only`. |
| High | Deferred | The 30-day revisit for the Jules-only fleet's lack of multi-provider fallback passed on 2026-07-21. | An outage can still block automated implementation dispatch; visibility improvements reduce detection time but do not supply continuity. | `docs/decisions/ADR-035-tier-3-multi-provider-fallback-deferral.md`, Decision and Consequences. |
| Medium | Partially wired | The workspace-audit skill has classifier modules, schema, and tests, but its `improve` orchestrator does not compose classifier output. | The intended self-audit capability cannot independently produce the findings its remediation workflow needs. | `.github/skills/audit-knowledgebase-workspace/SKILL.md`, Overview, Phase 4 components, and Contract. |
| Medium | Operationally undecided | The semantic search page accepts a maintainer-provided endpoint and falls back to Pagefind; no repository-owned service, deployment, or operator ownership is defined. | The user interface advertises an optional semantic lane, but its availability is external to this repository. The endpoint is stored in browser localStorage, so repository-bound agents cannot discover or use an individual user's configured endpoint; they correctly fall back to the curated wiki. | `wiki/search.md`; `docs/user-guide.md`, Optional semantic API results; `docs/mvp-runbook.md`, Wiki search semantic API contract; `.github/agents/query-synthesist.md`. |
| Medium | Content-adoption gap | The generated index contains framework and governance material, while `wiki/analyses/` is empty and no Medicare coverage corpus is evident in the catalog. | The tooling can govern a domain corpus, but the present content does not yet demonstrate the stated Medicare-oriented product value. | `wiki/index.md`, Sources, Entities, Concepts, and Analyses sections. |
| Low | Deferred | Pytest is the declared direction, but 58 unittest-style test files remain under the ratchet baseline. | The ratchet prevents further regression but retains two testing idioms and a finite migration burden. | `docs/ideas/test-framework-pytest-migration.md`. |

## How well the design intent is achieved

**Governance, provenance, and deterministic execution: strong.** The repository expresses its guarantees in multiple independent layers: normative contracts, canonical utility modules, bounded write surfaces, lock discipline, tests, and CI role separation. That redundancy is appropriate for a system whose distinguishing promise is that LLM-assisted curation cannot silently publish untraceable or unsafe changes.

**Knowledge accumulation and retrieval: partial.** The system has durable artifact structures, local qmd retrieval, deterministic indexing, Pagefind, and a policy gate for preserving high-value query output. The available catalog, however, primarily documents the framework itself. The empty analyses section and absence of evident Medicare coverage pages mean the repository has not yet demonstrated sustained domain knowledge accumulation.

**Autonomous operations and resilience: partial.** The automation architecture is carefully designed, but several capabilities stop at static wiring or a defined handoff. Checkpoint mutation is not integrated into CI-3, the workspace audit cannot compose its classifiers, semantic service ownership is outside the repository, and fleet continuity depends on a single provider after the documented deferral date.

## Recommended sequence

1. **Make the content layer prove the product value.** Ingest authoritative Medicare coverage sources through the existing governed lane and publish evidence-backed source, concept, entity, and analysis artifacts.
2. **Finish the processing feedback loop.** Define and test a CI-3 mutation-input adapter, then wire checkpoint `--mutate` under the existing lock and policy contracts.
3. **Choose ownership for optional services.** Either define a supported semantic-endpoint deployment and operations model or clearly position the browser field as an external integration point.
4. **Revisit fleet resilience now.** Record an explicit post-2026-07-21 decision: adopt a bounded fallback, renew the deferral with current evidence, or document a tested manual failover procedure.
5. **Compose the existing audit components.** Wire classifier output into the workspace-audit orchestrator so its improvement workflow can produce the evidence it already knows how to validate.
6. **Reduce the test-framework backlog opportunistically.** Preserve the ratchet and migrate legacy unittest files as they are meaningfully touched.

## Limits

This assessment does not claim that any GitHub Action has executed successfully, that secrets or external services are configured, or that the published site is currently reachable. Those are different evidence states and require run logs, environment inspection, or production monitoring. It also does not treat documented future work as a defect unless the repository's stated intent depends on it today.

## Domain-identity evidence

- `mkdocs.yml` identifies the published site as the Medicare Coverage Tools knowledgebase.
- `.github/skills/references/manual-of-style.md` treats Medicare coverage as the expected prose domain and requires CMS-first authoritative sourcing.
- `TEMPLATE.md` and `raw/processed/cloneable-template.md` establish that the implementation is reusable across domains and that the content layer must be replaced for a new instance.
