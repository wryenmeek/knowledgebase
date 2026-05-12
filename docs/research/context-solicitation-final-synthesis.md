# Context-Solicitation Skill Design Patterns: A Three-Repository Comparative Analysis

**Scope:** How `mattpocock/skills`, `ea-toolkit/ddc`, and `wryenmeek/knowledgebase` approach the problem of designing AI agent skills that effectively solicit, validate, and preserve context from human collaborators.

**Method:** Initial analysis via 7 research subagent dispatches across 2 waves. Adversarial validation via 10 additional subagent dispatches across 2 waves, checking all claims against primary sources. This corrected report incorporates all verified findings and corrections.

**Lineage:** Synthesized from `context-solicitation-skill-design-patterns.md` (original analysis) and `context-solicitation-adversarial-review.md` (adversarial validation). Both source documents are preserved alongside this report.

---

## Executive Summary

Two of these three repositories arrived at similar context-solicitation patterns independently; the third explicitly adopted and adapted from one of the others. **mattpocock/skills** established the "grilling" interaction pattern — one question at a time with agent-proposed answers, converging when all decision branches resolve. **ea-toolkit/ddc** independently developed the "demand checklist" pattern — entity-typed gap analysis driven by intentional failure, converging when checklist size reaches zero. **wryenmeek/knowledgebase** researched mattpocock/skills and explicitly adopted 4 skills (grill-me, zoom-out, caveman, edit-article), then extended them with governance infrastructure — structured confusion protocols, escalation-first design, and uncertainty preserved as first-class artifacts rather than resolved by guessing.

The KB↔mattpocock relationship is **derivation, not convergence** — KB's own SKILL.md files contain explicit "Adapted from" and "Inspired by" attribution lines [^1]. Only the DDC↔mattpocock similarity appears genuinely convergent (zero cross-references in either direction) [^1]. Despite different lineages, all three share five design principles: one-at-a-time questioning (with counter-examples), anti-hallucination as structural constraint, self-resolution before human query, dynamic convergence without fixed question counts, and failure as a discovery mechanism.

Academic research provides partial validation: AGENT-CQ (arXiv:2410.19692, 7 citations) shows AI-generated clarifying questions outperform human-generated ones on retrieval metrics; Elicitron (arXiv:2404.16045, 31 citations) demonstrates that agent-simulated interviews surface latent needs; and Holub et al. (arXiv:2601.14798) find that dynamic stopping outperforms fixed-step questioning [^2].

---

## 1. Three-Repository Overview

### 1.1 mattpocock/skills

**Repository:** `github.com/mattpocock/skills` (SHA ref: `733d3128`)
**Platform:** Claude Code skills (description-triggered routing)
**Philosophy:** Anti-vibe-coding, drawing on Evans (DDD), Beck (XP/TDD), Ousterhout (software design philosophy), and Thomas & Hunt (pragmatic programming) — each cited for distinct frameworks, not a single "DDD-influenced" umbrella [^3]
**Scale:** 27 total skills across 6 tiers, of which **13 are published** in `plugin.json`: 10 engineering, 3 productivity. The remaining 14 span 4 misc, 2 personal, 4 in-progress (including `writing-fragments`, which is draft-only), and 4 deprecated (including `qa`, which caps questions at "2-3 short clarifying questions") [^4]
**Core innovation:** The "grilling" interaction pattern — relentless one-at-a-time questioning with agent-proposed answers, producing CONTEXT.md as the cornerstone cross-skill artifact.
**Notable infrastructure:** `CLAUDE.md` with global rules; `CONTEXT-FORMAT.md` prescribing context file structure; `link-skills.sh` installation script; `.claude-plugin/plugin.json` for published skill registry; `.out-of-scope/question-limits.md` explicitly rejecting question caps as a design decision [^4].

### 1.2 ea-toolkit/ddc

**Repository:** `github.com/ea-toolkit/ddc` (SHA ref: `b8673f18`)
**Platform:** Claude Code skills **and** GitHub Copilot (dual-platform: `.claude/` config + `.github/copilot-instructions.md`) [^5]
**Philosophy:** Demand-driven knowledge curation — curate only what a problem actually demands [^6]
**Scale:** 4 skills (`ddc-cycle`, `ddc-entity`, `ddc-status`, `ddc-demo`) plus 5 sub-agent personas (ta/po/se/da/sa) [^7]
**Core innovation:** The RED→GREEN cycle — intentional failure as a discovery mechanism, producing entity-typed knowledge artifacts with quantified convergence metrics.
**Notable infrastructure:** Programmatic enforcement via 3 hooks (`validate-entity.sh`, `anonymization-guard.sh`, `auto-commit.sh`), 3 rules files (`cycle-log-format.md`, `entity-format.md`, `anonymization.md`), and `settings.json` wiring; local KB explorer (FastAPI backend + React/Cytoscape/BPMN frontend); Firebase Cloud Functions context-gap-scanner web app [^5].

### 1.3 wryenmeek/knowledgebase

**Repository:** `github.com/wryenmeek/knowledgebase`
**Platform:** GitHub Copilot CLI with custom agent personas
**Philosophy:** Provenance-first, policy-aligned — terms from AGENTS.md [^8]. The analytical frame "governed uncertainty" is this report's characterization, not KB's self-description.
**Scale:** 102 skills, 17 agent personas [^9]
**Core innovation:** Structured confusion protocols and escalation-first design — uncertainty is preserved as a first-class artifact rather than resolved by guessing.
**Important caveat:** KB's wiki directories contain only `.gitkeep` files with epoch timestamps — the knowledge surface is **scaffolding, not content** [^10]. DDC's 41+ curated entities and mattpocock's per-project CONTEXT.md outputs represent populated knowledge; KB's 102 skills represent governance tooling for a content surface that does not yet exist. Comparisons should be read as "skills infrastructure" vs. "content outputs."

---

## 2. Lineage and Attribution

Before comparing patterns, the relationship between these repos must be stated precisely:

| Relationship | Evidence | Nature |
|-------------|----------|--------|
| mattpocock → KB | 4 SKILL.md files with "Adapted from" / "Inspired by" lines; ADR-014 cites mattpocock's HITL/AFK pattern; test suite labels them "mattpocock-inspired skills"; `docs/ideas/skill-size-refactoring.md` references "the mattpocock target is ≤100 lines per skill" [^1] | **Direct derivation** |
| DDC ↔ mattpocock | Zero cross-references in either direction [^1] | **Independent arrival** at similar patterns |
| DDC ↔ KB | Zero cross-references in either direction [^1] | **Independent** (KB derived from mattpocock; DDC developed separately) |

This means shared patterns between KB and mattpocock are evidence of successful adoption and adaptation, not convergent evolution. Shared patterns between DDC and either of the others are evidence of independent convergence on similar design pressures.

---

## 3. Comparison Matrix

