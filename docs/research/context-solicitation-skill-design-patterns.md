# Context-Solicitation Skill Design Patterns: A Three-Repository Comparative Analysis

> ⚠️ **Superseded.** The convergence thesis in this document is disputed by the adversarial review. See [Final Synthesis: Context-Solicitation Skill Design Patterns](./context-solicitation-final-synthesis.md) for corrected findings. The original is preserved for provenance.

**Scope:** How `mattpocock/skills`, `ea-toolkit/ddc`, and `wryenmeek/knowledgebase` approach the problem of designing AI agent skills that effectively solicit, validate, and preserve context from human collaborators.

**Method:** 7 research subagent dispatches across 2 waves, covering: repo structure and philosophy (mattpocock), demand-driven checklist patterns (DDC), KB interactive and extraction skills, grill-with-docs deep dive, cross-skill structural comparison, academic literature survey, and KB context-engineering logic analysis.

---

## Executive Summary

Three open-source repositories have independently converged on a shared insight: **the most effective way for an AI agent to acquire context is to fail deliberately, make its ignorance legible, and then ask precisely targeted questions one at a time.** They diverge sharply on *how* questions are formatted, *when* artifacts are mutated, and *who decides when the conversation is done.* mattpocock/skills contributes the "grilling" pattern — one question at a time with a recommended answer, converging when all decision branches resolve. ea-toolkit/ddc contributes the "demand checklist" pattern — entity-typed gap analysis driven by intentional failure, converging when checklist size reaches zero. wryenmeek/knowledgebase contributes the "governed uncertainty" pattern — structured confusion protocols with escalation-first design, preserving gaps as first-class artifacts rather than resolving them. Academic research independently validates all three: AGENT-CQ (arXiv:2410.19692) shows AI-generated clarifying questions outperform human-generated ones; Elicitron (arXiv:2404.16045, 75 citations) demonstrates that agent-simulated interviews surface latent needs humans cannot articulate; and Holub et al. (arXiv:2601.14798) find that dynamic stopping outperforms fixed-step questioning — precisely the convergence model all three repos implement.

---

## 1. Three-Repository Overview

### 1.1 mattpocock/skills

**Repository:** `github.com/mattpocock/skills` (SHA ref: `70141119`)
**Platform:** Claude Code slash commands
**Philosophy:** Anti-vibe-coding, DDD-influenced (Evans, Beck, Ousterhout) [^1]
**Scale:** 27 skills across 6 buckets (10 engineering, 3 productivity, 4 misc, 2 personal, 4 in-progress, 4 deprecated) [^2]
**Core innovation:** The "grilling" interaction pattern — relentless one-at-a-time questioning with agent-proposed answers, producing CONTEXT.md as the cornerstone cross-skill artifact.

### 1.2 ea-toolkit/ddc

**Repository:** `github.com/ea-toolkit/ddc` (SHA ref: `b8673f18`)
**Platform:** Claude Code with Task sub-agent orchestration
**Philosophy:** Demand-driven knowledge curation — curate only what a problem actually demands [^3]
**Scale:** 5 skills (ddc-cycle orchestrator, ddc-entity, ddc-status, ddc-demo, plus sub-agent configurations for ta/po/se/da/sa roles) [^4]
**Core innovation:** The RED→GREEN cycle — intentional failure as a discovery mechanism, producing entity-typed knowledge artifacts with quantified convergence metrics.

### 1.3 wryenmeek/knowledgebase

**Repository:** `github.com/wryenmeek/knowledgebase`
**Platform:** GitHub Copilot CLI with custom agent personas
**Philosophy:** Provenance-first, policy-aligned, governed uncertainty [^5]
**Scale:** 80+ skills, 15+ agent personas [^6]
**Core innovation:** Structured confusion protocols and escalation-first design — uncertainty is preserved as a first-class artifact rather than resolved by guessing.

---

## 2. Comparison Matrix

| Dimension | mattpocock/skills | ea-toolkit/ddc | wryenmeek/knowledgebase |
|-----------|------------------|----------------|------------------------|
| **Question format** | One at a time + agent recommends an answer [^7] | 6-category demand checklist mapped to entity types [^8] | Structured confusion/missing/assumption protocols [^9] |
| **Anti-hallucination rule** | "Explore the codebase instead" [^10] | "Do not speculate beyond what the knowledge base contains" [^11] | "Do not answer speculatively just to unblock automation" [^12] |
| **Convergence model** | All decision branches resolved (qualitative) [^13] | Checklist size → 0 (quantitative) [^14] | All phases complete + user confirms + no open escalations [^15] |
| **Question cap** | Explicitly none — design decision documented in `.out-of-scope/question-limits.md` [^16] | Implicit — bounded by problem scope [^17] | Phase-gated (e.g., 3–5 per round in idea-refine) [^18] |
| **Self-resolution before asking** | Yes — "If a question can be answered by exploring the codebase, explore instead" [^10] | Partial — RED phase searches KB entities first [^19] | Yes — zoom-out reads entire codebase before surfacing gaps [^20] |
| **Artifact mutation timing** | Inline during conversation — "Don't batch these up" [^21] | Batched and atomic — all GREEN phase steps complete before confirmation [^22] | Governed pipeline — questioning is decoupled from wiki writes [^23] |
| **Primary output artifact** | CONTEXT.md + optional ADRs [^24] | Entity files in `domain-knowledge/entities/<type>/` + cycle logs [^25] | Decision logs + open questions + extraction bundles [^26] |
| **Convergence ownership** | Varies: agent (diagnose/tdd checklist), user (writing-fragments), or implicit (improve-architecture) [^27] | Agent + human co-owned — agent declares done, human scores 1–5, rejection triggers retry [^28] | Governed — orchestrator validates all prerequisites before declaring complete [^29] |
| **Failure as signal** | Implicit — incorrect answers during grilling surface misunderstandings [^30] | Explicit and central — RED phase failure IS the discovery mechanism [^31] | Implicit — extraction skills route gaps as escalation flags [^32] |
| **Skill routing** | Ambient — agent reads natural language and selects via `description` field [^33] | Explicit — user invokes slash commands; `ddc-cycle` orchestrates sub-skills [^34] | Hybrid — `description` triggers + `knowledgebase-orchestrator` lane routing [^35] |

