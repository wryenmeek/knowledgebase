---
name: using-agent-skills
description: Discovers and invokes agent skills. Use when starting a session or when you need to discover which skill applies to the current task. This is the meta-skill that governs how all other skills are discovered and invoked.
---

# Using Agent Skills

## Overview

Agent Skills is a collection of engineering workflow skills organized by development phase. Each skill encodes a specific process that senior engineers follow. This meta-skill helps you discover and apply the right skill for your current task.

## Skill Discovery

When a task arrives, identify the development phase and apply the corresponding skill:

```
Task arrives
    │
    ├── Unfamiliar territory? ──────→ zoom-out
    ├── Vague idea/need refinement? ──→ idea-refine
    ├── Need to stress-test a plan? ──→ grill-me
    ├── New project/feature/change? ──→ spec-driven-development
    ├── Have a spec, need tasks? ──────→ planning-and-task-breakdown
    ├── Implementing code? ────────────→ incremental-implementation
    │   ├── UI work? ─────────────────→ frontend-ui-engineering
    │   ├── API work? ────────────────→ api-and-interface-design
    │   ├── Need better context? ─────→ context-engineering
    │   └── Need doc-verified code? ───→ source-driven-development
    ├── Writing/running tests? ────────→ test-driven-development
    │   └── Browser-based? ───────────→ browser-testing-with-devtools
    ├── Something broke? ──────────────→ debugging-and-error-recovery
    ├── Reviewing code? ───────────────→ code-review-and-quality
    │   ├── Multi-step quality gate? ──→ quality-pass-chain
    │   ├── Security concerns? ───────→ security-and-hardening
    │   └── Performance concerns? ────→ performance-optimization
    ├── Committing/branching? ─────────→ git-workflow-and-versioning
    ├── CI/CD pipeline work? ──────────→ ci-cd-and-automation
    ├── Writing docs/ADRs? ───────────→ documentation-and-adrs
    │   └── Restructuring prose? ─────→ edit-article
    ├── Deploying/launching? ─────────→ shipping-and-launch
    ├── Agent-to-agent handoff? ──────→ caveman
    ├── Wiki intake rejected? ────────→ log-intake-rejection
    │   └── Reconsidering rejection? ─→ reconsider-rejected-source
    ├── Invoking a specialist agent?
    │   ├── Code review? ────────────→ @code-reviewer
    │   ├── Security review? ────────→ @security-auditor
    │   ├── Test strategy/coverage? ─→ @test-engineer
    │   ├── Documentation / ADRs? ───→ @documentation-engineer
    │   ├── Architecture proposals? ─→ @solutions-architect
    │   └── Framework authoring? ────→ @framework-engineer
    ├── Simplifying existing code? ───→ code-simplification
    ├── Removing/migrating systems? ──→ deprecation-and-migration
    ├── Auditing framework workspace? → audit-knowledgebase-workspace
    ├── Jules session stalled/review? → jules-session-triage
    └── Knowledgebase / wiki work?
        ├── Taxonomy/namespace? ──────────→ information-architecture-and-taxonomy
        ├── Schema/metadata governance? ──→ knowledge-schema-and-metadata-governance
        ├── Entity/ontology modeling? ────→ ontology-and-entity-modeling
        ├── Discoverability review? ───────→ search-and-discovery-optimization
        ├── Content freshness scan? ───────→ scan-content-freshness
        ├── Content quality report? ───────→ report-content-quality
        ├── Quality follow-up priority? ───→ prioritize-quality-follow-up
        ├── Context page fill/refresh? ────→ fill-context-pages / refresh-context-pages
        ├── Generate docs/ content? ───────→ generate-maintenance-docs
        ├── Knowledgebase snapshot? ───────→ snapshot-knowledgebase
        ├── Source conversion preview? ────→ convert-sources-to-md
        ├── Index sync/check? ─────────────→ sync-knowledgebase-state
        ├── Review a wiki plan? ───────────→ review-wiki-plan
        └── Route query for durable follow-up? → prepare-high-value-synthesis-handoff
```

## Core Operating Behaviors

These behaviors apply at all times, across all skills. They are non-negotiable.

### 1. Surface Assumptions

Before implementing anything non-trivial, explicitly state your assumptions:

```
ASSUMPTIONS I'M MAKING:
1. [assumption about requirements]
2. [assumption about architecture]
3. [assumption about scope]
→ Correct me now or I'll proceed with these.
```

Don't silently fill in ambiguous requirements. The most common failure mode is making wrong assumptions and running with them unchecked. Surface uncertainty early — it's cheaper than rework.