| Dimension | mattpocock/skills | ea-toolkit/ddc | wryenmeek/knowledgebase |
|-----------|------------------|----------------|------------------------|
| **Question format** | One at a time + agent recommends an answer [^11] | 6-category demand checklist mapped to entity types [^12] | Structured confusion/missing/assumption protocols [^13] |
| **Anti-hallucination rule** | "Explore the codebase instead" [^14] | "Do not speculate beyond what the knowledge base contains" [^15] | "Do not answer speculatively just to unblock automation" [^16] |
| **Convergence model** | All decision branches resolved (qualitative) [^17] | Checklist size → 0 (quantitative) [^18] | All phases complete + user confirms + no open escalations (governed/qualitative) [^19] |
| **Question cap** | Explicitly none — design decision documented in `.out-of-scope/question-limits.md` [^20] | Implicit — bounded by problem scope [^21] | Phase-gated (e.g., 5–8 variations in idea-refine; 3–5 refers to sharpening questions, not ideas) [^22] |
| **Self-resolution before asking** | Yes — "If a question can be answered by exploring the codebase, explore instead" [^14] | Partial — RED phase searches KB entities first [^23] | Yes — zoom-out maps one module and immediate neighbors before surfacing gaps [^24] |
| **Artifact mutation timing** | Inline during conversation — "Don't batch these up" [^25] | **Incremental per-entity** — auto-commit hook fires after every Write/Edit; each entity is individually committed ("commit early, commit often") [^26] | Governed pipeline — questioning is decoupled from wiki writes [^27] |
| **Primary output artifact** | CONTEXT.md + optional ADRs [^28] | Entity files in `domain-knowledge/entities/<type>/` + cycle logs [^29] | Decision logs + open questions + extraction bundles [^30] |
| **Convergence ownership** | Varies: test runner (tdd), user (writing-fragments), or implicit (improve-architecture) [^31] | Human-approved — agent drives curation but human has unilateral veto; "repeat until accepted" [^32] | Governed — orchestrator routes and blocks; downstream evidence-verifier and policy-arbiter validate [^33] |
| **Failure as signal** | Implicit — incorrect answers during grilling surface misunderstandings [^34] | Explicit and central — RED phase failure IS the discovery mechanism [^35] | Implicit — extraction skills route gaps as escalation flags [^36] |
| **Skill routing** | Ambient — agent reads natural language and selects via `description` field; no routing config in CLAUDE.md or settings.json [^37] | Description-triggered (same mechanism as mattpocock); ddc-cycle Steps 0–6 are inline, not sub-skill orchestration [^38] | Hybrid — `description` triggers + `knowledgebase-orchestrator` lane routing for governed work [^39] |
| **Enforcement infrastructure** | `CLAUDE.md` global rules (advisory) [^37] | Hooks (PreToolUse blocking + PostToolUse auto-commit) + rules (glob-scoped always-on) — programmatic enforcement [^5] | Pre-commit hooks + governance lock files + contract-bound write surfaces — strongest enforcement [^8] |

---

## 4. The Grilling Pattern (mattpocock/skills)

### 4.1 Core Mechanism

The grilling pattern appears in **4 mattpocock skills** (`grill-me`, `grill-with-docs`, `improve-codebase-architecture`, `writing-fragments`) with a consistent structural signature [^40]. Note: `diagnose` was previously counted but contains zero grilling language — no "one question at a time," no "recommended answer," no "interview" [^41].

1. **One question at a time** — never batch. "Ask the questions one at a time, waiting for feedback on each question before continuing" [^11].
2. **Agent proposes its own answer** — anchoring the conversation, reducing blank-screen cognitive load, and forcing the human to *react* rather than *generate*.
3. **Self-resolution before human query** — "If a question can be answered by exploring the codebase, explore the codebase instead" [^14].
4. **Walk each branch of the decision tree** — resolving dependencies one-by-one until all branches converge.

**Counter-examples within mattpocock/skills:** The one-at-a-time pattern is not universal even within this repo. `to-issues` Step 4 batches 4 questions simultaneously [^42]. `to-prd` opens with "Do NOT interview the user — just synthesize what you already know" — explicitly forbidding solicitation [^42]. These show the pattern is context-dependent, applied to interactive exploration skills but not to synthesis or triage skills. Conversely, `setup-matt-pocock-skills` (unanalyzed in the original report) is the strongest evidence *for* the pattern: it mandates "one at a time" for 3 configuration decisions and warns "Don't dump all three at once" [^42].

### 4.2 Variants

**`grill-me` (base):** Pure adversarial questioning. No persistent artifact mutation during the session. Output is a decision log of Q&A pairs [^11]. Located in `skills/productivity/` (not `skills/engineering/` as previously reported) [^43].

**`grill-with-docs` (domain-aware):** Extends `grill-me` by reading existing CONTEXT.md and ADR files before questioning. Adds four challenge triggers in priority order [^44]:
1. **Glossary conflict** — term user said ≠ CONTEXT.md definition (highest priority)
2. **Fuzzy/overloaded language** — term has multiple possible referents
3. **Scenario stress-test** — edge cases that probe concept boundaries
4. **Code contradiction** — user's stated claim ≠ what code actually does

Uniquely, `grill-with-docs` mutates CONTEXT.md *inline during the conversation* — "When a term is resolved, update CONTEXT.md right there. Don't batch these up" [^25]. This makes the grilling session a *live editing session* of the domain model.

**ADR gating in `grill-with-docs`:** ADRs are offered only when all three conjunctive gates pass [^45]:
1. Hard to reverse (cost of changing your mind is meaningful)
2. Surprising without context (future reader would wonder "why?")
3. Result of a real trade-off (genuine alternatives existed)

If any single gate fails, no ADR is created. The word "sparingly" appears in the SKILL.md header for ADRs [^45].

**`writing-fragments` (creative, unpublished):** Located in `skills/in-progress/` and excluded from `plugin.json` and README — this is draft-only software, not a deployed pattern [^4]. Adapts the grilling pattern for idea mining. Questions are excavation probes rather than adversarial challenges [^46]:
- "You said X — say it three different ways"
- "What's the version of that you wouldn't say in public?"
- "What's the example that made you believe this in the first place?"

Convergence is externally owned — the agent stops when the user signals readiness (a handoff constraint, not a prohibition on ending) [^46].

**Missing from original analysis:** `zoom-out` and `prototype` are published engineering skills with context-solicitation relevance that were not analyzed [^4].

### 4.3 The CONTEXT.md Artifact

CONTEXT.md is the cornerstone cross-skill artifact in mattpocock/skills — created/updated by `grill-with-docs` and `improve-codebase-architecture`. Other skills reference "domain glossary" generically but do not explicitly name `CONTEXT.md` as a dependency [^43]. Its format is prescribed by CONTEXT-FORMAT.md [^47]:

```
# {Context Name}
{1-2 sentence description}

## Language
**{Term}**: {one sentence definition}
_Avoid_: {synonym1}, {synonym2}

## Relationships
- An **{Term}** produces one or more **{Term}**

## Example dialogue
> **Dev:** "{question using bold terms}"
> **Domain expert:** "{answer clarifying boundary}"

## Flagged ambiguities
- "{word}" was used to mean both **{Term1}** and **{Term2}** — resolved: {resolution}
```