---

## 3. The Grilling Pattern (mattpocock/skills)

### 3.1 Core Mechanism

The grilling pattern appears in 5 mattpocock skills (`grill-me`, `grill-with-docs`, `improve-codebase-architecture`, `writing-fragments`, `diagnose`) with a consistent structural signature [^36]:

1. **One question at a time** — never batch. Each question must be answered before the next is asked.
2. **Agent proposes its own answer** — anchoring the conversation, reducing blank-screen cognitive load, and forcing the human to *react* rather than *generate*.
3. **Self-resolution before human query** — "If a question can be answered by exploring the codebase, explore the codebase instead" [^10].
4. **Walk each branch of the decision tree** — resolving dependencies one-by-one until all branches converge.

### 3.2 Variants

The grilling pattern has distinct specializations:

**`grill-me` (base):** Pure adversarial questioning. No persistent artifact mutation during the session. Output is a decision log of Q&A pairs [^7].

**`grill-with-docs` (domain-aware):** Extends `grill-me` by reading existing CONTEXT.md and ADR files before questioning. Adds four challenge triggers in priority order [^37]:
1. **Glossary conflict** — term user said ≠ CONTEXT.md definition (highest priority)
2. **Fuzzy/overloaded language** — term has multiple possible referents
3. **Scenario stress-test** — edge cases that probe concept boundaries
4. **Code contradiction** — user's stated claim ≠ what code actually does

Uniquely, `grill-with-docs` mutates CONTEXT.md *inline during the conversation* — "When a term is resolved, update CONTEXT.md right there. Don't batch these up" [^21]. This makes the grilling session a *live editing session* of the domain model.

**ADR gating in `grill-with-docs`:** ADRs are offered only when all three conjunctive gates pass [^38]:
1. Hard to reverse (cost of changing your mind is meaningful)
2. Surprising without context (future reader would wonder "why?")
3. Result of a real trade-off (genuine alternatives existed)

If any single gate fails, no ADR is created. The word "sparingly" appears in the SKILL.md header for ADRs [^38].

**`writing-fragments` (creative):** Adapts the grilling pattern for idea mining. Questions are excavation probes rather than adversarial challenges [^39]:
- "You said X — say it three different ways"
- "What's the version of that you wouldn't say in public?"
- "What's the example that made you believe this in the first place?"

Convergence is externally owned — the agent is explicitly forbidden from declaring the session complete. The session ends only when the user pivots to structure ("We're still mining. Structure comes later.") [^39].

### 3.3 The CONTEXT.md Artifact

CONTEXT.md is the cornerstone cross-skill artifact in mattpocock/skills — created/updated by `grill-with-docs` and `improve-codebase-architecture`, consumed by `diagnose`, `tdd`, `to-issues`, `to-prd`, and `zoom-out` [^24]. Its format is prescribed by CONTEXT-FORMAT.md [^40]:

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

Key design rule: "Don't couple CONTEXT.md to implementation details. Only include terms that are meaningful to domain experts" [^40].

---

## 4. The Demand Checklist Pattern (ea-toolkit/ddc)

### 4.1 Core Mechanism

DDC's demand checklist pattern is structurally analogous to TDD's RED→GREEN cycle — and this analogy is precise, not metaphorical [^41]:

| Phase | TDD | DDC |
|-------|-----|-----|
| **RED** | Write a failing test — a deliberate assertion of what is not yet true | Attempt to answer using only existing KB → produce demand checklist of gaps |
| **GREEN** | Write minimal code to make the test pass | Curate entity files to fill the demand checklist gaps |
| **Validation** | Per-cycle 5-item checklist | Human scores 1–5; rejection triggers re-entry |

Both treat **intentional failure as an epistemic instrument** — the RED state is more valuable than skipping to implementation because it makes gaps legible [^41].

### 4.2 Demand Checklist Structure

The RED phase produces a demand checklist categorized into 6 entity-type categories [^8]:

1. **Terminology needed** → `jargon-business` or `jargon-tech`
2. **Systems/platforms needed** → `systems`, `platforms`
3. **Processes/events needed** → `processes`, `business-events`
4. **Data structures needed** → `data-models`, `data-products`
5. **Business logic needed** → `capabilities`, `offerings`
6. **People/teams needed** → `teams`, `personas`

