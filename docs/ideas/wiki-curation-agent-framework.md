# Wiki curation agent framework

## Executive Summary

This repository should model wiki curation as a **small control plane plus specialized worker agents**, not as one monolithic "wiki maintainer" prompt.[^1][^3] The control plane belongs in `AGENTS.md` and should hold only stable guardrails such as write boundaries, provenance rules, append-only logging, and schema compliance, while deterministic operational work should move into on-demand skills so the system stays inside the instruction budget described in the research.[^3][^4][^8] For this knowledgebase, the minimum viable roster is: **Knowledgebase Orchestrator, Source Intake Steward, Evidence Verifier, Policy Arbiter, Synthesis Curator, Query Synthesist, Topology Librarian, Maintenance Auditor, Change Patrol, and Quality Analyst**, with a **Human Steward** retained as the escalation point for contradictions, deletions, and policy arbitration.[^7][^9][^10][^11][^13]

The main update I would make to this framework is at the **skill layer, not the role layer**: knowledge-structure decisions should no longer remain implicit inside synthesis or topology work. The framework should add first-class skills for **information architecture and taxonomy governance**, **ontology and entity modeling**, and **knowledge-schema and metadata governance**, with **entity resolution and canonicalization** plus **search and discovery optimization** as secondary follow-on skills.[^2][^5][^6][^13][^21]

The dependency order should be **intake -> verification -> policy -> synthesis/query/topology -> maintenance -> analytics**, because the wiki only becomes safe to scale once raw materials are immutable, claims are verified, and policy gates clear before any downstream drafting or topology work proceeds.[^2][^4][^5][^10][^14] No durable save, topology mutation, or publication path should open before that governance sequence succeeds, and any content-changing follow-up from audit/review roles should route back through the orchestrator rather than writing directly.[^4][^7][^10][^14] That sequencing also matches the repository's planning guidance: build foundations first, keep tasks vertically sliced, and make each stage leave the system in a valid state.[^20]

This document should be read in two layers:

1. **Current state** — what the MVP control plane has already landed in this repository.
2. **Target framework** — the workflow decomposition, skill map, and adaptation backlog that describe how the framework should expand within the accepted implementation boundary.

Unless a subsection explicitly says otherwise, the authoritative description of
**what is implemented today** lives in `docs/architecture.md`,
`docs/decisions/ADR-007-control-plane-layering-and-packaging.md`, and the
landed contracts under `.github/agents/**` and `.github/skills/**`. The role
maps, skill labels, and backlog notes below should therefore be read as
target-state design guidance first and current-runtime guarantees only where
the MVP sections say they are already landed.

## Ratified MVP implementation boundary

This framework should now be implemented as a **scaffolding-first MVP**. The
goal of the MVP is to make the control plane concrete without replacing the
repository's existing deterministic Python execution surface.

### Current implementation status snapshot

The current repo state is:

| Layer | Current status |
|---|---|
| Personas | Landed as `.github/agents/**` contracts with mission, handoff, and fail-closed sections. |
| Framework wrappers | Landed only for `validate-wiki-governance` and `sync-knowledgebase-state`. |
| Knowledge-structure skills | Landed as active **doc-only** contract skills: `information-architecture-and-taxonomy`, `ontology-and-entity-modeling`, `knowledge-schema-and-metadata-governance`, `entity-resolution-and-canonicalization`, and `search-and-discovery-optimization`. |
| Policy/evidence/self-audit skills | Landed as active **doc-only** workflow skills: `validate-inbox-source`, `verify-citations`, `enforce-npov`, `record-open-questions`, `log-policy-conflict`, `review-wiki-plan`, and `audit-knowledgebase-workspace`. |
| Deterministic execution | Still centered on `scripts/kb/ingest.py`, `scripts/kb/update_index.py`, `scripts/kb/lint_wiki.py`, `scripts/kb/qmd_preflight.py`, and `scripts/kb/persist_query.py`. |
| Verification | Enforced through `tests/kb/**`, especially the focused framework suites and wrapper runtime checks. |

### In scope now

| MVP slice | What lands in this repository |
|---|---|
| Agent scaffolding | Persona files under `.github/agents/` with mission, handoff, and stop-condition contracts. |
| Skill scaffolding | Skill directories under `.github/skills/` with discovery metadata, procedural `SKILL.md` files, references, and narrow wrapper logic where needed. |
| Thin wrapper integration | Wrapper entrypoints currently landed for governance validation and index/state synchronization; ingest and query persistence still run through direct `scripts/kb/**` entrypoints rather than framework-local wrappers. |
| Boundary documentation | Architecture and ADR updates that state where policy, personas, skills, wrappers, scripts, and tests belong. |

### Deferred follow-on work

- Porting the broader script-adaptation backlog into new `scripts/validation/`,
  `scripts/reporting/`, `scripts/context/`, `scripts/maintenance/`, or
  `scripts/ingest/` trees.
- Replacing or bypassing `scripts/kb/**` with agent-local implementations.
- Mixing heavy repository crawlers, batch reporting, baseline snapshots, or
  external-service integrations into the initial scaffolding milestone.

### Approved post-MVP package surfaces

The repository boundary is now widened for future work in:

- `scripts/validation/**`
- `scripts/reporting/**`
- `scripts/context/**`
- `scripts/maintenance/**`
- `scripts/ingest/**`

That approval is about **where future code may live**, not a claim that those
paths are already implemented or that automation may write there without a
narrower contract. Current runtime guarantees still come from
`docs/architecture.md`, ADR-007, ADR-004, ADR-005, and ADR-006.

### Where the packaging rule now lives