Key design rule: "Don't couple CONTEXT.md to implementation details. Only include terms that are meaningful to domain experts" [^47].

---

## 5. The Demand Checklist Pattern (ea-toolkit/ddc)

### 5.1 Core Mechanism

DDC's demand checklist pattern is structurally analogous to TDD's RED→GREEN cycle. The analogy illuminates the **loop discipline** (fail-first, minimal fill, iterate to pass) but contains three significant disanalogies the structural comparison should not obscure [^48]:

| Phase | TDD | DDC | Disanalogy |
|-------|-----|-----|------------|
| **RED** | Write a failing test (automated, deterministic) | Attempt to answer using only existing KB → produce demand checklist (human-assessed) | TDD's pass/fail is machine-judged and reproducible; DDC's is human-scored 1–5 and subjective |
| **GREEN** | Write minimal code to make the test pass (executable) | Curate entity files to fill gaps (prose, non-executable) | Code can be re-run and falsified; prose correctness is assessed by interpretation |
| **Validation** | Test runner confirms pass (mechanical) | Human scores 1–5; rejection triggers re-entry (editorial) | Refactoring in TDD is structural with objective verification; DDC's "validate and tighten" is editorial revision |

DDC's own METHODOLOGY.md uses careful wording — "Engineers will recognize this structure" — a structural comparison, not a precision claim [^48].

Both treat **intentional failure as an epistemic instrument** — the RED state is more valuable than skipping to implementation because it makes gaps legible [^35].

### 5.2 Demand Checklist Structure

The RED phase produces a demand checklist categorized into 6 entity-type categories [^12]:

1. **Terminology needed** → `jargon-business` or `jargon-tech`
2. **Systems/platforms needed** → `systems`, `platforms`
3. **Processes/events needed** → `processes`, `business-events`
4. **Data structures needed** → `data-models`, `data-products`
5. **Business logic needed** → `capabilities`, `offerings`
6. **People/teams needed** → `teams`, `personas`

Each checklist item maps to an entity type, creating a typed pipeline from "what I don't know" to "what I need to create."

### 5.3 RED Phase Detection Algorithm

The precise algorithm from `ddc-cycle` SKILL.md [^23]:

1. Search `domain-knowledge/entities/` for problem-related terms
2. Read matching entity files and assess coverage
3. Attempt to answer the problem using ONLY existing KB content
4. For each gap: categorize by entity type → add to demand checklist
5. Rate confidence 1–5 and explain what's missing
6. Ask: "Should I proceed with curation? Point me to a source document, answer directly, or both."

### 5.4 Quantified Convergence

DDC provides the most rigorous convergence metrics of all three repos. Per-cycle frontmatter tracks: `entities_created`, `entities_updated`, `entities_reused`, `confidence_before`, `confidence_after`, `human_score`, `checklist_size` [^49].

The `ddc-demo` example shows a complete convergence trajectory over 20 cycles [^18]:
- Gaps: 8→6→5→4→3→3→3→2→2→1→1→1→0
- At cycle 20: zero gaps, 6 entities reused, 0 new entities created = full convergence

The metric labeled "success rate 0.0 → 0.75" in the DDC paper is actually the **reuse ratio** — the proportion of entity reuse across cycles, not a general success rate [^7].

**Convergence claims:** The Navakoti & Navakoti paper (arXiv:2603.14057) presents 9 cycles as an illustration, not a convergence proof. The 20–30 cycle convergence range is explicitly called "a hypothesis" in the paper [^50]. The demo trajectory (13 cycles to zero gaps, 20 to stable) is simulated, not empirical.

### 5.5 Sub-Agent Role Differentiation

DDC's 5 sub-agent personas (ta/po/se/da/sa) share the same demand checklist format but differ in **roles, responsibilities, quality standards, and domain tooling** — not just navigation starting points [^7]:
- **ta-agent** (Technical Architect) → starts from systems/sequences
- **po-agent** (Product Owner) → starts from capabilities/personas
- **se-agent** (Software Engineer) → starts from data-models/APIs
- **da-agent** (Data Analyst) → starts from data-products/data-models
- **sa-agent** (Solutions Architect) → starts from platforms/integrations

This creates a multi-perspective gap scanner — each agent reads the same KB but *notices different gaps* based on its professional lens.

### 5.6 DDC Enforcement Infrastructure

The original analysis omitted DDC's programmatic enforcement layer, which is comparable in kind to KB's pre-commit hooks [^5]:

**Hooks (`.claude/hooks/`):**
- `validate-entity.sh` — PreToolUse blocking hook. Exits 2 if entity `type:` frontmatter doesn't match parent directory name (with pluralization stripping).
- `anonymization-guard.sh` — PreToolUse blocking hook. Checks written content against a configurable `.private/anonymization-map.yaml` (opt-in; skips if map absent). Blocks writes containing real-world terms that break the synthetic naming scheme.
- `auto-commit.sh` — PostToolUse hook. Fires after every Write/Edit to `domain-knowledge/` or `ddc-cycle-logs/`. Generates structured commit messages per entity.

**Rules (`.claude/rules/`):**
- `cycle-log-format.md` — Enforces 7 required sections, sequential numbering, and mandatory logging of *all rejected agent attempts*.
- `entity-format.md` — Enforces required frontmatter, relationship fields, and ≤150 lines per entity file.
- `anonymization.md` — Enforces synthetic naming scheme for the RetailCo example domain.

**Tooling:**
- `tooling/` — Local KB explorer: **FastAPI** backend (not Flask) + React/Cytoscape/BPMN frontend with graph visualization, entity search, and diagram rendering.
- `tools/context-gap-scanner/` — Firebase Cloud Functions web app ("Paste your company docs. See where your AI agents will fail.") using the Anthropic Claude API for gap analysis.

**AI-tool agnosticism:** DDC has both `.claude/` configuration and `.github/copilot-instructions.md` (4.6KB), making it usable with both Claude Code and GitHub Copilot. However, the enforcement layer (hooks blocking bad writes, auto-committing) is Claude Code-exclusive — Copilot users get advisory instructions only [^5].

---

## 6. The Governed Uncertainty Pattern (wryenmeek/knowledgebase)

### 6.1 Core Mechanism

KB's distinctive contribution is treating uncertainty as a first-class artifact rather than something to be resolved immediately. The architectural invariant across KB skills: **preserve uncertainty, don't guess it away** [^16]. Strongest expression in `record-open-questions`: "Do not answer the question speculatively just to unblock automation" [^16].

KB makes this more than advisory through required blocking frontmatter fields [^51]:
- **`open_questions`** — Required field. "Explicit unresolved contradictions, gaps, or escalation needs."
- **`confidence`** — Required field. Integer 1–5, "indicating evidence strength, not author preference."
- **`## Open Questions` body section** — Formally defined: "unresolved items that block or qualify certainty."