Each checklist item maps to an entity type, creating a typed pipeline from "what I don't know" to "what I need to create."

### 4.3 RED Phase Detection Algorithm

The precise algorithm from `ddc-cycle` SKILL.md [^19]:

1. Search `domain-knowledge/entities/` for problem-related terms
2. Read matching entity files and assess coverage
3. Attempt to answer the problem using ONLY existing KB content
4. For each gap: categorize by entity type → add to demand checklist
5. Rate confidence 1–5 and explain what's missing
6. Ask: "Should I proceed with curation? Point me to a source document, answer directly, or both."

### 4.4 Quantified Convergence

DDC provides the most rigorous convergence metrics of all three repos. Per-cycle frontmatter tracks: `entities_created`, `entities_updated`, `entities_reused`, `confidence_before`, `confidence_after`, `human_score`, `checklist_size` [^42].

The `ddc-demo` example shows a complete convergence trajectory over 20 cycles [^14]:
- Gaps: 8→6→5→4→3→3→3→2→2→1→1→1→0
- At cycle 20: zero gaps, 6 entities reused, 0 new entities created = full convergence

This is the only system of the three that provides *quantitative* evidence of convergence rather than relying on qualitative judgment.

### 4.5 Sub-Agent Role Differentiation

DDC's 5 sub-agent personas (ta/po/se/da/sa) share the same demand checklist format but differ in navigation starting points [^4]:
- **ta-agent** (Technical Architect) → starts from systems/sequences
- **po-agent** (Product Owner) → starts from capabilities/personas
- **se-agent** (Software Engineer) → starts from data-models/APIs
- **da-agent** (Data Analyst) → starts from data-products/data-models
- **sa-agent** (Solutions Architect) → starts from platforms/integrations

This creates a multi-perspective gap scanner — each agent reads the same KB but *notices different gaps* based on its professional lens.

---

## 5. The Governed Uncertainty Pattern (wryenmeek/knowledgebase)

### 5.1 Core Mechanism

KB's distinctive contribution is treating uncertainty as a first-class artifact rather than something to be resolved immediately. The architectural invariant across all KB skills: **"Preserve uncertainty, don't guess it away"** [^12]. Strongest expression in `record-open-questions`: "Do not answer the question speculatively just to unblock automation" [^12].

### 5.2 Structured Confusion Protocols

The `context-engineering` skill defines typed protocols for different kinds of uncertainty [^9]:

```
CONFUSION: [conflict] → Options A/B/C → "Which approach?"
MISSING REQUIREMENT: [gap] → Options A/B/C → "Which behavior?"
PLAN: [steps] → "Executing unless you redirect"
ASSUMPTIONS: [list] → "Correct me now or I'll proceed"
```

Each protocol type generates a different downstream action — confusion escalates, missing requirements block, plans proceed with opt-out, assumptions proceed with a correction window. This is more fine-grained than either mattpocock's single-question format or DDC's categorized checklist.

### 5.3 Two-Family Architecture

KB separates context-solicitation into two skill families [^43]:

**Interactive Q&A skills** (require live human):
- `grill-me` — adversarial stress-testing with autopilot guard [^44]
- `idea-refine` — iterative divergent/convergent thinking with autopilot guard [^18]
- `context-engineering` — structured confusion protocols [^9]

**Extraction/Preservation skills** (read-only, deterministic, no human input):
- `zoom-out` — reads entire codebase structure [^20]
- `analyze-missed-queries` — scans wiki for coverage gaps [^45]
- `record-open-questions` — preserves uncertainty as structured artifacts [^12]
- `claim-inventory` — enumerates factual claims from sources [^46]
- `extract-entities-and-claims` — extracts candidate entities and chronology [^47]
- `using-agent-skills` — meta-skill for skill selection guidance [^48]

The critical design decision: **extraction skills never guess**. They route uncertainty as escalation flags to the governance pipeline rather than filling in blanks. This separation means the system can operate in AFK mode for extraction while reserving interactive skills for when a human is present.

### 5.4 Context-Engineering Logic (Python)

KB's context-engineering skill includes a typed contract system in Python [^49]:

- `context_import_contract.py`: Allowlisted read paths, max 12 imports, path traversal protection, duplicate detection
- `normalize_context_imports.py`: Deterministic normalization of import manifests
- `validate_context_imports.py`: Validation producing structured `ContextImportValidationResult` with reason codes

This is infrastructure that neither mattpocock nor DDC have — a programmatic enforcement layer for context boundaries, not just skill-level instructions.

---

## 6. Shared Design Principles

All three repositories independently converge on five principles:

### 6.1 One-at-a-Time Questioning

All three explicitly reject question batching:
- mattpocock: "Ask the questions one at a time, waiting for feedback on each question before continuing" [^7]
- DDC: Each demand checklist item is resolved individually through RED→GREEN; sub-agents process one entity at a time [^8]
- KB: `grill-me` inherits the one-at-a-time pattern; `idea-refine` evaluates ideas one per round [^18]

### 6.2 Anti-Hallucination as Architecture