### 2. Manage Confusion Actively

When you encounter inconsistencies, conflicting requirements, or unclear specifications:

1. **STOP.** Do not proceed with a guess.
2. Name the specific confusion.
3. Present the tradeoff or ask the clarifying question.
4. Wait for resolution before continuing.

**Bad:** Silently picking one interpretation and hoping it's right.
**Good:** "I see X in the spec but Y in the existing code. Which takes precedence?"

### 3. Push Back When Warranted

You are not a yes-machine. When an approach has clear problems:

- Point out the issue directly
- Explain the concrete downside (quantify when possible — "this adds ~200ms latency" not "this might be slower")
- Propose an alternative
- Accept the human's decision if they override with full information

Sycophancy is a failure mode. "Of course!" followed by implementing a bad idea helps no one. Honest technical disagreement is more valuable than false agreement.

### 4. Enforce Simplicity

Your natural tendency is to overcomplicate. Actively resist it.

Before finishing any implementation, ask:
- Can this be done in fewer lines?
- Are these abstractions earning their complexity?
- Would a staff engineer look at this and say "why didn't you just..."?

If you build 1000 lines and 100 would suffice, you have failed. Prefer the boring, obvious solution. Cleverness is expensive.

### 5. Maintain Scope Discipline

Touch only what you're asked to touch.

Do NOT:
- Remove comments you don't understand
- "Clean up" code orthogonal to the task
- Refactor adjacent systems as a side effect
- Delete code that seems unused without explicit approval
- Add features not in the spec because they "seem useful"

Your job is surgical precision, not unsolicited renovation.

### 6. Verify, Don't Assume

Every skill includes a verification step. A task is not complete until verification passes. "Seems right" is never sufficient — there must be evidence (passing tests, build output, runtime data).

## Failure Modes to Avoid

These are the subtle errors that look like productivity but create problems:

1. Making wrong assumptions without checking
2. Not managing your own confusion — plowing ahead when lost
3. Not surfacing inconsistencies you notice
4. Not presenting tradeoffs on non-obvious decisions
5. Being sycophantic ("Of course!") to approaches with clear problems
6. Overcomplicating code and APIs
7. Modifying code or comments orthogonal to the task
8. Removing things you don't fully understand
9. Building without a spec because "it's obvious"
10. Skipping verification because "it looks right"

## Skill Rules

1. **Check for an applicable skill before starting work.** Skills encode processes that prevent common mistakes.

2. **Skills are workflows, not suggestions.** Follow the steps in order. Don't skip verification steps.

3. **Multiple skills can apply.** A feature implementation might involve `idea-refine` → `spec-driven-development` → `planning-and-task-breakdown` → `incremental-implementation` → `test-driven-development` → `code-review-and-quality` → `shipping-and-launch` in sequence.

4. **When in doubt, start with a spec.** If the task is non-trivial and there's no spec, begin with `spec-driven-development`.

## Lifecycle Sequence

For a complete feature, the typical skill sequence is:

```
0. zoom-out                    → Orient in unfamiliar territory
1. idea-refine                 → Refine vague ideas
1.5 grill-me                   → Stress-test before committing
2. spec-driven-development     → Define what we're building
2.5 api-and-interface-design   → Explore interface alternatives
3. planning-and-task-breakdown → Break into verifiable chunks
4. context-engineering         → Load the right context
5. source-driven-development   → Verify against official docs
6. incremental-implementation  → Build slice by slice
7. test-driven-development     → Prove each slice works
8. code-review-and-quality     → Review before merge
9. git-workflow-and-versioning → Clean commit history
10. documentation-and-adrs     → Document decisions
11. shipping-and-launch        → Deploy safely
```

Not every task needs every skill. A bug fix might only need: `debugging-and-error-recovery` → `test-driven-development` → `code-review-and-quality`.

## Skill Routing

Skills fall into three routing categories based on **execution role**:

**Operator-direct** (`Direct`) — self-contained procedures safe to invoke explicitly by the operator
(human or CI). Do not require persona mediation:
`zoom-out`, `grill-me`, `edit-article`, `caveman`, `quality-pass-chain`,
`write-a-skill`, `request-refactor-plan`, `triage-issue`,
`improve-codebase-architecture`, `reconsider-rejected-source`,
`code-simplification`, `deprecation-and-migration`,
`audit-knowledgebase-workspace`, `jules-session-triage`,
`fill-context-pages`, `generate-maintenance-docs`,
`information-architecture-and-taxonomy`, `knowledge-schema-and-metadata-governance`,
`ontology-and-entity-modeling`, `refresh-context-pages`,
`report-content-quality`, `scan-content-freshness`,
`search-and-discovery-optimization`, `snapshot-knowledgebase`,
`prioritize-quality-follow-up`.