These are enforced by deterministic tooling, not just skill instructions.

### 6.2 Structured Confusion Protocols

The `using-agent-skills` skill (not `context-engineering` as previously reported) defines the ASSUMPTIONS protocol. The `context-engineering` skill defines typed protocols for different kinds of uncertainty [^13]:

```
CONFUSION: [conflict] → Options A/B/C → "Which approach?"
MISSING REQUIREMENT: [gap] → Options A/B/C → "Which behavior?"
PLAN: [steps] → "Executing unless you redirect"
ASSUMPTIONS: [list] → "Correct me now or I'll proceed"
```

Each protocol type generates a different downstream action — confusion escalates, missing requirements block, plans proceed with opt-out, assumptions proceed with a correction window. This is more fine-grained than either mattpocock's single-question format or DDC's categorized checklist.

### 6.3 Two-Family Architecture

KB separates context-solicitation into two skill families [^52]:

**Interactive Q&A skills** (require live human):
- `grill-me` — adversarial stress-testing with autopilot guard (adapted from mattpocock/skills) [^1]
- `idea-refine` — iterative divergent/convergent thinking with autopilot guard; generates 5–8 variations per round, with 3–5 sharpening questions [^22]
- `context-engineering` — structured confusion protocols [^13]

**Extraction/Preservation skills** (read-only, deterministic, no human input):
- `zoom-out` — maps one module and immediate neighbors ("List its direct callers and callees. Map one level of abstraction up and one level down") — does NOT read entire codebase structure [^24]
- `analyze-missed-queries` — scans wiki for coverage gaps [^53]
- `record-open-questions` — preserves uncertainty as structured artifacts [^16]
- `claim-inventory` — enumerates factual claims from sources [^54]
- `extract-entities-and-claims` — extracts candidate entities and chronology [^55]
- `using-agent-skills` — meta-skill for skill selection guidance [^56]

The critical design decision: **extraction skills never guess**. They route uncertainty as escalation flags to the governance pipeline. The `knowledgebase-orchestrator` routes and blocks — validation is performed by downstream `evidence-verifier` and `policy-arbiter` personas [^33].

### 6.4 Context-Engineering Logic (Python)

KB's context-engineering skill includes a typed contract system in Python [^57]:

- `context_import_contract.py`: Allowlisted read paths, max 12 imports, path traversal protection, duplicate detection
- `normalize_context_imports.py`: Deterministic normalization of import manifests
- `validate_context_imports.py`: Validation producing structured `ContextImportValidationResult` with reason codes

This is infrastructure that neither mattpocock nor DDC have — a programmatic enforcement layer for context boundaries, not just skill-level instructions.

### 6.5 KB CONTEXT.md System

KB has 5 scoped CONTEXT.md files enforced by a pre-commit hook requiring `## Terms`, `## Invariants`, `## File Roles` sections [^58]:

| File | Scope |
|------|-------|
| `CONTEXT.md` | `scope: repo` |
| `wiki/CONTEXT.md` | `scope: directory` |
| `.github/skills/CONTEXT.md` | `scope: directory` |
| `scripts/kb/CONTEXT.md` | `scope: module` |
| `schema/CONTEXT.md` | `scope: directory` |

This is a **deliberately different format** from mattpocock's CONTEXT-FORMAT.md. KB's format serves operational/governance vocabulary (what things *are*, what invariants hold, where files *live*). mattpocock's serves interaction/linguistic vocabulary (how to *talk*, example dialogues, what to avoid saying). The pre-commit hook is proof of deliberate enforcement — the format difference is governed, not accidental [^58].

---

## 7. Shared Design Principles

Despite different lineages (derivation for KB↔mattpocock; independent for DDC↔others), all three share five principles — though each has counter-examples or nuances.

### 7.1 One-at-a-Time Questioning (with counter-examples)

The one-at-a-time pattern is prominent in all three but is **not universal even within mattpocock/skills**:
- **mattpocock:** "Ask the questions one at a time" [^11]. But `to-issues` batches 4 questions simultaneously in Step 4, and `to-prd` forbids interviewing entirely [^42]. The pattern applies to interactive exploration, not to synthesis or triage.
- **DDC:** Each demand checklist item is resolved individually through RED→GREEN; sub-agents process one entity at a time [^12].
- **KB:** `grill-me` inherits the one-at-a-time pattern (adopted from mattpocock); `idea-refine` evaluates ideas one per round [^22].

### 7.2 Anti-Hallucination as Architecture

All three embed anti-hallucination as a structural constraint, not just a prompt instruction:
- **mattpocock:** "If a question can be answered by exploring the codebase, explore the codebase instead" — prefer verified fact over generated answer [^14]
- **DDC:** "Do not speculate beyond what the knowledge base contains" — KB entities are the only permitted evidence [^15]
- **KB:** "Do not answer the question speculatively just to unblock automation" — uncertainty is preserved rather than filled [^16]

### 7.3 Self-Resolution Before Human Query

All three attempt automated resolution before asking the human:
- **mattpocock:** Codebase exploration as a prerequisite to questioning [^14]
- **DDC:** RED phase searches existing entities before producing the demand checklist [^23]
- **KB:** Extraction skills process sources autonomously; `zoom-out` maps module context before surfacing gaps [^24]

### 7.4 Dynamic Convergence (No Fixed Question Count)

None use a fixed number of questions. All converge based on content rather than count:
- **mattpocock:** Convergence = all decision branches resolved; explicit design decision to reject question limits [^20]
- **DDC:** Convergence = demand checklist size → 0; cycle count varies with problem complexity (5–20+ observed) [^18]
- **KB:** Convergence = all phases complete, no open escalations, user confirms [^19]

This matches the academic finding from Holub et al. (arXiv:2601.14798) that dynamic stopping outperforms fixed-step questioning [^59].

### 7.5 Failure as a Discovery Mechanism

All three use failure productively, though with different emphases:
- **mattpocock:** The grilling session surfaces misunderstandings through adversarial probing — wrong answers reveal hidden assumptions [^34]
- **DDC:** RED phase failure is the *explicit* discovery mechanism — the agent's inability to answer IS the signal of what to curate [^35]
- **KB:** Extraction skills flag gaps as escalations — the *absence* of evidence is preserved rather than papered over [^36]

---

## 8. Divergent Design Decisions

### 8.1 Mutation Timing

This is the deepest architectural divergence among the three systems:

**mattpocock (inline):** "When a term is resolved, update CONTEXT.md right there. Don't batch these up" [^25]. The artifact grows organically during the conversation.

**DDC (incremental per-entity):** The `auto-commit.sh` PostToolUse hook fires after **every individual Write or Edit** [^26]. Each entity is committed as its own git commit the moment it is written ("commit early, commit often"). This is the **opposite of atomic/batched** — DDC is maximally incremental with full intermediate state visibility. The "batched" impression comes from the summary confirmation at Step 3's end, but that is a summary statement, not a write event.