All three embed anti-hallucination as a structural constraint, not just a prompt instruction:
- mattpocock: "If a question can be answered by exploring the codebase, explore the codebase instead" — prefer verified fact over generated answer [^10]
- DDC: "Do not speculate beyond what the knowledge base contains" — KB entities are the only permitted evidence [^11]
- KB: "Do not answer the question speculatively just to unblock automation" — uncertainty is preserved rather than filled [^12]

### 6.3 Self-Resolution Before Human Query

All three attempt automated resolution before asking the human:
- mattpocock: Codebase exploration as a prerequisite to questioning [^10]
- DDC: RED phase searches existing entities before producing the demand checklist [^19]
- KB: `zoom-out` reads the entire codebase structure; extraction skills process sources autonomously [^20]

### 6.4 Dynamic Convergence (No Fixed Question Count)

None of the three repos use a fixed number of questions. All converge based on content rather than count:
- mattpocock: Convergence = all decision branches resolved; explicit design decision to reject question limits [^16]
- DDC: Convergence = demand checklist size → 0; cycle count varies with problem complexity (5–20+ observed) [^14]
- KB: Convergence = all phases complete, no open escalations, user confirms [^15]

This matches the academic finding from Holub et al. (arXiv:2601.14798) that dynamic stopping outperforms fixed-step questioning [^50].

### 6.5 Failure as a Discovery Mechanism

All three use failure productively, though with different emphases:
- mattpocock: The grilling session surfaces misunderstandings through adversarial probing — wrong answers reveal hidden assumptions [^30]
- DDC: RED phase failure is the *explicit* discovery mechanism — the agent's inability to answer IS the signal of what to curate [^31]
- KB: Extraction skills flag gaps as escalations — the *absence* of evidence is preserved rather than papered over [^32]

---

## 7. Divergent Design Decisions

### 7.1 Inline vs. Deferred vs. Governed Mutation

This is the deepest architectural divergence among the three systems:

**mattpocock (inline):** "When a term is resolved, update CONTEXT.md right there. Don't batch these up" [^21]. The artifact grows organically during the conversation. The user can edit the file between turns and the agent will re-read before writing [^39].

**DDC (batched/atomic):** All GREEN phase entity creation steps execute to completion before confirmation is shown. The user cannot observe intermediate state [^22]. Entity files are schema-validated (YAML frontmatter with typed required fields).

**KB (governed):** Questioning is decoupled from wiki writes. Artifacts from grilling sessions (decision logs, open questions) feed into a governance pipeline that requires policy review, evidence verification, and lock acquisition before any wiki mutation occurs [^23]. This adds latency but provides audit trails and rollback capability.

**Design implication:** Inline mutation is fastest for single-user codebase documentation. Batched mutation is best when artifact consistency matters more than speed. Governed mutation is required when multiple agents or users share the same knowledge surface and changes must be traceable.

### 7.2 Convergence Measurement

**mattpocock (qualitative):** Convergence is judged by the agent or user, not measured. The `improve-codebase-architecture` skill has no explicit termination condition — "decisions crystallize" implicitly [^27]. `writing-fragments` terminates only when the user shifts to asking about structure [^39].

**DDC (quantitative):** Convergence is measured with per-cycle metrics in YAML frontmatter: `checklist_size`, `confidence_before`, `confidence_after`, `human_score` [^42]. The demo shows a numerical trajectory from 8 gaps to 0 [^14].

**KB (governed/qualitative):** Convergence is defined by phase completion against a skill's declared procedure, plus absence of open escalations. No numerical metrics comparable to DDC's.

**Design implication:** DDC's quantitative convergence metrics are the most rigorous. Adopting even a simplified version (tracking "open gaps" count per cycle) would benefit both mattpocock and KB skills.

### 7.3 Who Decides "Done"

Three distinct ownership models [^27]:

| Model | Examples | Trade-off |
|-------|----------|-----------|
| **Agent owns convergence** (checklist) | mattpocock `diagnose` (5-item checklist), `tdd` (5-item checklist) | Consistent quality; risk of premature termination |
| **User owns convergence** (topic-shift) | mattpocock `writing-fragments`, `improve-codebase-architecture` | Respects user's judgment; risk of incomplete exploration |
| **Procedure owns convergence** (step completion) | DDC `ddc-entity` (6 steps), DDC `ddc-status` (single pass) | Predictable; cannot adapt to unexpected complexity |
| **Co-owned** (agent + human scoring) | DDC `ddc-cycle` (agent declares + human scores 1–5 + rejection loop) | Most robust; highest interaction cost |
| **Governed** (orchestrator validates) | KB knowledgebase-orchestrator | Traceable; highest latency |

### 7.4 Artifact Schema Philosophy

**mattpocock (prose-shaped):** Artifacts are formatted based on what they represent — CONTEXT.md has a Language section with term definitions, Relationships section, Example dialogue section [^40]. No YAML frontmatter on most artifacts.

**DDC (schema-shaped):** Every entity has YAML frontmatter with typed required fields (`type`, `id`, `name`, `description`, `status`, `related_systems`, `implements_capability`, `depends_on`) [^25]. The schema IS the convergence criterion — if all required fields are populated, the entity is complete.