**Persona-routed** (`Persona`) — intended as governed pipeline steps called by agent personas
(e.g., `knowledgebase-orchestrator`, `synthesis-curator`, `source-intake-steward`,
`maintenance-auditor`, `quality-analyst`, `change-patrol`, `evidence-verifier`,
`policy-arbiter`, `topology-librarian`). Generally should not be invoked directly:
`log-intake-rejection`, `route-wiki-task`, `plan-wiki-job`,
`enforce-page-template`, `validate-inbox-source`,
`enforce-repository-boundaries`, `run-deterministic-validators`,
`validate-wiki-governance`,
`analyze-missed-queries`, `append-log-entry`, `append-maintenance-log`,
`check-link-topology`, `checksum-asset`, `claim-inventory`,
`compare-against-existing-pages`, `compute-kpis`,
`create-intake-manifest`, `cross-reference-symmetry-check`,
`detect-ai-tells`, `detect-original-research`, `enforce-npov`,
`entity-resolution-and-canonicalization`, `escalate-contradictions`,
`extract-entities-and-claims`, `fail-closed-on-errors`, `freshness-audit`,
`handoff-query-derived-page`, `log-ingest-event`, `log-patrol-incident`,
`log-policy-conflict`, `patrol-human-edits`, `persist-query-result`,
`policy-diff-review`, `prioritize-curation-backlog`,
`propose-supersede-or-archive`, `recommend-maintenance-follow-up`,
`record-open-questions`, `register-source-provenance`, `retrieve-from-index`,
`route-noncompliant-edit-for-review`, `run-ingest`, `score-page-quality`,
`semantic-wiki-lint`, `semi-formal-reasoning`,
`synthesize-cited-answer`, `synthesize-concept-page`, `synthesize-entity-page`,
`update-index`, `verify-citations`, `write-sourceref-citations`.

**Hybrid** (`Both`) — operator-safe but also used as governed pipeline steps. May be invoked
either way:
`convert-sources-to-md`, `sync-knowledgebase-state`, `review-wiki-plan`,
`manage-redirects-and-anchors`, `validate-taxonomy-placement`,
`suggest-backlinks`, `prepare-high-value-synthesis-handoff`.

See the Route column in the Quick Reference table for a per-skill label.

## Quick Reference