**KB (governed):** Questioning is decoupled from wiki writes. Artifacts from grilling sessions feed into a governance pipeline requiring policy review, evidence verification, and lock acquisition before any wiki mutation [^27]. This adds latency but provides audit trails and rollback capability.

### 8.2 Convergence Measurement

**mattpocock (qualitative):** Convergence is judged by the agent, test runner, or user — not measured numerically. For `tdd`, the test runner is the convergence oracle (binary pass/fail), not the agent's checklist [^31].

**DDC (quantitative):** Convergence is measured with per-cycle metrics in YAML frontmatter: `checklist_size`, `confidence_before`, `confidence_after`, `human_score` [^49]. The demo shows a numerical trajectory from 8 gaps to 0 [^18].

**KB (governed/qualitative):** Convergence is defined by phase completion against a skill's declared procedure, plus absence of open escalations.

### 8.3 Who Decides "Done"

| Model | Examples | Trade-off |
|-------|----------|-----------|
| **Test runner owns convergence** | mattpocock `tdd` (test runner produces binary pass/fail) [^31] | Objective, reproducible; limited to executable domains |
| **User owns convergence** (topic-shift) | mattpocock `writing-fragments` (stops when user signals readiness) | Respects user's judgment; risk of incomplete exploration |
| **Human-approved** (unilateral veto) | DDC `ddc-cycle` (agent drives, human scores 1–5, rejection triggers retry, "repeat until accepted") [^32] | Most robust; highest interaction cost. Asymmetric — human has veto with no upper bound |
| **Procedure owns convergence** (step completion) | DDC `ddc-entity` (6 steps), DDC `ddc-status` (single pass) | Predictable; cannot adapt to unexpected complexity |
| **Governed** (orchestrator routes + human steward decides) | KB knowledgebase-orchestrator (HITL is the default per ADR-014; AFK is a small allowlisted set) [^33] | Traceable; highest latency |

### 8.4 Artifact Schema Philosophy

**mattpocock (prose-shaped):** Artifacts formatted by what they represent — CONTEXT.md has Language, Relationships, Example dialogue sections [^47]. No YAML frontmatter on most artifacts.

**DDC (schema-shaped):** Every entity has YAML frontmatter with typed required fields (`type`, `id`, `name`, `description`, `status`, `related_systems`, `implements_capability`, `depends_on`) [^29]. The schema IS the convergence criterion — if all required fields are populated, the entity is complete.

**KB (contract-shaped):** Page template with required frontmatter (`title`, `aliases`, `tags`, `created`, `modified`, `source_refs`, `status`, `open_questions`, `confidence`) governed by `schema/page-template.md` and `schema/metadata-schema-contract.md` [^8]. More formal than mattpocock, comparable to DDC, but applied to wiki pages rather than domain entities.

### 8.5 Enforcement Depth

| Layer | mattpocock | DDC | KB |
|-------|-----------|-----|-----|
| **Skill instructions** | ✅ In SKILL.md | ✅ In SKILL.md | ✅ In SKILL.md |
| **Global rules** | ✅ CLAUDE.md (advisory) | ✅ `.claude/rules/` (glob-scoped, always-on) | ✅ AGENTS.md + copilot-instructions (advisory + hook-enforced) |
| **Pre-write validation** | ❌ | ✅ `validate-entity.sh` + `anonymization-guard.sh` (blocking hooks) | ✅ Pre-commit hooks (frontmatter, CONTEXT.md format, governance locks) |
| **Post-write automation** | ❌ | ✅ `auto-commit.sh` (per-entity commits) | ✅ Contract-bound write surfaces + append-only log |
| **Write-path governance** | ❌ | Partial (hooks enforce format, not content policy) | ✅ ADR-005 lock protocol + write-surface matrix |

---

## 9. Academic Grounding

### 9.1 Agent-Generated Questions Outperform Human Questions (on retrieval metrics)

**AGENT-CQ** (Siro et al., arXiv:2410.19692, **7 citations**): LLM-generated clarifying questions outperform human-generated ones **for retrieval-based metrics** (BM25, cross-encoder) [^60]. The "outperform" finding applies specifically to retrieval effectiveness, not all quality dimensions. This partially validates the mattpocock pattern of having the agent propose its own answer.

### 9.2 Agent Interviews Surface Latent Needs

**Elicitron** (Ataei et al., arXiv:2404.16045, **31 citations**): LLM agents simulating users identify latent needs that humans cannot articulate [^61]. This is the closest academic analog to DDC's approach — the agent's failure to answer reveals needs the human didn't know they had.

### 9.3 Dynamic Stopping Outperforms Fixed-Step

**Holub et al.** (arXiv:2601.14798): Two-agent Socratic protocol comparing fixed-step vs. dynamic stopping. Dynamic stopping produces better outcomes [^59]. All three repos implement dynamic stopping — mattpocock via branch resolution, DDC via checklist depletion, KB via phase completion.

### 9.4 Socratic Questioning (Study Protocol, Not Results)

**Degen** (arXiv:2504.06294): This is a **study protocol** proposing to test whether Socratic questioning triggers System 2 thinking [^62]. The paper uses future tense ("will be") and describes proposed methodology — it has not produced results. The hypothesis that Socratic questioning triggers deliberate reasoning is plausible and maps to grill-me's adversarial format, but it is unproven by this paper.

### 9.5 Clinician Perceptions of AI Questioning (Not "Teaching to Question")

**Held et al.** (Elsevier, 2025): This paper studies clinician **perceptions of a patient-facing AI tool's acceptability** [^63]. It is not about "AI teaching humans to question better" — the finding concerns whether clinicians find AI-generated Socratic questions acceptable for patient use. The "duality" framing (AI questions teach humans what to ask themselves) is plausible as a research hypothesis but is not what this paper demonstrates.

### 9.6 RE Technique Mapping

The following analogies between traditional Requirements Engineering techniques and AI skill patterns are **this report's analytical framework**, not established academic findings. No cited paper makes these specific mappings [^64]:

| Traditional RE Technique | AI Skill Analog | Basis |
|--------------------------|-----------------|-------|
| Structured interviews | `grill-me` / `grill-with-docs` | One-at-a-time, interviewer-driven |
| Contextual inquiry | "Explore the codebase instead" (self-resolution) | Observe before asking |
| Scenario walkthroughs | DDC RED→GREEN cycles | Attempt task, identify gaps |
| Think-aloud protocol | Agent recommends answer first (anchoring) | Externalize reasoning |
| Card sorting | Entity type classification in DDC demand checklist | Category-based organization |

### 9.7 The DDC Academic Paper

**Navakoti & Navakoti** (arXiv:2603.14057): Demand-driven vs. supply-driven knowledge curation. 46 entities curated in 9 cycles (270 minutes). Agent **reuse ratio** improved from 0.0 to 0.75 [^6]. The paper validates that agent failure is a reliable gap signal and that convergence is measurable, but the 20–30 cycle convergence range is an explicit hypothesis, not an empirical finding [^50].

---

## 10. Design Recommendations

Based on the comparative analysis, academic grounding, and feasibility assessment against KB's existing architecture:

### 10.1 Use One-at-a-Time + Recommended Answer for Interactive Exploration (Context-Dependent)

The mattpocock grilling pattern's combination of (a) one question at a time and (b) agent proposes its own answer is highly effective for interactive exploration. However, it is **not a universal best practice** — mattpocock's own repo applies it selectively. Skills focused on synthesis (`to-prd`), triage (`to-issues`), or batch operations may legitimately batch questions or skip solicitation entirely [^42]. Apply this pattern to interactive context-solicitation skills; do not mandate it for all skill types.

### 10.2 Make Failure Legible Before Filling Gaps

DDC's RED phase — attempting to answer with current knowledge and producing a typed gap list — should precede any context solicitation. The agent should first demonstrate what it *doesn't know* and categorize those gaps before asking the human to fill them. This prevents both unfocused questioning and scope creep [^35] [^61].

### 10.3 Track Convergence Numerically

DDC's per-cycle metrics (`checklist_size`, `confidence_before`, `confidence_after`) provide the only objective convergence signal among the three repos. Even a simplified version — counting open gaps per iteration — would improve skills by making progress visible and enabling principled termination decisions [^49]. Note: DDC's demo trajectory is simulated; no ablation study exists comparing quantified vs. qualitative convergence.

### 10.4 Separate Interactive Skills from Extraction Skills

KB's two-family architecture (interactive Q&A vs. read-only extraction) is a clean separation of concerns. Interactive skills should have autopilot guards. Extraction skills should run autonomously and route uncertainty as escalation flags [^52].

### 10.5 Use Typed Gap Categories (with domain translation)

DDC's 6-category demand checklist is more useful than an untyped gap list because each category maps to a specific entity type and creation workflow. For KB, adopting typed gap categories is **schema-compatible** (additive optional field, no ADR required initially) but DDC's specific 6 categories need complete domain translation for Medicare/policy content before being meaningful [^65].

### 10.6 Preserve Uncertainty as a First-Class Artifact

KB **already implements this** through required blocking frontmatter fields (`open_questions`, `confidence` 1–5) and the `## Open Questions` body section — all enforced by deterministic tooling [^51]. DDC's rejection loop (reject → re-answer → re-review) is a complementary **resolution mechanism**, not a preservation mechanism — once the cycle completes, the uncertainty is consumed rather than preserved as a queryable artifact. mattpocock's `grill-me` achieves preservation in the decision log format. No action needed for KB; DDC would benefit from adding durable uncertainty records [^51].

### 10.7 Mutate Artifacts at the Right Frequency

The three mutation frequencies (inline, incremental, governed) suit different contexts:
- **Inline** (update during conversation) — best for single-user, low-stakes documentation like CONTEXT.md [^25]
- **Incremental** (commit per entity) — best for structured artifacts that accumulate over a session, like DDC entities [^26]
- **Governed** (update through a pipeline with policy review) — best for shared knowledge surfaces with audit requirements [^27]

### 10.8 Use Multi-Perspective Gap Scanning

DDC's 5 sub-agent personas demonstrate that different professional perspectives notice different gaps in the same knowledge base. No ablation study exists proving this increases coverage, but the design is logically sound [^7].

### 10.9 Adopt _Avoid_ Lists for Term Disambiguation

mattpocock's CONTEXT-FORMAT.md `_Avoid_` lists (terms to ban) are effective for disambiguation. KB's CONTEXT.md system **already exists and is cross-skill** with 5 scoped files, but uses a deliberately different format enforced by pre-commit hook [^58]. KB's `## Terms` tables define what terms *mean* but contain no "avoid" column or disambiguation lists.

**Feasible adoption path:** The pre-commit hook is permissive of additional sections and table columns — adding an `Avoid` column to `## Terms` or an `## Avoid` section requires **zero hook changes** and fits KB's "additive first" schema evolution rule. This is the clearest low-friction, high-value adoption from mattpocock's format [^65].

### 10.10 Gate ADR Creation with Conjunctive Criteria

mattpocock's three-gate ADR test (hard to reverse AND surprising without context AND result of a real trade-off) prevents ADR proliferation while ensuring important decisions are captured [^45]. This is a normative recommendation — the original report did not demonstrate that KB's 21 ADRs fail this test.

### 10.11 On DDC RED→GREEN as a KB Skill Pattern

The DDC RED→GREEN cycle as an **AFK automation pattern** is **hard-blocked** by ADR-014 [^66]:
- §3: Operator may NEVER override a classification to AFK (deny-by-default)
- §4: Synthesis is not on the exhaustive AFK allowlist
- §6: AFK skips evidence-verifier and policy-arbiter — the review personas the cycle requires

However, the DDC RED→GREEN pattern as a **HITL workflow** already exists in KB's persona pipeline: synthesis draft (RED state) → evidence and policy review (review gate) → re-route on failure. What is blocked is making this cycle fast/automated without human review at each gate [^66].

---

## 11. What Each Repo Could Learn from the Others

### 11.1 What mattpocock/skills Could Adopt

- **From DDC:** Quantified convergence metrics per cycle — even a simple "open gaps remaining" counter would make progress visible in `grill-with-docs` sessions [^49]
- **From DDC:** Entity-typed gap categorization — when `grill-me` surfaces a gap, classifying it (terminology? system? process? data?) would make the gap list more actionable [^12]
- **From KB:** Autopilot guards on interactive skills — mattpocock skills have no protection against running in unattended mode [^52]
- **From DDC:** Pre-write validation hooks — mattpocock has no enforcement beyond advisory CLAUDE.md rules [^5]

### 11.2 What ea-toolkit/ddc Could Adopt

- **From mattpocock:** Agent proposes its own answer during the RED phase — currently DDC's RED phase identifies gaps but doesn't propose what the answer *should* be, missing the anchoring benefit [^11]
- **From mattpocock:** The `_Avoid_` terminology disambiguation pattern — DDC's entity files serve a similar purpose but lack explicit anti-confusion guidance [^47]
- **From KB:** Open question preservation as durable artifacts — when a DDC cycle ends with unresolved gaps, those should become explicit tracked artifacts with `open_questions` and `confidence` fields rather than disappearing between sessions [^51]

### 11.3 What wryenmeek/knowledgebase Could Adopt

- **From mattpocock:** `_Avoid_` lists in CONTEXT.md `## Terms` tables — feasible with zero hook changes; KB currently has no term avoidance/disambiguation [^65]
- **From DDC:** Quantified convergence metrics — KB has no per-cycle numerical tracking of how many gaps remain across an interactive session [^49]
- **From DDC:** Typed gap categories (after domain translation) — KB's `analyze-missed-queries` finds gaps but doesn't classify them by entity type [^65]
- **From mattpocock:** ADR gating with conjunctive criteria — the three-gate test may reduce ADR proliferation [^45]

---

## 12. Confidence Assessment