**KB (contract-shaped):** Page template with required frontmatter (`title`, `aliases`, `tags`, `created`, `modified`, `source_refs`, `status`) governed by `schema/page-template.md` and `schema/metadata-schema-contract.md` [^5]. More formal than mattpocock, comparable to DDC, but applied to wiki pages rather than domain entities.

---

## 8. Academic Grounding

### 8.1 Agent-Generated Questions Outperform Human Questions

**AGENT-CQ** (Siro et al., arXiv:2410.19692, 10 citations): LLM-generated clarifying questions outperform human-generated ones for retrieval effectiveness [^51]. This validates the mattpocock pattern of having the agent propose its own answer — the agent's framing of the question is often better than what a human would ask unprompted.

### 8.2 Agent Interviews Surface Latent Needs

**Elicitron** (Ataei et al., arXiv:2404.16045, 75 citations): LLM agents simulating users identify latent needs that humans cannot articulate [^52]. This is the closest academic analog to DDC's approach — the agent's failure to answer reveals needs the human didn't know they had. DDC operationalizes this insight by making failure the *entry point* of every cycle.

### 8.3 Dynamic Stopping Outperforms Fixed-Step

**Holub et al.** (arXiv:2601.14798): Two-agent Socratic protocol comparing fixed-step vs. dynamic stopping. Dynamic stopping produces better outcomes [^50]. All three repos implement dynamic stopping — mattpocock via branch resolution, DDC via checklist depletion, KB via phase completion. None use fixed question counts.

### 8.4 Socratic Questioning as System 2 Trigger

**Degen** (arXiv:2504.06294, 13 citations): Socratic questioning triggers System 2 thinking (slow, deliberate reasoning) vs. System 1 (fast, automatic) [^53]. This maps directly to `grill-me`'s "relentlessly interview" instruction — the adversarial format forces the human out of fast-acceptance mode and into deliberate consideration.

**Held et al.** (Elsevier, 2025): Clinicians used AI-generated Socratic questions not just for dialogue but to *improve their own questioning ability* — a "duality" where AI questions teach humans what to ask themselves [^54]. The `grill-me` skill could serve this same dual purpose.

### 8.5 Traditional RE Technique Mapping

The academic literature on Requirements Engineering maps cleanly to these skill patterns [^55]:

| Traditional RE Technique | AI Skill Equivalent |
|--------------------------|-------------------|
| Structured interviews | `grill-me` / `grill-with-docs` |
| Contextual inquiry | "Explore the codebase instead" (self-resolution) |
| Scenario walkthroughs | DDC RED→GREEN cycles |
| Think-aloud protocol | Agent recommends answer first (anchoring) |
| Card sorting | Entity type classification in DDC demand checklist |

### 8.6 The DDC Academic Paper

**Navakoti & Navakoti** (arXiv:2603.14057): Demand-driven vs. supply-driven knowledge curation. 46 entities curated in 9 cycles (270 minutes). Agent success rate improved from 0.0 to 0.75 [^3]. The paper validates that agent failure is a reliable gap signal and that convergence is measurable, but the claimed 20–30 cycle convergence range is not fully empirically demonstrated (only 9 cycles shown reaching 0.75, not 1.0) [^56].

---

## 9. Design Recommendations

Based on the comparative analysis and academic grounding, these principles emerge for designing more effective context-solicitation skills:

### 9.1 Adopt One-at-a-Time + Recommended Answer as the Default

The mattpocock grilling pattern's combination of (a) one question at a time and (b) agent proposes its own answer is the single most impactful design decision across all three repos. It reduces cognitive load, anchors the conversation, and forces the human to react rather than generate from scratch. Every context-solicitation skill should default to this pattern unless there is a specific reason to deviate [^7] [^51].

### 9.2 Make Failure Legible Before Filling Gaps

DDC's RED phase — attempting to answer with current knowledge and producing a typed gap list — should precede any context solicitation. The agent should first demonstrate what it *doesn't know* and categorize those gaps before asking the human to fill them. This prevents both unfocused questioning and scope creep [^31] [^52].

### 9.3 Track Convergence Numerically

DDC's per-cycle metrics (`checklist_size`, `confidence_before`, `confidence_after`) provide the only objective convergence signal among the three repos. Even a simplified version — counting open gaps per iteration — would improve mattpocock and KB skills by making progress visible and enabling principled termination decisions [^42].

### 9.4 Separate Interactive Skills from Extraction Skills

KB's two-family architecture (interactive Q&A vs. read-only extraction) is a clean separation of concerns. Interactive skills should have autopilot guards. Extraction skills should run autonomously and route uncertainty as escalation flags. This enables AFK operation for deterministic work while preserving human judgment for ambiguous decisions [^43] [^44].

### 9.5 Use Typed Gap Categories

DDC's 6-category demand checklist (terminology, systems, processes, data, business logic, people) is more useful than an untyped gap list because each category maps to a specific entity type and creation workflow. When building context-solicitation skills for specialized domains, define typed gap categories that map to the domain's artifact types [^8].

### 9.6 Preserve Uncertainty as a First-Class Artifact