- [`docs/architecture.md`](../architecture.md#wiki-curation-framework-mvp-boundary)
  summarizes the implementation boundary.
- [`docs/decisions/ADR-007-control-plane-layering-and-packaging.md`](../decisions/ADR-007-control-plane-layering-and-packaging.md)
  records the accepted control-plane layering and packaging rule.

## Recommended control-plane model

The research separates the autonomous wiki into three layers: immutable raw sources, synthesized wiki pages, and schema/configuration that disciplines agent behavior.[^2] This repository already expresses the same shape operationally through `raw/inbox/`, `raw/processed/`, `raw/assets/`, `wiki/`, and `schema/`, with explicit guardrails to fail closed, restrict writes, preserve append-only logging, require canonical SourceRef citations, and keep page frontmatter aligned with the page template.[^4][^5]

The right implementation pattern is therefore:

| Layer | What lives here | Why it stays here |
|---|---|---|
| **Global policy** | Root `AGENTS.md` plus narrow nested overrides | Keeps durable rules short, imperative, and always-on.[^3][^4] |
| **Workflow logic** | `.github/skills/*` skill directories | Encodes ingest, verification, maintenance, and formatting as repeatable procedures loaded only when needed.[^8][^15][^16] |
| **Role personas** | `.github/agents/*` agent definitions | Keeps each agent focused on mission, review lens, and output contract instead of embedding every procedure in the persona itself.[^17][^18][^19] |
| **Human authority** | Steward / curator approvals | Preserves human control over contradiction resolution, archival decisions, and exceptional policy calls.[^7] |

This split is the key architectural choice for the framework: **personas stay concise; skills carry the jobs; scripts and references provide deterministic checks**.[^8][^14]

## Architecture overview

```text
                         ┌───────────────────────┐
                         │     Human Steward     │
                         │ contradictions/archive│
                         └──────────┬────────────┘
                                    │
                           escalation/approval
                                    │
┌───────────────────────┐   routes   ▼   invokes   ┌───────────────────────┐
│  Knowledgebase        │──────────────────────────▶│  Shared wiki skills    │
│  Orchestrator         │                           │  + validators/scripts  │
└───────┬───────────────┘                           └───────────────────────┘
        │
        ├────────▶ Source Intake Steward ───────▶ Evidence Verifier ───────▶ Policy Arbiter
        │                                                                     │
        │                                                                     ├────────▶ Synthesis Curator
        │                                                                     │                │
        │                                                                     │                └──▶ Evidence Verifier ─▶ Policy Arbiter ─▶ Topology Librarian
        │                                                                     │
        │                                                                     ├────────▶ Query Synthesist
        │                                                                     │                │
        │                                                                     │                └──▶ Knowledgebase Orchestrator for any durable follow-up
        │                                                                     │
        │                                                                     └────────▶ Topology Librarian
        │
        └────────▶ Maintenance Auditor ────────▶ Change Patrol ───────────▶ Quality Analyst
                                 │                       │                         │
                                 └───────────────────────┴─────────────────────────┴──▶ Knowledgebase Orchestrator for content-changing follow-up
```

The orchestrator should choose the path, but every worker should still be bounded by the same repository-wide constraints: no writes outside allowlisted paths, no mutation of raw sources, append-only log behavior, and page outputs that match the frontmatter template.[^4][^5]

## Knowledge-structure layer now explicit in the framework

The previous version of this framework correctly identified roles for synthesis, topology, maintenance, and analytics, but it still treated several core design disciplines as side effects of those roles rather than as reusable expertise.[^2][^5][^6] The framework now makes that dependency explicit at the contract layer through a **knowledge-structure layer** of skills that sits underneath Synthesis Curator, Topology Librarian, and Quality Analyst:

1. **`information-architecture-and-taxonomy`** — owns namespace boundaries, browse paths, tag families, category specificity rules, and structural refactors that affect findability and discoverability.[^2][^6]
2. **`ontology-and-entity-modeling`** — defines canonical entity types, relation vocabulary, merge/split criteria, alias strategy, and what kinds of concepts deserve distinct pages versus linked subsections.[^5][^6][^7]
3. **`knowledge-schema-and-metadata-governance`** — owns the frontmatter contract, allowed field semantics, schema evolution, migration rules, and the difference between advisory and blocking validation failures for knowledge artifacts.[^4][^5][^21]
4. **`entity-resolution-and-canonicalization`** — in post-MVP phases, handles duplicate detection, synonym mapping, canonical naming, redirects, and conflict-safe merge proposals once the corpus grows. In today's MVP, it remains read-only assessment scaffolding that recommends keep/merge/split/escalate outcomes rather than automating rewrites.[^6][^7]
5. **`search-and-discovery-optimization`** — in post-MVP phases, closes the loop between topology and KPI signals by using missed queries, search success, and navigation weak spots to reshape titles, tags, indexes, and related-page paths. In today's MVP, it remains a recommendation-only discovery lens rather than a telemetry or KPI runtime.[^13]

In the current repo, this layer is partly landed: taxonomy, ontology, and metadata governance are active doc-only skills, while entity resolution and search/discovery optimization remain deferred scaffolding.[^2][^5][^6]

## Implemented persona roster and target job/skill map

The personas named below are **landed as contract files under `.github/agents/**`**. Their job lists and named skills should be read as the intended workflow decomposition for the framework, not as proof that every listed skill already exists as executable automation in this repository.

When a live persona contract is intentionally narrower than the long-term
design, the current MVP contract takes precedence over the aspirational job
list here.

### 1. Knowledgebase Orchestrator

The orchestrator is the router and safety gate for all wiki work.[^3][^15] Its jobs are to classify requests into **ingest**, **query**, **maintenance**, or **review** lanes, enforce write scope before any other agent runs, select the correct worker sequence, and stop the run on validation or policy failures instead of letting a downstream agent improvise.[^4][^8][^14]

**Jobs**

1. Classify the incoming task.
2. Select the workflow and worker order.
3. Enforce repository boundaries and idempotency.
4. Aggregate outcomes and escalate when needed.[^4][^7][^20]

**Skills**

- `route-wiki-task`
- `enforce-repository-boundaries`
- `plan-wiki-job`
- `fail-closed-on-errors`
- `append-log-entry`[^4][^14][^20]

### 2. Source Intake Steward

This agent owns the trust boundary between untrusted inputs and curated work.[^2][^4] It should validate new material in `raw/inbox/`, normalize metadata, move approved artifacts into immutable storage (`raw/processed/` or `raw/assets/`), and emit a structured intake manifest that later agents can consume without reinterpreting the source every time.[^2][^4]

**Jobs**

1. Validate source type and placement.
2. Compute provenance metadata and checksums.
3. Normalize or register the artifact without altering source content.
4. Record the ingest event for auditability.[^2][^4]

**Skills**

- `validate-inbox-source`
- `register-source-provenance`
- `checksum-asset`
- `create-intake-manifest`
- `log-ingest-event`[^4]

### 3. Synthesis Curator

This agent turns source material into wiki pages and updates, which is the core "LLM-edited wiki" behavior described in the research.[^1][^9] It should extract entities, concepts, claims, and chronology; decide whether each target is a create or update; and draft pages that already conform to the repository's frontmatter template, source array, confidence field, open questions, and status lifecycle.[^5][^6][^9] Critically, it should do that work against an explicit ontology and metadata contract rather than inventing page identity or schema interpretation ad hoc during each ingest pass.[^5][^6]

**Jobs**

1. Extract entities, concepts, claims, and temporal context.
2. Match existing pages or create new ones.
3. Apply the canonical entity and relationship model before deciding page identity.
4. Draft page content with SourceRef-backed evidence.
5. Populate frontmatter and open questions.
6. Hand off drafts for verification before they are considered complete.[^5][^6][^9]

**Skills**

- `extract-entities-and-claims`
- `ontology-and-entity-modeling`
- `synthesize-entity-page`
- `synthesize-concept-page`
- `knowledge-schema-and-metadata-governance`
- `enforce-page-template`
- `write-sourceref-citations`
- `entity-resolution-and-canonicalization`
- `record-open-questions`[^5][^6][^9]

### 4. Query Synthesist

The research treats query answering as a distinct workflow that should read the wiki first, answer with citations, and optionally prepare high-value analyses for governed persistence so the repository compounds over time without bypassing its control plane.[^1][^9] That makes query synthesis a separate role from page drafting: it is optimized for retrieval, comparison, and reusable synthesis rather than raw-source intake.[^9]

**Jobs**

1. Consult the index and relevant wiki pages.
2. Synthesize an answer with inline citations.
3. Decide whether the answer merits governed durable follow-up.
4. Route any durable candidate back through `knowledgebase-orchestrator`, verification, and policy review before a write-capable publication path opens.[^9]

**Skills**

- `retrieve-from-index`
- `synthesize-cited-answer`
- `prepare-high-value-synthesis-handoff`
- `handoff-query-derived-page`[^9]

### 5. Evidence Verifier

In the target end state, this agent becomes the hard quality gate between
drafting and publication.[^10] The research is explicit that a wiki becomes
unsafe without a programmatic fact-checking and citation-verification pipeline,
and recommends a workflow that inventories claims, traces each one back to
sources, looks for hallucination tells, and runs deterministic validators until
the document passes.[^10]

In today's MVP, however, the landed contract is intentionally narrower: the
verifier remains intake-evidence-focused, checking provenance completeness,
checksum evidence, SourceRef prerequisites, and readiness for policy review
before any downstream drafting lane opens. Post-draft claim inventories,
citation re-checks, and hallucination-style review are still target-state
follow-on work rather than current runtime guarantees.

**Jobs**

1. In today's MVP, validate intake provenance, checksum evidence, and SourceRef prerequisites before policy review.
2. Reject incomplete, provisional-only, or non-authoritative packages that cannot proceed deterministically.
3. Hand verified intake packages to `Policy Arbiter` and fail closed when evidence remains unresolved.
4. In a later phase, parse draft source inventories, extract factual claims, and cross-check them against cited sources before durable publication.[^10]
5. In a later phase, run deterministic citation/link validators and return drafts that fail evidence checks.[^10]

**Skills**

`verify-citations` is now a landed doc-only workflow for SourceRef and
provenance-readiness review in the current MVP. The remaining labels below
describe the **target expanded verification lane** beyond that landed surface:

- `verify-citations`
- `claim-inventory`
- `semi-formal-reasoning`
- `detect-ai-tells`
- `run-deterministic-validators`[^10][^14]

### 6. Policy Arbiter

This agent enforces the editorial constitution: neutral point of view, no original research, and contradiction handling.[^7] It should review whether claims are attributed with due weight, whether the draft introduces synthesis that cannot be grounded in the source layer, and whether conflicting evidence must trigger an explicit human arbitration path rather than silent overwrite behavior.[^7]

**Jobs**

1. Check due weight and attribution.
2. Detect unsupported inference or original research.
3. Identify contradictions against existing high-confidence pages.
4. Write open questions and escalation records instead of forcing a merge.[^7]

**Skills**

In today's MVP, `enforce-npov` and `log-policy-conflict` are landed doc-only
workflow skills. The other labels below remain target-state follow-on slices.

- `enforce-npov`
- `detect-original-research`
- `compare-against-existing-pages`
- `escalate-contradictions`
- `log-policy-conflict`[^7]

### 7. Topology Librarian

This agent owns findability and discoverability, which the research treats as
foundational to a functioning wiki rather than optional polish.[^2] In the
target end state, it can coordinate index, backlink, alias, and taxonomy
follow-up so the graph stays explorable instead of collapsing into broad
buckets.[^2][^6][^9]

In today's MVP, its scope is narrower: it recommends topology changes within
existing contracts, hands deterministic index refreshes to
`sync-knowledgebase-state`, and escalates identity-sensitive alias/redirect
pressure instead of inventing a second discovery runtime. Redirect-style
automation, bulk alias rewrites, and broad discovery pipelines remain deferred.

**Jobs**

1. Recommend index or catalog follow-up and route approved refreshes through deterministic wrappers.
2. Recommend cross-link and backlink follow-up within the cleared scope and existing contracts.
3. Escalate alias or redirect pressure when canonical identity, durable anchors, or new runtime behavior would be required.
4. Apply category, namespace, and browse-path rules from the explicit IA/taxonomy model.
5. Validate category placement and tag specificity while deferring unsupported automation.[^2][^6]

**Skills**

The landed dependencies here are `sync-knowledgebase-state` plus the active
doc-only knowledge/discovery skills. The remaining labels below are best read as
target-state workflow slices rather than current direct-runtime capabilities:

- `information-architecture-and-taxonomy`
- `update-index`
- `suggest-backlinks`
- `manage-redirects-and-anchors`
- `validate-taxonomy-placement`
- `search-and-discovery-optimization`
- `check-link-topology`[^2][^6][^9]

### 8. Maintenance Auditor

The research treats linting as a semantic maintenance pipeline, not a formatting nicety.[^11] This agent should sweep for orphan pages, stale operational content, broken cross-reference symmetry, and status drift, then surface governed maintenance follow-up packages that preserve history and send any content-changing remediation back through the control plane.[^11]

**Jobs**

1. Detect orphan pages and weak discoverability.
2. Sweep for freshness and review-cadence violations.
3. Check contradiction symmetry across related pages.
4. Propose supersede/archive actions within policy bounds.[^11]

**Skills**

- `semantic-wiki-lint`
- `freshness-audit`
- `cross-reference-symmetry-check`
- `propose-supersede-or-archive`
- `append-maintenance-log`[^11]

### 9. Change Patrol

This agent exists for environments where humans can edit the wiki directly and those edits must be screened quickly against policy and structural rules.[^11] It should review diffs, detect citation removal, style violations, or namespace breaches, and route destructive or policy-relevant follow-up back through the control plane rather than reverting content directly.[^11]

**Jobs**

1. Review incoming human edits.
2. Compare edits against policy and style constraints.
3. Return destructive or non-compliant changes to governed review for explicit disposition.
4. Log warnings and raise incidents for review.[^11]

**Skills**

- `patrol-human-edits`
- `policy-diff-review`
- `route-noncompliant-edit-for-review`
- `log-patrol-incident`[^11]

### 10. Quality Analyst

This agent turns the wiki from a corpus into an observable system over
time.[^13] In the target end state, it can score pages for maturity and
confidence, calculate search and freshness metrics, and surface structural gaps
such as missed queries or high-demand but low-quality documents so the rest of
the agent fleet can prioritize work intelligently.[^13]

In today's MVP, however, the landed contract is recommendation-first: it uses
existing repository evidence to assess discoverability, coverage, and quality
cues, then feeds governed prioritization back into the orchestrator. New
telemetry, KPI pipelines, daemons, crawlers, or external reporting surfaces are
deferred by ADR-007.

**Jobs**

1. Assess page maturity and trust signals using existing repo evidence.
2. Recommend freshness or discoverability follow-up only when the signal can be grounded in existing deterministic artifacts.
3. Identify high-value pages or gaps that need deeper governed curation.
4. Feed prioritized recommendations back to the orchestrator rather than updating scores directly.[^13]

**Skills**

The labels below are target-state workflow names, not current MVP runtime
guarantees:

- `score-page-quality`
- `compute-kpis`
- `analyze-missed-queries`
- `prioritize-curation-backlog`[^13]

### Human Steward (non-agent, required)

The framework still needs a human steward because the research explicitly keeps strategic adjudication of truth, contradiction resolution, and high-risk archival decisions in human hands.[^7] The automation goal is to remove clerical work, not to eliminate accountability for disputed knowledge.[^7][^21]

## End-to-end workflows

The workflows below are the **target governed operating model** for the
framework. Today, the lane order and persona contracts are landed, while
execution still relies heavily on direct `scripts/kb/**` entrypoints plus the
two thin wrapper skills for governance and index synchronization.

### Workflow A: Source ingest to curated page

1. **Orchestrator** classifies the request as ingest and confirms the run can only touch allowlisted repository zones.[^4]
2. **Source Intake Steward** validates the asset, registers provenance, and preserves immutability by moving or recording the source without rewriting it.[^2][^4]
3. **Evidence Verifier** checks the intake package and provenance record before any downstream drafting lane opens.[^10][^14]
4. **Policy Arbiter** decides whether the request may advance into policy-cleared drafting or must stop/escalate.[^7]
5. **Synthesis Curator** drafts the cleared create/update package so it matches the page template and source-array requirements.[^5][^6][^9]
6. **Evidence Verifier** re-checks the draft's claims and citations before durable publication in the target expanded verification lane; in today's MVP, that richer post-draft review remains future-state guidance layered on top of the landed intake-evidence contract.[^10][^14]
7. **Policy Arbiter** performs the final governance decision and escalates contradictions instead of silently merging them.[^7]
8. **Topology Librarian** recommends index, link, tag, and alias follow-up only after the governed wiki change is cleared; deterministic index sync still delegates to `sync-knowledgebase-state`, and redirect-style automation remains deferred.[^2][^6][^9]
9. **Maintenance Auditor** can pick up the new page in later sweeps for freshness and symmetry checks.[^11]
10. **Quality Analyst** later updates—or, in today's MVP, recommends—page quality signals and backlog priorities based on existing repo evidence rather than a new analytics runtime.[^13]

This is the primary vertical slice to build first because every later workflow depends on the guarantees established here.[^20]

### Workflow B: Query answer to reusable synthesis

1. **Orchestrator** classifies the request as query.[^15]
2. **Query Synthesist** starts from the wiki index and relevant pages rather than the raw source layer, then produces an answer with inline citations.[^9]
3. If the answer appears valuable enough for durable reuse, it returns to **Knowledgebase Orchestrator** as a governed follow-up request instead of saving directly.[^9]
4. **Evidence Verifier** can later check any newly composed comparative claims before a durable draft is allowed; until that broader verification lane lands, this remains target-state guidance layered on top of the current intake-evidence contract.[^10]
5. **Policy Arbiter** decides whether the answer is still a faithful synthesis instead of new analysis that exceeds the source evidence.[^7]
6. If the answer is valuable and policy-safe, **Synthesis Curator** drafts the durable artifact, then **Evidence Verifier** and **Policy Arbiter** clear publication before **Topology Librarian** recommends the approved graph follow-up and routes any deterministic index work through the existing surfaces.[^9]

This workflow lets the repository compound from usage, not just from ingestion.[^1][^9]

### Workflow C: Ongoing maintenance and patrol

1. **Maintenance Auditor** runs periodic semantic sweeps for orphans, stale content, and contradictory pages.[^11]
2. **Change Patrol** reviews human edits or hook-triggered changes for policy, citation, and namespace violations.[^11]
3. **Quality Analyst** recommends evidence-backed priorities so the next maintenance cycle targets the highest-risk parts of the corpus first, without inventing a new telemetry runtime in MVP.[^13]
4. Any content-changing follow-up returns to **Knowledgebase Orchestrator** so the evidence/policy lane is reopened before synthesis or topology work begins.[^4][^7][^11]
5. **Policy Arbiter** or the **Human Steward** handles anything that cannot be resolved automatically.[^7][^11]

This workflow is what prevents long-term entropy, which the research identifies as the default failure mode of large knowledge repositories.[^1][^11]

## Skill framework status and next additions

The report above is intentionally role-first, but the implementation unit should still be the **skill**, because the repo's skill meta-guidance says skills are workflows, can be chained, and should be invoked when a task matches their process envelope.[^15][^16] The existing custom agents in this repository are already concise persona documents with explicit scope and output contracts, which is the right pattern to reuse for wiki agents as well.[^17][^18][^19]

Today, the skill layer is split across three real states, with direct
`scripts/kb/**` commands still carrying the underlying deterministic runtime:

| Current state | Skills |
|---|---|
| **Thin wrappers with Python logic** | `validate-wiki-governance`, `sync-knowledgebase-state` |
| **Active doc-only skills** | `information-architecture-and-taxonomy`, `ontology-and-entity-modeling`, `knowledge-schema-and-metadata-governance`, `entity-resolution-and-canonicalization`, `search-and-discovery-optimization` |
| **Active doc-only workflow skills** | `validate-inbox-source`, `verify-citations`, `enforce-npov`, `record-open-questions`, `log-policy-conflict`, `review-wiki-plan`, `audit-knowledgebase-workspace` |

Outside the landed wrapper/doc-only entries above, the remaining skill names in
the next tables should be read as target-state workflow labels rather than
current executable repository surfaces.

I recommend organizing the skill inventory into four bands:

| Band | Skills | Why |
|---|---|---|
| **Knowledge-structure skills** | `information-architecture-and-taxonomy`, `ontology-and-entity-modeling`, `knowledge-schema-and-metadata-governance`, `entity-resolution-and-canonicalization`, `search-and-discovery-optimization` | These define the shape of the knowledge system itself: taxonomy, canonical entities, metadata contracts, aliases, and discovery feedback loops should be explicit design workflows rather than incidental byproducts of page creation.[^2][^5][^6][^13][^21] |
| **Foundation skills** | `enforce-repository-boundaries`, `enforce-page-template`, `write-sourceref-citations`, `append-log-entry`, `run-deterministic-validators` | Shared by almost every agent; encode non-negotiable repository contracts.[^4][^5][^14] |
| **Pipeline skills** | `validate-inbox-source`, `extract-entities-and-claims`, `verify-citations`, `enforce-npov`, `update-index`, `semantic-wiki-lint`, `patrol-human-edits`, `compute-kpis` | Map one-to-one to the repeatable jobs identified in the research.[^7][^9][^10][^11][^13] |
| **Escalation/documentation skills** | `record-open-questions`, `log-policy-conflict`, `propose-supersede-or-archive`, `prepare-high-value-synthesis-handoff` | Preserve why a decision was deferred or why a state changed, which matters for future humans and agents.[^5][^7][^21] |

The key design correction here is that **Topology Librarian and Synthesis Curator should consume these knowledge-structure skills, not substitute for them**. Without that separation, taxonomy, ontology, and schema decisions will keep being made implicitly during ingest or maintenance, which is exactly how large knowledgebases drift into inconsistent naming, duplicate concepts, and metadata sprawl.[^2][^5][^6]

Each skill should be authored using the **hybrid contract + assertion** direction already proposed in `docs/ideas/spec.md`: define inputs, outputs, side effects, idempotency, and failure behavior in a compact contract, then pair the high-risk rules with explicit assertions and deterministic checks.[^14] In practice, that means every wiki skill should carry:

1. A short YAML `name` and `description` for discovery.[^8]
2. A step-by-step `SKILL.md` body that stays procedural rather than encyclopedic.[^8]
3. A contract table covering allowed paths, required artifacts, and failure mode.[^14]
4. An assertion checklist for trust-boundary, citation, and policy rules.[^14]
5. Optional `scripts/` and `references/` resources for validators and style guides.[^8][^12]

## Recommended build order

Following the repository's planning guidance, I would implement the framework in four phases rather than trying to land every agent at once.[^20]

1. **Foundation**: Orchestrator, Source Intake Steward, Evidence Verifier, and the shared boundary/schema/provenance skills, plus `knowledge-schema-and-metadata-governance` so the artifact contract is explicit before large-scale page generation begins.[^4][^5][^10][^20][^21]
2. **Knowledge structure**: `information-architecture-and-taxonomy`, `ontology-and-entity-modeling`, and `entity-resolution-and-canonicalization`, because those rules should be defined before synthesis and topology work scale out across the corpus.[^2][^5][^6]
3. **Editorial completeness**: Synthesis Curator, Query Synthesist, Policy Arbiter, Topology Librarian, and `search-and-discovery-optimization`.[^6][^7][^9][^13]
4. **Operational hardening**: Maintenance Auditor, Change Patrol, Quality Analyst, and later KPI/reporting skills within the approved post-MVP package boundary, while keeping the current CI, concurrency, source-boundary, and deny-by-default rules intact.[^11][^13][^20]

That sequence keeps the first slice small enough to verify while also correcting the most important architectural gap from the earlier draft: the wiki needs explicit knowledge-structure decisions before it can reliably automate page creation, taxonomy maintenance, and search optimization at scale.[^2][^5][^6][^20]

## Appendix A: Post-MVP cross-repository customizations to revisit

This appendix is a **forward-looking adaptation backlog**, not a description of
behavior already implemented in this repository. It is intentionally
non-authoritative for current packaging decisions and should **not** be read as
approval to widen runtime write permissions or bypass `docs/architecture.md` /
ADR-007. The repo-level `scripts/validation/**`, `scripts/reporting/**`,
`scripts/context/**`, `scripts/maintenance/**`, and `scripts/ingest/**`
surfaces are now approved package locations, but they still inherit the
repository's existing safety model.

After reviewing the `.github/` customizations in `vscode-genai`, `Scribe`, and `hot-springs-island`, I think this framework should borrow a few patterns deliberately rather than copying their entire ecosystems wholesale. The common theme across all three repos is that they make the control plane **explicit, validated, and self-auditing**, which is exactly what this knowledgebase will need once multiple wiki workers exist.[^22][^23]

- **Borrow `vscode-genai`'s orchestrator-first routing and thin-trigger discipline.** That repo keeps workflow selection concentrated in an orchestrator and preserves prompts as thin triggers instead of procedural payloads, which is a strong fit for this knowledgebase because it prevents the control plane from turning into a second, conflicting workflow layer.[^22][^23] I would make the **Knowledgebase Orchestrator** the default front door for all future wiki automations, and keep any prompts or slash-command entrypoints limited to intent classification plus skill dispatch.

- **Treat state synchronization as a dedicated wiki workflow, not cleanup.** The `vscode-genai` memory manager, memory-sync sub-skill, and governance validators treat project state synchronization as an explicit maintenance concern.[^24][^25][^26] The equivalent follow-on adaptation here would extend `sync-knowledgebase-state` beyond its current index-sync wrapper scope so it can later manage additional governed state such as `wiki/log.md`, backlog or status artifacts, and open-question ledgers after ingest, query persistence, archival, contradiction escalation, or policy review.

- **Adopt governance gates that can run in either signal or blocking mode.** `vscode-genai` couples syntax preflights, wiki-health checks, memory-sync checks, and freshness enforcement with a useful advisory-versus-blocking split.[^25][^26][^27] This framework should later expand `validate-wiki-governance` beyond its current fixed read-only wrapper so it can check SourceRef shape, page-template compliance, backlink or See Also hygiene, append-only log discipline, and freshness thresholds, with `signal` mode for scheduled maintenance and `blocking` mode for merge-critical workflows.

- **Add explicit handoffs and gate checks to every worker agent.** Scribe's agents declare handoff targets, and its orchestration layer validates quality gates before the next specialist takes over.[^28][^29] I would extend each proposed wiki worker with explicit `handoff triggers`, `required deliverables`, and `stop conditions`; for example, Evidence Verifier should gate Policy Arbiter, and Policy Arbiter should either approve or emit an escalation artifact before Topology Librarian runs.

- **Enforce discovery-first, reuse-before-creation discipline.** Scribe formalizes discovery-first workflows and decision matrices so the system enhances existing capabilities before creating new roles or implementations.[^30][^31] This framework should therefore require a discovery pass before adding any new wiki agent, skill, or validator, especially in taxonomy, policy, and synthesis workflows where role sprawl would otherwise become a maintenance tax.

- **Route documentation-like work by change analysis and prerequisite ordering.** Scribe's docs orchestration skill routes work by diff analysis, intent classification, and dependency handling rather than treating documentation as a flat editing task.[^32] The knowledgebase orchestrator should mirror that pattern and choose between ingest, synthesis, verification, topology, maintenance, and analytics paths based on the request and the changed artifacts, not just on user wording.

- **Add a self-auditing maintenance layer for the agent framework itself.** HSI treats the `.github/` layer as an asset that must be audited for broken references, stale commands, and orphaned tools, with optional self-healing behavior.[^33] The landed `audit-knowledgebase-workspace` skill now verifies agent or skill references, documented commands, and attached validators still resolve, and it flags orphaned but useful scripts or docs for governed integration follow-up instead of auto-healing them.

- **Introduce multi-perspective plan review before execution.** HSI's plan-review flow forces a reality check and then reviews plans through TDD, protocol, QA, and docs lenses before implementation begins.[^34] The landed `review-wiki-plan` workflow now applies the same pattern to proposed wiki changes through orchestration, policy, QA, documentation, and execution-boundary lenses before new automation or high-risk governance changes are implemented.

- **Require baseline capture for high-risk wiki changes.** HSI's extraction-quality workflow requires a pre-flight baseline snapshot before implementation so regressions are visible instead of anecdotal.[^35] For schema changes, mass page rewrites, or ingestion-pipeline refactors, this framework should require a baseline capture of target pages or manifests and a post-change diff review before merge.

- **Codify operational reliability and standards-lookup guardrails.** HSI explicitly distinguishes safe versus risky automation patterns and requires standards lookup before proposing plan or documentation changes.[^36][^37] The knowledgebase should capture equivalent wiki-specific guardrails in `AGENTS.md` or a narrow instruction file: prefer deterministic Python validators over brittle shell glue, require standards lookup before changing schema or policy docs, and keep log immutability and raw-source immutability as non-bypassable safety rules.

If I were narrowing this to the **first three adaptations to implement**, I would choose:

1. **`sync-knowledgebase-state` plus `validate-wiki-governance`**, because they harden the control plane and make later automation safer.[^24][^25][^26][^27]
2. **Explicit handoff and gate contracts** for every worker agent, because they turn the proposed roster into an executable workflow instead of a descriptive taxonomy.[^28][^29]
3. **`audit-knowledgebase-workspace` plus `review-wiki-plan`**, because they help the framework resist drift as more skills, prompts, validators, and workflows are added.[^33][^34]

## Appendix B: Post-MVP script adaptation backlog

This appendix is also **future-facing backlog**. The candidate script paths and
skill-local helpers listed here are proposed follow-on work; they are not
present repository paths today unless already called out elsewhere as landed
MVP surfaces. Nothing in this appendix overrides the current rule that
`scripts/kb/**` remains the authoritative execution surface for the currently
landed system.

Reviewing the `skills/*/logic/` surfaces alongside the repo-level `scripts/` directories makes the packaging boundary much clearer for a **post-MVP** phase: small deterministic validators, formatters, and contract enforcers belong with atomic skills, while repository-crawling orchestration, external-service integrations, and batch generation/reporting would belong in repo-level scripts and should be invoked by thin skills rather than embedded inside them.[^38][^39][^40][^41]

### Best candidates to package with atomic skills

These are the pieces I would adapt as skill-local `logic/` assets because they are narrow, deterministic, and reusable across multiple workflows:

| Candidate | Best knowledgebase adaptation | Package location | Why |
| --- | --- | --- | --- |
| `validate_context_imports.py` + `context_import_contract.py` | `validate-context-imports` / `normalize-context-imports` | `.github/skills/.../logic/` | Strict path-shape checks, import-count caps, and legacy-to-strict conversion are ideal skill-local guardrails for any skill that reads or writes structured context files. |
| `validate_wiki_health.py` + `validate-see-also.py` | `validate-wiki-topology` | `.github/skills/.../logic/` | These checks are small but high-leverage: required control artifacts, required headings, orphan detection, and optional `See Also` enforcement map directly onto wiki curation quality gates. |
| `validate-external-sources.py` | `validate-source-registry` | `.github/skills/.../logic/` | A declarative local-vs-external validation registry is a good fit for source-trust skills that need deterministic freshness or provenance checks without a full ingest pipeline. |
| `remediate_docs.py` + `align_tables.py` | `repair-markdown-structure` | `.github/skills/.../logic/` | These are exactly the sort of tiny repair utilities that atomic skills can run after generation to normalize headings, fenced blocks, duplicate headings, and tables. |
| Scribe `validate-documentation` wrapper pattern | `validate-doc-batch` wrapper | `.github/skills/.../logic/` | The important reusable idea is not Scribe's concrete strategy classes, but the wrapper shape: one skill-local entrypoint that runs formatting and link validation and fails closed on remaining errors. |

These atomic-skill candidates are supported by the import contract and validator pair, wiki-health and `See Also` checks, the external-source registry validator, the markdown repair utilities, and Scribe's thin validation wrapper pattern.[^38][^39][^40][^41][^42]

### Best candidates to keep in repo-level scripts after MVP

These are worth adapting after MVP, but they should live as repo-level scripts
because they scan broad directory trees, depend on local project conventions,
call external services, or produce artifacts whose meaning is
repository-specific.

| Candidate | Best knowledgebase adaptation | Post-MVP package location | Why |
| --- | --- | --- | --- |
| `analyze-documentation-freshness.py`, Scribe `check_doc_freshness.py`, HSI `check_doc_freshness.py` | `scripts/validation/check_doc_freshness.py` | `scripts/validation/` | Freshness analysis is inherently repository-aware: it needs git history, path scopes, file-role classification, and project-specific thresholds, so the skill should call it rather than own it. |
| Scribe `generate_docs.py` | `scripts/maintenance/generate_docs.py` | `scripts/maintenance/` | Missing-file generation, API reference building, nav updates, and changelog generation are coordinated batch operations, not single atomic skill steps. |
| Scribe + HSI `manage_gemini_md.py` | `scripts/context/manage_context_pages.py` | `scripts/context/` | Directory discovery heuristics, exclusion rules, diff-based scope reduction, and coverage reporting are repo-topology concerns that should remain script-level. |
| Scribe + HSI `orchestrate_gemini_md_content_fill.py` | `scripts/context/fill_context_pages.py` | `scripts/context/` | Anything that scans the tree, bootstraps config/loggers, and calls Gemini to fill placeholders is too stateful and expensive to bury in a skill-local helper. |
| HSI `snapshot_dataset.py` | `scripts/validation/snapshot_knowledgebase.py` | `scripts/validation/` | Baseline capture and regression comparison are excellent fits for high-risk wiki rewrites, but the snapshot schema and target corpus are repo-level concerns. |
| HSI `extraction_quality_report.py` | `scripts/reporting/content_quality_report.py` | `scripts/reporting/` | Multi-module reporting that merges confidence, health, coverage, schema, density, and integrity checks is valuable, but it is an analytics/reporting program more than an atomic skill primitive. |
| HSI `convert_pdfs_to_md.py` | `scripts/ingest/convert_sources_to_md.py` | `scripts/ingest/` | Source conversion with Drive lookups, converter fallbacks, and persistence back to storage is a heavyweight ingest utility that should sit behind an intake skill, not inside one. |

These repo-level candidates are supported by the three freshness analyzers, Scribe's batch documentation generator, the two context-page management/update flows, the snapshot regression tool, the multi-module extraction quality reporter, and the PDF-to-Markdown ingest utility.[^43][^44][^45][^46][^47][^48][^49]

### Packaging rule inside the approved post-MVP boundary

Within the approved post-MVP package boundary, I would use this rule of thumb:

1. **Put it in a skill's `logic/` folder** when it is deterministic, side-effect-bounded, fast enough to run as part of a single workflow step, and reusable across multiple agents without knowledge of the whole repo state.[^38][^39][^41][^42]
2. **Put it in repo-level `scripts/`** when it walks the repository, maintains durable artifacts, computes reports, snapshots baselines, or depends on external services, credentials, or repository-specific file conventions.[^43][^44][^45][^46][^47][^48][^49]
3. **Expose repo scripts through thin atomic skills** so the orchestrator still has a clean vocabulary such as `scan-content-freshness`, `refresh-context-pages`, `fill-context-pages`, `snapshot-knowledgebase`, or `report-content-quality`, while the heavy operational logic stays testable and reusable as normal scripts.[^42][^44][^46]

### Recommended script adaptation backlog

If I were converting this evaluation into a **post-MVP** implementation queue,
I would start with:

1. **Skill-local validators/repairs**: `validate-context-imports`, `validate-wiki-topology`, `validate-source-registry`, and `repair-markdown-structure`.[^38][^39][^40][^41]
2. **Repo-level maintenance and context automation**: `scripts/validation/check_doc_freshness.py` and `scripts/context/manage_context_pages.py` with a paired `fill_context_pages.py` orchestrator.[^43][^45][^46]
3. **Repo-level ingest/reporting utilities**: `scripts/ingest/convert_sources_to_md.py`, `scripts/validation/snapshot_knowledgebase.py`, and `scripts/reporting/content_quality_report.py` for high-risk migrations and ongoing corpus health reporting.[^47][^48][^49]

This queue is explicitly out of scope for the current landed MVP runtime even
though its package locations are now approved by `docs/architecture.md` and
ADR-007.

## Confidence Assessment

**High confidence:** The control-plane split between concise personas, durable repository guardrails, and on-demand workflow skills is strongly supported by the research and aligns cleanly with this repo's existing `AGENTS.md`, page template, skill library, and custom-agent patterns.[^3][^4][^5][^8][^15][^17]

**Medium confidence:** The exact roster size is a design choice rather than a directly prescribed list in the source research; I chose to separate query synthesis, topology maintenance, patrol, and quality analysis because those jobs have different triggers, failure modes, and escalation paths, which should make the eventual skills smaller and more deterministic.[^9][^11][^13][^20]

**Medium confidence:** Some path names in the research are generic examples rather than this repository's exact layout, so I adapted them to the repo's real constraints; for example, the research discusses append-only logging and skill directories conceptually, while this repo's binding paths are `wiki/log.md`, `schema/page-template.md`, `.github/skills/`, and `.github/agents/`.[^4][^5][^8][^17]

## Footnotes

[^1]: `raw/inbox/LLMwiki-best practices-research.md:5-11`
[^2]: `raw/inbox/LLMwiki-best practices-research.md:15-35`
[^3]: `raw/inbox/LLMwiki-best practices-research.md:37-46`
[^4]: `AGENTS.md:5-25`
[^5]: `schema/page-template.md:1-31`
[^6]: `raw/inbox/LLMwiki-best practices-research.md:57-67`
[^7]: `raw/inbox/LLMwiki-best practices-research.md:69-87`
[^8]: `raw/inbox/LLMwiki-best practices-research.md:89-107`
[^9]: `raw/inbox/LLMwiki-best practices-research.md:109-121`
[^10]: `raw/inbox/LLMwiki-best practices-research.md:123-137`
[^11]: `raw/inbox/LLMwiki-best practices-research.md:139-156`
[^12]: `raw/inbox/LLMwiki-best practices-research.md:158-172`
[^13]: `raw/inbox/LLMwiki-best practices-research.md:174-199`
[^14]: `docs/ideas/spec.md:4-21`
[^15]: `.github/skills/using-agent-skills/SKILL.md:14-37`
[^16]: `.github/skills/using-agent-skills/SKILL.md:123-149`
[^17]: `.github/agents/code-reviewer.md:1-92`
[^18]: `.github/agents/test-engineer.md:1-90`
[^19]: `.github/agents/security-auditor.md:1-96`
[^20]: `.github/skills/planning-and-task-breakdown/SKILL.md:22-223`
[^21]: `.github/skills/documentation-and-adrs/SKILL.md:8-27,240-278`
[^22]: `vscode-genai/.github/README.md:7,34,52,65`
[^23]: `vscode-genai/.github/agents/repo-orchestrator.agent.md:25,35,51,61`
[^24]: `vscode-genai/.github/agents/memory-manager.agent.md:27-52`; `vscode-genai/.github/skills/project-management-memory-sync/SKILL.md:1-39`
[^25]: `vscode-genai/.github/skills/documentation-validation/SKILL.md:85,113,117,122`
[^26]: `vscode-genai/.github/workflows/validate-context-links.yml:61,67,73,75`
[^27]: `vscode-genai/.github/workflows/documentation-freshness.yml:7,69,70,107-110`
[^28]: `Scribe/.github/agents/qa.md:23,28,32,40`
[^29]: `Scribe/.github/skills/agent-orchestration-patterns/SKILL.md:741,808,822,828`; `Scribe/.github/skills/quality-validation-workflow/SKILL.md:127-131,185,423,430,433`
[^30]: `Scribe/.github/skills/protocol-based-testing/SKILL.md:17,90,125,132,146,150`
[^31]: `Scribe/.github/skills/infrastructure-analysis/SKILL.md:141,169,171,180,526`
[^32]: `Scribe/.github/skills/docs-agent-orchestrator/SKILL.md:24-29`
[^33]: `hot-springs-island/.github/skills/audit-workspace/SKILL.md:57,60,62,72,82,92`
[^34]: `hot-springs-island/.github/prompts/review-plan.prompt.md:7,12,19,27,33,36`
[^35]: `hot-springs-island/.github/skills/verify-extraction-quality/SKILL.md:21,27,30,88`
[^36]: `hot-springs-island/.github/instructions/operational-reliability.instructions.md:10,19,27`
[^37]: `hot-springs-island/.github/instructions/documentation_standards.instructions.md:29,33`
[^38]: `vscode-genai/.github/skills/documentation-validation/logic/validate_context_imports.py:21,37,57,67,75,131`; `vscode-genai/scripts/utils/context_import_contract.py:90,134,151,159`
[^39]: `vscode-genai/.github/skills/documentation-validation/logic/validate_wiki_health.py:21-22,122,136,166-178,195,211`; `vscode-genai/.github/skills/documentation-validation/logic/validate-see-also.py:10,46,49`
[^40]: `vscode-genai/.github/skills/documentation-validation/logic/validate-external-sources.py:8,51,54,56,66,93`
[^41]: `vscode-genai/scripts/utils/remediate_docs.py:19,24,30,45-47,63,87`; `vscode-genai/scripts/utils/align_tables.py:6,41,52,82,90`
[^42]: `Scribe/.github/skills/validate-documentation/logic/wrapper.py:20-21,45,51,55-56,61`; `Scribe/scripts/validation/validate_links.py:23,52-58,61,64,72-73`
[^43]: `vscode-genai/.github/skills/documentation-validation/logic/analyze-documentation-freshness.py:34,243,257,272,283,286,288,291,352-357,367,377-407`; `Scribe/scripts/validation/check_doc_freshness.py:4,27,66-67,70,75,88,99`; `hot-springs-island/scripts/validation/check_doc_freshness.py:190,236,317,390,579,657,662,665,668,671,677,891`
[^44]: `Scribe/scripts/maintenance/generate_docs.py:82,86,90,94`
[^45]: `Scribe/scripts/manage_gemini_md.py:58,69,77,94`; `hot-springs-island/scripts/context/manage_gemini_md.py:42,69,163,180,327,383,503,587,666,680-681`
[^46]: `Scribe/scripts/maintenance/orchestrate_gemini_md_content_fill.py:4,32-33,41,46,67-68,75,80,84,128`; `hot-springs-island/scripts/context/orchestrate_gemini_md_content_fill.py:50,176,190,203,250,319,366,376,378,445,453,457`
[^47]: `hot-springs-island/scripts/validation/snapshot_dataset.py:94,129,244,273,373,379,415,435,494,500`
[^48]: `hot-springs-island/scripts/reporting/extraction_quality_report.py:537,607,648,735,777,869,934,951-955,1010-1015`
[^49]: `hot-springs-island/scripts/generators/convert_pdfs_to_md.py:1,3-5,27,35,70,97,105,124,131`