| Claim | Confidence | Basis |
|-------|-----------|-------|
| KB derived from mattpocock, not convergent | **Very High** | Verbatim "Adapted from" / "Inspired by" lines in 4 SKILL.md files + test suite + ADR-014 [^1] |
| DDC and mattpocock are independently convergent | **High** | Zero cross-references in either direction confirmed by code search [^1] |
| All three use one-at-a-time questioning (with exceptions) | **High** | Verified from primary sources; counter-examples also verified [^42] |
| DDC mutation is incremental, not atomic | **Very High** | `auto-commit.sh` hook + `settings.json` PostToolUse wiring confirmed verbatim [^26] |
| DDC's convergence metrics are the most rigorous | **High** | Verified from cycle log frontmatter and demo trajectory data [^49] |
| KB already has uncertainty preservation | **Very High** | `open_questions` and `confidence` are required blocking fields [^51] |
| KB already has cross-skill CONTEXT.md | **Very High** | 5 scoped files enforced by pre-commit hook [^58] |
| _Avoid_ lists are feasible for KB | **High** | Pre-commit hook confirmed permissive of additions [^65] |
| RED→GREEN as AFK is blocked by ADR-014 | **High** | ADR-014 §3, §4, §6 read directly [^66] |
| Academic papers partially validate patterns | **Medium-High** | Papers fetched and read; citation counts verified; two papers mischaracterized in original report now corrected [^60] [^62] [^63] |
| Multi-perspective gap scanning increases coverage | **Medium** | Logical inference from DDC sub-agent design; no ablation study exists |

---

## Footnotes

[^1]: KB attribution verified by adversarial validation subagent. `search_code("mattpocock repo:wryenmeek/knowledgebase")` returned 8 files. All 4 SKILL.md attribution lines confirmed verbatim. Cross-reference searches (`wryenmeek` in mattpocock, `ea-toolkit` in mattpocock, `mattpocock` in ddc, `wryenmeek` in ddc) all returned 0 results.

[^2]: Citation counts verified via Semantic Scholar API during adversarial validation. Original report inflated all counts.

[^3]: `mattpocock/skills:README.md` — cites Evans (DDD), Beck (XP/TDD), Ousterhout (software design), and Thomas & Hunt (pragmatic programming) for distinct frameworks.

[^4]: `mattpocock/skills:.claude-plugin/plugin.json` lists 13 published skills. `CLAUDE.md` excludes personal/in-progress/deprecated from README and plugin.json. `qa` is in `skills/deprecated/`. `writing-fragments` is in `skills/in-progress/`.

[^5]: DDC infrastructure verified by adversarial validation subagent. All hooks, rules, settings.json, tooling, and copilot-instructions.md fetched and verified. Backend confirmed as FastAPI (not Flask).

[^6]: Navakoti & Navakoti, "Demand-Driven Context," arXiv:2603.14057, 2026. 46 entities in 9 cycles (270 min), reuse ratio 0.0 → 0.75.

[^7]: DDC has 4 skills in `.claude/skills/`: `ddc-cycle`, `ddc-entity`, `ddc-status`, `ddc-demo`. Sub-agents differ in roles, responsibilities, quality standards, and domain tooling — not just navigation starting points.

[^8]: `wryenmeek/knowledgebase:AGENTS.md` — "provenance-first" and "policy-aligned" are verbatim terms.

[^9]: Exact counts from `.github/skills/` and `.github/agents/` directory listings during adversarial validation.

[^10]: KB wiki directories (`wiki/entities/`, `wiki/concepts/`, `wiki/analysis/`) contain only `.gitkeep` files. Confirmed by adversarial validation omissions subagent.

[^11]: `mattpocock/skills:skills/productivity/grill-me/SKILL.md` — "Ask the questions one at a time" (not caps); "For each question, provide YOUR recommended answer."

[^12]: `ea-toolkit/ddc:.claude/skills/ddc-cycle/SKILL.md` Step 2 RED Phase — demand checklist with 6 entity-type categories.

[^13]: `wryenmeek/knowledgebase:.github/skills/context-engineering/SKILL.md` — structured confusion protocols: CONFUSION, MISSING REQUIREMENT, PLAN. ASSUMPTIONS protocol is in `using-agent-skills/SKILL.md`.

[^14]: `mattpocock/skills:skills/engineering/grill-with-docs/SKILL.md` — "If a question can be answered by exploring the codebase, explore the codebase instead."

[^15]: `ea-toolkit/ddc` RED phase instructions — "Do not speculate beyond what the knowledge base contains."

[^16]: `wryenmeek/knowledgebase:.github/skills/record-open-questions/SKILL.md` — "Do not answer the question speculatively just to unblock automation."

[^17]: `mattpocock/skills:skills/productivity/grill-me/SKILL.md` — convergence = all decision branches resolved.

[^18]: DDC demo convergence trajectory over 20 cycles: gaps 8→6→5→4→3→3→3→2→2→1→1→1→0 (13 cycles to zero); stable through cycle 20.

[^19]: KB convergence: all skill phases complete + user confirms + no open escalations in governance pipeline. Note: this formula is this report's analytical synthesis, not a verbatim KB quote.

[^20]: `mattpocock/skills:.out-of-scope/question-limits.md` — explicit design decision to have no question cap.

[^21]: DDC question count is implicitly bounded by problem scope.

[^22]: `wryenmeek/knowledgebase:.github/skills/idea-refine/SKILL.md` — "Generate 5-8 idea variations"; "3-5" refers to sharpening questions, not ideas per round.

[^23]: `ea-toolkit/ddc:.claude/skills/ddc-cycle/SKILL.md` Step 2: "Search domain-knowledge/entities/ for existing knowledge; Attempt to answer the problem using ONLY what exists in the KB."

[^24]: `wryenmeek/knowledgebase:.github/skills/zoom-out/SKILL.md` — "List its direct callers and callees. Map one level of abstraction up and one level down." Maps one module and immediate neighbors, not the entire codebase. Inspired by mattpocock/skills `zoom-out` [^1].

[^25]: `mattpocock/skills:skills/engineering/grill-with-docs/SKILL.md` — "When a term is resolved, update CONTEXT.md right there. Don't batch these up."

[^26]: `ea-toolkit/ddc:.claude/settings.json` PostToolUse hook fires `auto-commit.sh` after every Write/Edit. Each entity individually committed. CLAUDE.md: "A 'logical unit' = one entity added."

[^27]: `wryenmeek/knowledgebase:AGENTS.md` — governed pipeline requires policy review, evidence verification, and lock acquisition before wiki mutation.

[^28]: CONTEXT.md created/updated by `grill-with-docs` and `improve-codebase-architecture`. Other skills reference "domain glossary" generically without explicitly naming CONTEXT.md.

[^29]: `ea-toolkit/ddc:.claude/skills/ddc-entity/SKILL.md` — entity files at `domain-knowledge/entities/<type>/<kebab-case-id>.md` with YAML frontmatter.

[^30]: KB output artifacts: decision logs from `grill-me`, open questions from `record-open-questions`, extraction bundles from `extract-entities-and-claims`.