KB's `record-open-questions` skill treats unresolved uncertainty as a structured artifact rather than a bug to be fixed. When a human answers "I don't know," that should become an explicit open question — not a silent assumption. mattpocock's `grill-me` achieves this in the decision log format ("I don't know" becomes an open question in the spec) [^12] [^7]. DDC would benefit from formalizing this — currently, rejected answers trigger retries rather than preserving the uncertainty [^28].

### 9.7 Mutate Artifacts at the Right Frequency

The three mutation frequencies (inline, batched, governed) suit different contexts:
- **Inline** (update during conversation) — best for single-user, low-stakes documentation like CONTEXT.md [^21]
- **Batched** (update atomically after completion) — best for structured artifacts that must be internally consistent, like DDC entities [^22]
- **Governed** (update through a pipeline with policy review) — best for shared knowledge surfaces with audit requirements [^23]

A skill should declare its mutation frequency explicitly rather than defaulting to the most complex option.

### 9.8 Use Multi-Perspective Gap Scanning

DDC's 5 sub-agent personas (ta/po/se/da/sa) demonstrate that different professional perspectives notice different gaps in the same knowledge base. When designing context-solicitation for complex domains, use multiple specialized perspectives to increase gap detection coverage [^4].

### 9.9 Design CONTEXT.md as a Cross-Skill Artifact

mattpocock's CONTEXT.md (with Language, Relationships, Example dialogue, and Flagged ambiguities sections) is the most carefully designed persistent context artifact across all three repos. Its "Avoid" lists (terms to ban) are particularly effective for disambiguation. Any multi-skill system should have a canonical context artifact with a prescribed format that multiple skills both read and write [^40].

### 9.10 Gate ADR Creation with Conjunctive Criteria

mattpocock's three-gate ADR test (hard to reverse AND surprising without context AND result of a real trade-off) prevents ADR proliferation while ensuring important decisions are captured. This is more principled than KB's approach of writing ADRs whenever a design decision is made, and more structured than DDC's approach of not having explicit ADR machinery [^38].

---

## 10. Confidence Assessment

| Claim | Confidence | Basis |
|-------|-----------|-------|
| All three repos use one-at-a-time questioning | **High** | Verified from SKILL.md sources across all three repos |
| Anti-hallucination is structural across all three | **High** | Exact quotes from all three repos' skill files |
| DDC's convergence metrics are the most rigorous | **High** | Verified from cycle log frontmatter and demo trajectory data |
| mattpocock's CONTEXT.md is a cross-skill artifact | **High** | File references verified across 5+ consuming skills |
| KB has 80+ skills and 15+ agent personas | **Medium** | Count from prior adversarial review; exact counts may vary with current repo state |
| Academic papers validate all three patterns | **Medium-High** | Papers fetched and read; relevance mapping is interpretive |
| "Agent proposes answer" has no direct academic analog | **Medium** | Extensive search found only indirect parallels (Holub et al. Student-Teacher model) |
| DDC's 20–30 cycle convergence claim is unvalidated | **High** | Paper shows only 9 cycles reaching 0.75 success rate; demo shows 13 to zero gaps, 20 to stable |
| Inline mutation suits single-user contexts | **Medium** | Inference from design trade-offs; no empirical comparison conducted |
| Multi-perspective gap scanning increases coverage | **Medium** | Logical inference from DDC sub-agent design; no ablation study |

---

## 11. What Each Repo Could Learn from the Others

### 11.1 What mattpocock/skills Could Adopt

- **From DDC:** Quantified convergence metrics per cycle — even a simple "open gaps remaining" counter would make progress visible in `grill-with-docs` sessions [^42]
- **From DDC:** Entity-typed gap categorization — when `grill-me` surfaces a gap, classifying it (terminology? system? process? data?) would make the gap list more actionable [^8]
- **From KB:** Autopilot guards on interactive skills — mattpocock skills have no protection against running in unattended mode where answers can't be provided [^44]
- **From KB:** Structured confusion protocols — the `CONFUSION / MISSING REQUIREMENT / PLAN / ASSUMPTIONS` taxonomy is more precise than mattpocock's single undifferentiated question format [^9]

### 11.2 What ea-toolkit/ddc Could Adopt

- **From mattpocock:** Agent proposes its own answer during the RED phase — currently DDC's RED phase identifies gaps but doesn't propose what the answer *should* be, missing the anchoring benefit [^7]
- **From mattpocock:** CONTEXT.md as a persistent domain glossary — DDC's entity files serve a similar purpose but lack the explicit "Avoid" terminology disambiguation [^40]
- **From KB:** Open question preservation — when a DDC cycle ends with unresolved gaps, those should become explicit tracked artifacts rather than disappearing between sessions [^12]
- **From KB:** Governed mutation pipeline — DDC's entity creation has no review step beyond the human's 1–5 score; a lightweight validation layer would catch entity-level errors before they propagate [^23]

### 11.3 What wryenmeek/knowledgebase Could Adopt