| Phase | Skill | Route | One-Line Summary |
|-------|-------|-------|-----------------|
| Orient | zoom-out | Direct | Map modules, callers, and abstractions before diving in |
| Define | idea-refine | Direct | Refine ideas through structured divergent and convergent thinking |
| Define | grill-me | Direct | Stress-test plans through adversarial questioning |
| Define | spec-driven-development | Direct | Requirements and acceptance criteria before code |
| Plan | planning-and-task-breakdown | Direct | Decompose into small, verifiable tasks |
| Build | incremental-implementation | Direct | Thin vertical slices, test each before expanding |
| Build | source-driven-development | Direct | Verify against official docs before implementing |
| Build | context-engineering | Direct | Right context at the right time |
| Build | frontend-ui-engineering | Direct | Production-quality UI with accessibility |
| Build | api-and-interface-design | Direct | Stable interfaces with clear contracts |
| Verify | test-driven-development | Direct | Failing test first, then make it pass |
| Verify | browser-testing-with-devtools | Direct | Chrome DevTools MCP for runtime verification |
| Verify | debugging-and-error-recovery | Direct | Reproduce → localize → fix → guard |
| Review | code-review-and-quality | Direct | Five-axis review with quality gates |
| Review | code-simplification | Direct | Simplify code for clarity without changing behavior |
| Review | quality-pass-chain | Direct | Orchestrate 4-step quality gate sequence |
| Review | security-and-hardening | Direct | OWASP prevention, input validation, least privilege |
| Review | performance-optimization | Direct | Measure first, optimize only what matters |
| Ship | git-workflow-and-versioning | Direct | Atomic commits, clean history |
| Ship | ci-cd-and-automation | Direct | Automated quality gates on every change |
| Ship | documentation-and-adrs | Direct | Document the why, not just the what |
| Ship | deprecation-and-migration | Direct | Manage removal and migration of old systems or APIs |
| Ship | edit-article | Direct | Restructure prose for clarity without changing facts |
| Ship | shipping-and-launch | Direct | Pre-launch checklist, monitoring, rollback plan |
| Operate | caveman | Direct | Compress agent-to-agent handoffs for efficiency |
| Operate | log-intake-rejection | Persona | Persist write-once rejection records to raw/rejected/ |
| Operate | reconsider-rejected-source | Direct | Re-evaluate previously rejected sources |
| Meta | write-a-skill | Direct | Create new skills with all required wiring steps |
| Meta | request-refactor-plan | Direct | Structure refactoring proposals as GitHub Issues |
| Meta | triage-issue | Direct | Classify and prioritize GitHub Issues |
| Meta | improve-codebase-architecture | Direct | Identify and propose architecture improvements |
| Meta | audit-knowledgebase-workspace | Direct | Verify skills, agents, tests, and wrappers point at real surfaces |
| Meta | jules-session-triage | Direct | Triage Jules sessions and route review feedback to stuck sessions |
| KB / Governance | information-architecture-and-taxonomy | Direct | Govern wiki namespace placement, browse paths, and tags |
| KB / Governance | knowledge-schema-and-metadata-governance | Direct | Validate frontmatter, propose fields, assess schema-change policy |
| KB / Governance | ontology-and-entity-modeling | Direct | Model canonical subjects, aliases, and relationship vocabulary |
| KB / Governance | search-and-discovery-optimization | Direct | Review page titles, tags, and index placement for retrieval effectiveness |
| KB / Governance | review-wiki-plan | Both | Review wiki plans against MVP governance before approval |
| KB / Ingest | validate-inbox-source | Persona | Validate source provenance and format before ingest |
| KB / Ingest | checksum-asset | Persona | Compute and record SHA-256 checksum for a raw asset |
| KB / Ingest | register-source-provenance | Persona | Record canonical provenance metadata for intake sources |
| KB / Ingest | claim-inventory | Persona | Enumerate and attribute factual claims from an intake package |
| KB / Ingest | create-intake-manifest | Persona | Assemble sealed intake manifest for evidence and policy review |
| KB / Ingest | convert-sources-to-md | Both | Preview or apply inbox source conversion to Markdown |
| KB / Ingest | run-ingest | Persona | Run the deterministic source ingest pipeline |
| KB / Ingest | log-ingest-event | Persona | Record a state-change entry in wiki/log.md after ingest |
| KB / Ingest | write-sourceref-citations | Persona | Write canonical SourceRef provenance strings |
| KB / Synthesis | extract-entities-and-claims | Persona | Extract entities, concepts, claims, and chronology from a cleared package |
| KB / Synthesis | entity-resolution-and-canonicalization | Persona | Resolve duplicates, aliases, and canonical naming conflicts |
| KB / Synthesis | entity-resolution-and-canonicalization | Persona | Determine canonical identity for disputed entities; produce merge, split, alias, or escalation decision |
| KB / Synthesis | enforce-npov | Persona | Apply neutral-point-of-view policy to drafts and synthesis |
| KB / Synthesis | detect-ai-tells | Persona | Flag hallucination markers and AI-generation artifacts |
| KB / Synthesis | detect-original-research | Persona | Detect unsourced conclusions that exceed cited support |
| KB / Synthesis | semi-formal-reasoning | Persona | Assess whether stated conclusions follow from cited premises |
| KB / Synthesis | compare-against-existing-pages | Persona | Detect duplicates and conflicts before new-page publication |
| KB / Synthesis | synthesize-entity-page | Persona | Draft a policy-cleared entity wiki page from a verified package |
| KB / Synthesis | synthesize-concept-page | Persona | Draft a policy-cleared concept wiki page from a verified package |
| KB / Synthesis | verify-citations | Persona | Verify SourceRef citation readiness and provenance completeness |
| KB / Synthesis | escalate-contradictions | Persona | Produce a governed escalation record for unresolvable conflicts |
| KB / Synthesis | record-open-questions | Persona | Capture unresolved evidence or policy gaps for later follow-up |
| KB / Query | retrieve-from-index | Persona | Retrieve relevant wiki pages and index entries before synthesis |
| KB / Query | synthesize-cited-answer | Persona | Produce a cited answer from curated retrieval results |
| KB / Query | handoff-query-derived-page | Persona | Convert a query result into a governed editorial handoff |
| KB / Query | prepare-high-value-synthesis-handoff | Both | Package a cited insight for governed durable follow-up |
| KB / Query | persist-query-result | Persona | Persist a cleared query result via the governed script surface |
| KB / Maintenance | semantic-wiki-lint | Persona | Audit wiki pages for stale summaries, orphaned evidence, broken relationships |
| KB / Maintenance | freshness-audit | Persona | Produce a read-only freshness assessment of wiki or docs content |
| KB / Maintenance | scan-content-freshness | Direct | Run deterministic freshness age checks over wiki or docs |
| KB / Maintenance | cross-reference-symmetry-check | Persona | Audit wiki cross-references for symmetry and dangling links |
| KB / Maintenance | check-link-topology | Persona | Review link topology impacts of cleared editorial changes |
| KB / Maintenance | propose-supersede-or-archive | Persona | Recommend retiring, replacing, or marking pages as historical |
| KB / Maintenance | recommend-maintenance-follow-up | Persona | Package maintenance findings into a recommendation-first handoff |
| KB / Maintenance | append-maintenance-log | Persona | Record a maintenance-event entry in wiki/log.md |
| KB / Quality | score-page-quality | Persona | Produce a read-only quality score for a wiki page |
| KB / Quality | analyze-missed-queries | Persona | Scan wiki for coverage gaps, missing citations, and placeholders |
| KB / Quality | compute-kpis | Persona | Aggregate repo-level quality KPIs from quality-scores artifacts |
| KB / Quality | report-content-quality | Direct | Summarize content quality signals without persisting undeclared artifacts |
| KB / Quality | prioritize-curation-backlog | Persona | Rank open curation work items by quality signals and evidence |
| KB / Quality | prioritize-quality-follow-up | Direct | Rank quality follow-up work from existing evidence (recommend-only) |
| KB / Topology | manage-redirects-and-anchors | Both | Record redirect entries when pages are renamed, merged, or superseded |
| KB / Topology | suggest-backlinks | Both | Recommend governed backlink opportunities between cleared pages |
| KB / Topology | validate-taxonomy-placement | Both | Validate page placement against taxonomy and identity contracts |
| KB / Topology | update-index | Persona | Prepare governed wiki/index.md follow-up after structural changes |
| KB / Topology | sync-knowledgebase-state | Both | Check or refresh wiki/index.md through allowlisted wrappers |
| KB / Topology | snapshot-knowledgebase | Direct | Capture a read-only baseline over wiki, schema, and raw artifacts |
| KB / Change patrol | patrol-human-edits | Persona | Diff-based risk classification for changed wiki content |
| KB / Change patrol | policy-diff-review | Persona | Risk-classify wiki/source edits for governance follow-up |
| KB / Change patrol | log-patrol-incident | Persona | Package change-patrol incidents into append-only escalation records |
| KB / Change patrol | log-policy-conflict | Persona | Record contradiction or policy-conflict outcomes in append-only form |
| KB / Change patrol | route-noncompliant-edit-for-review | Persona | Route high-risk change-patrol findings to the governed review lane |
| KB / Pipeline | route-wiki-task | Persona | Route wiki tasks through the ingest-safe governance lane |
| KB / Pipeline | plan-wiki-job | Persona | Plan and scope a governed wiki job before execution |
| KB / Pipeline | fail-closed-on-errors | Persona | Enforce fail-closed behavior when a governed step errors or is incomplete |
| KB / Pipeline | enforce-page-template | Persona | Validate wiki page frontmatter and heading structure |
| KB / Pipeline | enforce-repository-boundaries | Persona | Enforce repository path allowlist for governed writes |
| KB / Pipeline | run-deterministic-validators | Persona | Run allowlisted validators against schema, wiki, and raw evidence |
| KB / Pipeline | validate-wiki-governance | Persona | Run full governance preflight before any wiki write |
| KB / Pipeline | append-log-entry | Persona | Append a state-change entry to wiki/log.md |
| KB / Context | fill-context-pages | Direct | Fill placeholder markers in .github/skills/** or docs/** files |
| KB / Context | generate-maintenance-docs | Direct | Generate and apply docs/ content via a two-step governed workflow |
| KB / Context | refresh-context-pages | Direct | Refresh context-page inventories and fill plans |
| Dev / Docs | documentation-engineer | Direct | Author, audit, and maintain documentation and ADRs with engineering rigor |
| Dev / Architecture | solutions-architect | Direct | Produce architecture proposals, refactoring plans, and migration decisions |
| Dev / Meta | framework-engineer | Direct | Author new skills, audit framework integrity, maintain .github/ surface |