[^31]: For `tdd`, the test runner owns convergence (binary pass/fail), not the agent's checklist. User approval is also required for the initial plan.

[^32]: `ea-toolkit/ddc:.claude/skills/ddc-cycle/SKILL.md` Step 5 — human has unilateral veto with no upper bound: "Repeat until accepted." Asymmetric — closer to "human-approved" than symmetric "co-owned."

[^33]: KB orchestrator routes and blocks; validation is performed by downstream `evidence-verifier` and `policy-arbiter`. HITL is the default per ADR-014; AFK is a small exhaustive allowlist.

[^34]: mattpocock grilling — wrong answers during adversarial probing reveal hidden assumptions.

[^35]: DDC RED phase — the agent's inability to answer IS the signal of what to curate.

[^36]: KB extraction skills route gaps as escalation flags — `analyze-missed-queries` identifies coverage gaps, `record-open-questions` preserves them.

[^37]: mattpocock description field routing — no routing config in CLAUDE.md or settings.json; description field is the only mechanism. CLAUDE.md contains global rules but not routing configuration.

[^38]: `ddc-cycle` Steps 0–6 are inline workflow steps within a single SKILL.md. It does NOT invoke `ddc-entity`, `ddc-status`, or `ddc-demo` as sub-skills. Those are independent peer skills. DDC uses the same description-trigger mechanism as mattpocock.

[^39]: KB hybrid routing — description triggers in SKILL.md frontmatter + `knowledgebase-orchestrator` lane routing for governed work. Three routing categories (Direct, Persona, Both) documented in `using-agent-skills/SKILL.md`.

[^40]: Grilling pattern in 4 skills: `grill-me`, `grill-with-docs`, `improve-codebase-architecture` (embeds grill-with-docs), `writing-fragments` (adapted for creative excavation).

[^41]: `diagnose` SKILL.md full text searched — zero matches for "one question at a time," "recommended answer," or "interview." Confirmed by adversarial validation subagent.

[^42]: Counter-examples verified by adversarial validation subagent: `to-issues/SKILL.md` Step 4 batches 4 questions simultaneously; `to-prd/SKILL.md` opens with "Do NOT interview the user"; `setup-matt-pocock-skills/SKILL.md` Step 2 mandates "one at a time" for 3 configuration decisions and warns "Don't dump all three at once."

[^43]: `grill-me` and `write-a-skill` are in `skills/productivity/`, not `skills/engineering/`.

[^44]: `mattpocock/skills:skills/engineering/grill-with-docs/SKILL.md` "During the session" section — four challenge triggers.

[^45]: `mattpocock/skills:skills/engineering/grill-with-docs/SKILL.md` — ADR offered only when: (1) Hard to reverse AND (2) Surprising without context AND (3) Result of a real trade-off. "all three are true" and "if any of the three is missing, skip."

[^46]: `mattpocock/skills:skills/in-progress/writing-fragments/SKILL.md` — in-progress/unpublished. Agent stops when user signals readiness (handoff constraint).

[^47]: `mattpocock/skills:CONTEXT-FORMAT.md` — Language (term + definition + Avoid), Relationships, Example dialogue, Flagged ambiguities.

[^48]: TDD/DDC comparison verified against `ea-toolkit/ddc:METHODOLOGY.md` (careful wording: "Engineers will recognize this structure"), `mattpocock/skills:skills/engineering/tdd/SKILL.md` (test runner produces binary pass/fail), and `ddc-cycle/SKILL.md` (human scores 1-5).

[^49]: DDC cycle log frontmatter metrics: `entities_created`, `entities_updated`, `entities_reused`, `confidence_before`, `confidence_after`, `human_score`, `checklist_size`.

[^50]: DDC paper (arXiv:2603.14057) presents 9 cycles as illustration; 20–30 cycle convergence is explicitly "a hypothesis."

[^51]: KB uncertainty preservation: `open_questions` (required blocking frontmatter), `confidence` 1–5 (required blocking), `## Open Questions` body section — all enforced by deterministic tooling. Verified from `schema/metadata-schema-contract.md` and `schema/page-template.md`.

[^52]: KB two-family architecture: interactive Q&A (grill-me, idea-refine, context-engineering) vs. extraction/preservation (zoom-out, analyze-missed-queries, record-open-questions, claim-inventory, extract-entities-and-claims, using-agent-skills). Interactive skills have autopilot guards.

[^53]: `wryenmeek/knowledgebase:.github/skills/analyze-missed-queries/SKILL.md` — scans wiki pages for coverage gaps.

[^54]: `wryenmeek/knowledgebase:.github/skills/claim-inventory/SKILL.md` — enumerates factual claims from source intake.

[^55]: `wryenmeek/knowledgebase:.github/skills/extract-entities-and-claims/SKILL.md` — extracts candidate entities, concepts, claims, and chronology.

[^56]: `wryenmeek/knowledgebase:.github/skills/using-agent-skills/SKILL.md` — meta-skill for skill selection guidance.

[^57]: `wryenmeek/knowledgebase:.github/skills/context-engineering/logic/context_import_contract.py` — typed import contract with allowlisted paths, max 12 imports, path traversal protection.

[^58]: KB CONTEXT.md enforced by `scripts/hooks/check_context_md_format.py` with `REQUIRED_SECTIONS = ("## Terms", "## Invariants", "## File Roles")`. Case-sensitive, blocking. 5 scoped CONTEXT.md files confirmed. Hook is permissive of additional sections — checks required ones exist, does not reject extras.

[^59]: Holub et al., "Two-Agent Socratic Protocol," arXiv:2601.14798, 2026 — dynamic stopping outperforms fixed-step.

[^60]: Siro et al., "AGENT-CQ," arXiv:2410.19692, 2024, **7 citations** — LLM-generated clarifying questions outperform human-generated ones on retrieval-based metrics (BM25, cross-encoder), not all quality dimensions.

[^61]: Ataei et al., "Elicitron," arXiv:2404.16045, 2024, **31 citations** — LLM agent interviews identify latent needs.

[^62]: Degen, "Resurrecting Socrates," arXiv:2504.06294, 2025 — **study protocol**, not completed research. Uses future tense; describes proposed methodology, not results.

[^63]: Held et al., "Clinician Perceptions of Socrates 2.0," Cognitive and Behavioral Practice, Elsevier, 2025 — studies clinician perceptions of patient-facing AI tool acceptability, not "AI teaching humans to question better."

[^64]: RE technique mapping is this report's analytical framework. No cited paper makes these specific mappings.

[^65]: Feasibility verified by adversarial validation subagent. KB schema allows additive optional fields; pre-commit hook permits additional CONTEXT.md sections and table columns. DDC's 6 gap categories need Medicare/policy domain translation. `_Avoid_` lists require zero hook changes.

[^66]: ADR-014 §3 (operator cannot override to AFK), §4 (synthesis not on exhaustive allowlist), §6 (AFK skips evidence-verifier and policy-arbiter). HITL equivalent of RED→GREEN already exists in persona pipeline.