- **From mattpocock:** The `grill-with-docs` pattern of inline CONTEXT.md mutation — KB's strict governance pipeline may be overkill for low-stakes domain glossary updates during development [^21]
- **From mattpocock:** The CONTEXT-FORMAT.md template — KB's CONTEXT.md files use a different format (`## Terms`, `## Invariants`, `## File Roles`); the mattpocock format's `_Avoid_` lists and `## Example dialogue` sections are more effective for disambiguation [^40]
- **From DDC:** Demand checklist typed gap categories — KB's `analyze-missed-queries` finds gaps but doesn't classify them by entity type, making prioritization harder [^8]
- **From DDC:** Quantified convergence metrics — KB has no per-cycle numerical tracking of how many gaps remain across an interactive session [^42]
- **From DDC:** The RED→GREEN cycle as a formal skill pattern — KB's `grill-me` skill could add an explicit "attempt to answer with current knowledge first" step before starting the adversarial questioning phase [^31]

---

## Footnotes

[^1]: Inferred from `mattpocock/skills` README references to Evans (Domain-Driven Design), Beck (TDD), and Ousterhout (A Philosophy of Software Design). SHA ref: `70141119`.

[^2]: Inventory from research subagent `mattpocock-skills-overview`: 10 engineering (`diagnose`, `grill-me`, `grill-with-docs`, `improve-codebase-architecture`, `tdd`, `to-issues`, `to-prd`, `triage`, `qa`, `setup-matt-pocock-skills`), 3 productivity, 4 misc, 2 personal, 4 in-progress, 4 deprecated.

[^3]: Navakoti & Navakoti, "Demand-Driven Context," arXiv:2603.14057, 2026. 46 entities in 9 cycles (270 min), success rate 0.0 → 0.75.

[^4]: DDC sub-agents: `ta-agent` (Technical Architect), `po-agent` (Product Owner), `se-agent` (Software Engineer), `da-agent` (Data Analyst), `sa-agent` (Solutions Architect). Verified from `.claude/agents/` directory.

[^5]: `wryenmeek/knowledgebase:AGENTS.md` and `raw/processed/SPEC.md`. Provenance-first, policy-aligned governance.

[^6]: Approximate counts from `.github/skills/` and `.github/agents/` directories. Exact counts vary with current repo state.

[^7]: `mattpocock/skills:skills/engineering/grill-me/SKILL.md` — "Ask ONE question at a time"; "For each question, provide YOUR recommended answer." Verified in KB fork at `.github/skills/grill-me/SKILL.md` (SHA: `3fd08da1`).

[^8]: `ea-toolkit/ddc:.claude/skills/ddc-cycle/SKILL.md` Step 2 RED Phase — demand checklist with 6 entity-type categories. SHA: `052e4694`.

[^9]: `wryenmeek/knowledgebase:.github/skills/context-engineering/SKILL.md` — structured confusion protocols: CONFUSION, MISSING REQUIREMENT, PLAN, ASSUMPTIONS.

[^10]: `mattpocock/skills:skills/engineering/grill-with-docs/SKILL.md` — "If a question can be answered by exploring the codebase, explore the codebase instead." SHA: `6dad6ad7`.

[^11]: `ea-toolkit/ddc` RED phase instructions — "Do not speculate beyond what the knowledge base contains."

[^12]: `wryenmeek/knowledgebase:.github/skills/record-open-questions/SKILL.md` — "Do not answer the question speculatively just to unblock automation."

[^13]: `mattpocock/skills:skills/engineering/grill-me/SKILL.md` — convergence = all decision branches resolved, no unresolved branches remaining.

[^14]: DDC demo convergence trajectory over 20 cycles: gaps 8→6→5→4→3→3→3→2→2→1→1→1→0 (13 cycles to zero); stable at zero through cycle 20.

[^15]: KB convergence: all skill phases complete + user confirms + no open escalations in governance pipeline.

[^16]: `mattpocock/skills:.out-of-scope/question-limits.md` — explicit design decision to have no question cap.

[^17]: DDC question count is implicitly bounded by problem scope — the demand checklist has as many items as the problem demands.

[^18]: `wryenmeek/knowledgebase:.github/skills/idea-refine/SKILL.md` — phase-gated with ~3–5 ideas evaluated per round.

[^19]: `ea-toolkit/ddc:.claude/skills/ddc-cycle/SKILL.md` Step 2: "Search domain-knowledge/entities/ for existing knowledge; Read matching entity files and assess coverage; Attempt to answer the problem using ONLY what exists in the KB."

[^20]: `wryenmeek/knowledgebase:.github/skills/zoom-out/SKILL.md` — reads entire codebase structure before surfacing gaps.

[^21]: `mattpocock/skills:skills/engineering/grill-with-docs/SKILL.md` — "When a term is resolved, update CONTEXT.md right there. Don't batch these up — capture them as they happen."

[^22]: `ea-toolkit/ddc:.claude/skills/ddc-cycle/SKILL.md` Step 3 GREEN Phase — all entity creation steps execute before Step 4 confirmation.

[^23]: `wryenmeek/knowledgebase:AGENTS.md` — governed pipeline requires policy review, evidence verification, and lock acquisition before wiki mutation.

[^24]: `mattpocock/skills:CONTEXT.md` — consumed by `diagnose`, `tdd`, `to-issues`, `to-prd`, `zoom-out`; created/updated by `grill-with-docs`, `improve-codebase-architecture`.

[^25]: `ea-toolkit/ddc:.claude/skills/ddc-entity/SKILL.md` — entity files at `domain-knowledge/entities/<type>/<kebab-case-id>.md` with YAML frontmatter. SHA: `091e7087`.

[^26]: KB output artifacts: decision logs from `grill-me`, open questions from `record-open-questions`, extraction bundles from `extract-entities-and-claims`.

[^27]: Cross-pattern analysis structural comparison Part 4.4 — convergence ownership taxonomy.

[^28]: `ea-toolkit/ddc:.claude/skills/ddc-cycle/SKILL.md` Step 5 — "If the human rejects your answer: record what you got wrong, incorporate corrections, re-answer. Repeat until accepted."

[^29]: KB knowledgebase-orchestrator validates prerequisites before declaring governance gates complete.

[^30]: mattpocock grilling — wrong answers during adversarial probing reveal hidden assumptions and misunderstandings.

[^31]: DDC RED phase — "the agent's inability to answer IS the signal of what to curate." Structural analysis from cross-pattern subagent.

[^32]: KB extraction skills route gaps as escalation flags — `analyze-missed-queries` identifies coverage gaps, `record-open-questions` preserves them.

[^33]: mattpocock description field routing — "The description is the only thing your agent sees when deciding which skill to load." `write-a-skill` SKILL.md.

[^34]: DDC explicit invocation — `ddc-cycle` orchestrates sub-skills via `Task` tool calls.

[^35]: KB hybrid routing — description triggers in SKILL.md frontmatter + `knowledgebase-orchestrator` lane routing for governed work.

[^36]: Grilling pattern appears in: `grill-me`, `grill-with-docs`, `improve-codebase-architecture` (embeds `grill-with-docs`), `writing-fragments` (adapted for creative excavation), `diagnose` (limited to Phase 1 + Phase 3 questioning).

[^37]: `mattpocock/skills:skills/engineering/grill-with-docs/SKILL.md` "During the session" section — four challenge triggers in priority cascade.

[^38]: `mattpocock/skills:skills/engineering/grill-with-docs/SKILL.md` — ADR offered only when: (1) Hard to reverse AND (2) Surprising without context AND (3) Result of a real trade-off.

[^39]: `mattpocock/skills:skills/in-progress/writing-fragments/SKILL.md` — excavation probes, append-only fragment file, convergence externally owned. SHA: `c36cee5b`.

[^40]: `mattpocock/skills:CONTEXT-FORMAT.md` — Language (term + definition + Avoid), Relationships, Example dialogue, Flagged ambiguities.

[^41]: Cross-pattern analysis Part 4.6 — TDD vs DDC RED/GREEN structural homology: "Both use intentional failure as an epistemic instrument."

[^42]: DDC cycle log frontmatter metrics: `entities_created`, `entities_updated`, `entities_reused`, `confidence_before`, `confidence_after`, `human_score`, `checklist_size`.

[^43]: KB two-family architecture: interactive Q&A (grill-me, idea-refine, context-engineering) vs. extraction/preservation (zoom-out, analyze-missed-queries, record-open-questions, claim-inventory, extract-entities-and-claims, using-agent-skills).

[^44]: `wryenmeek/knowledgebase:.github/skills/grill-me/SKILL.md` autopilot guard — if `ask_user` returns unavailable, stop immediately and display autopilot warning.

[^45]: `wryenmeek/knowledgebase:.github/skills/analyze-missed-queries/SKILL.md` — scans wiki pages for coverage gaps.

[^46]: `wryenmeek/knowledgebase:.github/skills/claim-inventory/SKILL.md` — enumerates factual claims from source intake.

[^47]: `wryenmeek/knowledgebase:.github/skills/extract-entities-and-claims/SKILL.md` — extracts candidate entities, concepts, claims, and chronology.

[^48]: `wryenmeek/knowledgebase:.github/skills/using-agent-skills/SKILL.md` — meta-skill for skill selection guidance.

[^49]: `wryenmeek/knowledgebase:.github/skills/context-engineering/logic/context_import_contract.py` — typed import contract with allowlisted paths, max 12 imports, path traversal protection. SHA: `a700e7f3`.

[^50]: Holub et al., "Two-Agent Socratic Protocol," arXiv:2601.14798, 2026 — dynamic stopping outperforms fixed-step.

[^51]: Siro et al., "AGENT-CQ," arXiv:2410.19692, 2024, 10 citations — LLM-generated clarifying questions outperform human-generated.

[^52]: Ataei et al., "Elicitron," arXiv:2404.16045, 2024, 75 citations — LLM agent interviews identify latent needs.

[^53]: Degen, "Resurrecting Socrates," arXiv:2504.06294, 2025, 13 citations — Socratic questioning triggers System 2 thinking.

[^54]: Held et al., "Clinician Perceptions of Socrates 2.0," Cognitive and Behavioral Practice, Elsevier, 2025, 2 citations — AI-generated questions teach humans better questioning.

[^55]: Academic RE technique mapping from research subagent `academic-context-patterns`.

[^56]: DDC paper (arXiv:2603.14057) claims 20–30 cycle convergence but demonstrates only 9 cycles reaching 0.75. Demo shows 13 cycles to zero gaps, 20 to stable — closer to the claim but from a simulation, not the paper's empirical study.
