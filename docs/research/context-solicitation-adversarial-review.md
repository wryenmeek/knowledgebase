# Adversarial Validation: Context-Solicitation Skill Design Patterns Report

**Target:** `docs/research/context-solicitation-skill-design-patterns.md`
**Method:** 10 research subagent dispatches across 2 waves. Wave 1 (5 agents): per-repo claim verification for mattpocock, DDC, KB; academic paper verification; omissions scan. Wave 2 (5 agents): KB attribution verification, counter-example confirmation, DDC infrastructure verification, comparison table accuracy, recommendation feasibility.
**Verdict:** The report contains **1 thesis-level failure**, **19 factual errors**, **12 material omissions**, **6 framing problems**, and **4 recommendation feasibility failures**. Approximately 40% of claims are fully verified; 35% are partially verified with meaningful inaccuracies; 25% are inaccurate, misleading, or unverifiable.

---

## Executive Summary

The report's central thesis — "Three open-source repositories have independently converged on a shared insight" — is **definitively refuted** by KB's own source code. Four KB skill files contain explicit attribution lines: `"Adapted from mattpocock/skills"` in `grill-me`, `caveman`, and `edit-article`; `"Inspired by mattpocock/skills"` in `zoom-out`. KB's test suite labels these as `"# mattpocock-inspired skills (ADR-014, research adoption)"`. The repos are not independent; KB directly adopted and adapted skills from mattpocock. Only the DDC↔mattpocock relationship appears genuinely independent (zero cross-references in either direction) [^1].

Beyond the thesis failure, the report inflates all academic citation counts (Elicitron 75→actual 31; AGENT-CQ 10→actual 7; Sami 18→actual 14), presents a study protocol as completed research, mischaracterizes DDC's mutation model as "batched/atomic" when it is actually per-entity auto-committed, omits DDC's entire enforcement infrastructure (hooks, rules, tooling), and recommends changes KB already has or that are hard-blocked by existing ADRs.

---

## 1. Thesis-Level Failure: "Independently Converged" Is Refuted

### What the report claims

§Executive Summary: "Three open-source repositories have independently converged on a shared insight." §6 header: "Shared Design Principles — All three repositories independently converge on five principles."

### What the evidence shows

`wryenmeek/knowledgebase` contains 8 files referencing `mattpocock/skills` [^1]:

| File | Verbatim text |
|------|--------------|
| `.github/skills/grill-me/SKILL.md` (final line) | "Adapted from mattpocock/skills `grill-me`. Focused on plan/decision stress-testing." |
| `.github/skills/zoom-out/SKILL.md` (final line) | "Inspired by mattpocock/skills `zoom-out`. KB variant adds governance orientation." |
| `.github/skills/caveman/SKILL.md` (final line) | "Adapted from mattpocock/skills `caveman`. KB variant restricts to agent-to-agent per NPOV/AI-tells policy." |
| `.github/skills/edit-article/SKILL.md` (final line) | "Adapted from mattpocock/skills `edit-article`. KB variant narrows to prose-only restructuring." |
| `docs/decisions/ADR-014-hitl-afk-work-classification.md` | "Inspired by the `to-issues` skill's HITL/AFK classification pattern" |
| `tests/kb/test_framework_skills.py` | `# mattpocock-inspired skills (ADR-014, research adoption)` |
| `wiki/sources/context-md-domain-model.md` | Research reference |
| `docs/ideas/skill-size-refactoring.md` | "the mattpocock target is ≤100 lines per skill" |

Cross-reference checks: mattpocock/skills has zero references to wryenmeek or ddc. ea-toolkit/ddc has zero references to mattpocock or wryenmeek [^1].

**Correct framing:** mattpocock/skills established patterns independently. DDC arrived at similar patterns independently. KB researched mattpocock/skills and explicitly adopted 4 skills. The KB↔mattpocock relationship is derivation, not convergence. Only the DDC↔mattpocock similarity could be called convergent.

---

## 2. Factual Errors (19 confirmed)

### 2.1 mattpocock/skills errors

| # | Claim | Actual | Severity |
|---|-------|--------|----------|
| E1 | grill-me: "Ask ONE question at a time" [^7] | Actual: "Ask the questions one at a time" (no caps) [^2] | Minor — substance correct, quote inexact |
| E2 | grill-me and write-a-skill are in `skills/engineering/` | Both are in `skills/productivity/` [^2] | Moderate — systematic path error |
| E3 | "Grilling pattern appears in 5 skills" including `diagnose` [^36] | `diagnose` has zero grilling language — no "one question at a time," no "recommended answer," no "interview." True count is 4 [^2] [^3] | Significant — inflates the pattern's reach |
| E4 | Footnote [^2] lists `grill-me` and `qa` as "engineering" skills | `grill-me` is productivity; `qa` is deprecated. `zoom-out` and `prototype` are the actual engineering skills in those slots [^2] [^4] | Significant — wrong inventory |
| E5 | CONTEXT.md "consumed by diagnose, tdd, to-issues, to-prd, zoom-out" [^24] | None of these 5 skills name `CONTEXT.md` explicitly — they reference "domain glossary" generically [^2] | Moderate — inferred wiring presented as explicit |
| E6 | Agent is "explicitly forbidden from declaring the session complete" (writing-fragments) [^39] | Actual: agent is told to stop when user signals readiness — a handoff constraint, not a prohibition on ending [^2] | Minor — interpretive overstatement |

### 2.2 DDC errors

| # | Claim | Actual | Severity |
|---|-------|--------|----------|
| E7 | "5 skills" including "ddc-cycle orchestrator" [^4] | 4 skills in `.claude/skills/`: ddc-cycle, ddc-entity, ddc-status, ddc-demo. Name is "ddc-cycle," not "orchestrator" [^5] | Moderate — wrong count and name |
| E8 | "success rate 0.0 → 0.75" [^3] | Metric is the **reuse ratio** (proportion of entity reuse), not a "success rate" [^5] | Significant — misidentifies the metric |
| E9 | Sub-agents "differ only in navigation starting points" | Agents have different roles, responsibilities, quality standards, procedural sections, and domain tooling [^5] | Significant — gross oversimplification |
| E10 | DDC mutation is "batched and atomic" [^22] | Auto-commit hook fires after EVERY Write/Edit — DDC is maximally incremental, not atomic. Each entity is individually committed [^6] [^7] | Significant — inverts the actual design |
| E11 | DDC uses "explicit invocation; ddc-cycle orchestrates sub-skills via Task" [^34] | ddc-cycle's Steps 0–6 are inline — it does NOT invoke ddc-entity, ddc-status, or ddc-demo as sub-skills [^5] [^7] | Significant — no sub-skill orchestration exists |

### 2.3 KB errors

| # | Claim | Actual | Severity |
|---|-------|--------|----------|
| E12 | "governed uncertainty" sourced from AGENTS.md [^5] | "Provenance-first" and "policy-aligned" appear in AGENTS.md; "governed uncertainty" appears nowhere — it is the report author's coinage [^8] | Moderate — misattributed framing |
| E13 | CONFUSION/MISSING REQUIREMENT/PLAN/ASSUMPTIONS all in context-engineering [^9] | ASSUMPTIONS protocol is in `using-agent-skills/SKILL.md`, not context-engineering [^8] | Moderate — wrong file attribution |
| E14 | idea-refine: "~3-5 ideas evaluated per round" [^18] | Actual: "Generate 5-8 idea variations." "3-5" refers to sharpening questions, not ideas [^8] | Moderate — conflated two different numbers |
| E15 | zoom-out "reads entire codebase structure" [^20] | It maps one module and immediate neighbors ("List its direct callers and callees. Map one level of abstraction up and one level down") [^8] | Significant — material mischaracterization |
| E16 | "orchestrator validates prerequisites" [^29] | Orchestrator routes and blocks; validation is done by downstream evidence-verifier and policy-arbiter [^8] | Moderate — wrong role description |

### 2.4 Academic paper errors

| # | Claim | Actual | Severity |
|---|-------|--------|----------|
| E17 | Citation counts: Elicitron 75, AGENT-CQ 10, Sami 18 | Actual: Elicitron 31 (2.4× inflated), AGENT-CQ 7 (1.4× inflated), Sami 14 (1.3× inflated) [^9] | Significant — all counts inflated |
| E18 | Degen (arXiv:2504.06294) demonstrates that Socratic questioning "triggers System 2 thinking" [^53] | Paper is a **study protocol** — it has not produced results. It *proposes* to test the hypothesis [^9] | Significant — future study presented as completed research |
| E19 | Held et al.: "AI questions teach humans better questioning" [^54] | Paper is about clinician *perceptions* of a patient-facing AI tool's acceptability, not about teaching humans questioning [^9] | Significant — mischaracterized finding |

### 2.5 Cross-system comparison errors

| # | Claim | Actual | Severity |
|---|-------|--------|----------|
| E20 | TDD/DDC analogy is "precise, not metaphorical" [^41] | Three unacknowledged disanalogies: (1) automated vs. human-judged pass/fail, (2) executable code vs. non-executable prose, (3) mechanical refactoring vs. editorial revision. DDC's own METHODOLOGY.md says only "Engineers will recognize this structure" — careful wording, not "precise" [^7] | Moderate — overstated |
| E21 | RE technique mappings [^55] presented as academic knowledge | These are the report author's analogies with no citations — not established in the RE literature [^9] | Moderate — unattributed opinion |

---

## 3. Material Omissions (12 confirmed)

### 3.1 Critical omissions (change a conclusion)

| # | Omission | Impact |
|---|----------|--------|
| O1 | KB's attribution lines to mattpocock (4 skill files + 4 other files) [^1] | Refutes the central thesis |
| O2 | `writing-fragments` is unpublished/in-progress — CLAUDE.md excludes it from README and plugin.json [^4] | A primary example is draft-only software, not deployed |
| O3 | `zoom-out` and `prototype` are published engineering skills the report never analyzes [^4] | Wrong skill inventory; both have context-solicitation relevance |
| O4 | `qa` (deprecated) explicitly caps questions at "2-3 short clarifying questions" [^3] | Counter-evidence to the no-limit questioning thesis that the report misses entirely |
| O5 | KB's wiki is completely empty (all `.gitkeep` files, epoch timestamps) | Report compares DDC's 41+ entities against KB's 102 skills — scaffolding vs. content, a category error |

> **Update (2026-05-13):** `wiki/concepts/` now contains 6 curated pages (`context-md-domain-model.md`, `github-customizations-governance.md`, `google-drive-source-monitoring.md`, `knowledgebase-spec.md`, `pre-commit-guardrails.md`, `wiki-quality-best-practices.md`) and `wiki/sources/` contains 7 processed source documents.

### 3.2 Major omissions (materially change analysis)

| # | Omission | Impact |
|---|----------|--------|
| O6 | DDC hooks (`validate-entity.sh`, `anonymization-guard.sh`, `auto-commit.sh`) + rules (`cycle-log-format.md`, `entity-format.md`, `anonymization.md`) [^6] | DDC has programmatic enforcement comparable in kind to KB's pre-commit hooks — report treats DDC as having minimal infrastructure |
| O7 | DDC ships a local KB explorer (FastAPI + React/Cytoscape) and a Firebase Cloud Functions gap scanner [^6] | Report never mentions DDC's most tangible user-facing deliverables |
| O8 | DDC is AI-tool-agnostic: has both `.claude/` and `.github/copilot-instructions.md` (4.6KB) [^6] | Report frames DDC as Claude Code-exclusive throughout |
| O9 | `to-issues` Step 4 asks 4 questions simultaneously — confirmed counter-example to §6.1 [^3] | Falsifies "all three agree on one-at-a-time questioning" |
| O10 | `to-prd` opens with "Do NOT interview the user — just synthesize what you already know" [^3] | Synthesis-without-solicitation is an equal pattern in the same repo |
| O11 | `setup-matt-pocock-skills` is the most context-solicitation-intensive skill in the repo, unanalyzed — mandates "one at a time" for 3 configuration decisions and explicitly warns "Don't dump all three at once" [^3] | Strongest evidence FOR the one-at-a-time thesis is invisible in the report |
| O12 | Plugin.json (13 published skills) vs. 27 total across all tiers — the report conflates published and draft/deprecated/personal [^4] | Active pattern library is smaller and better-defined than reported |

---

## 4. Framing Problems (6 confirmed)

| # | Problem | Evidence |
|---|---------|----------|
| F1 | "DDD-influenced (Evans, Beck, Ousterhout)" [^1] — collapses Evans=DDD, Beck=XP, Ousterhout=software design into a single "DDD-influenced" frame | README cites each for different frameworks; Thomas & Hunt also quoted but unreported [^2] |
| F2 | Report's [^56] critique of DDC convergence implies 9 cycles is a convergence failure | Paper presents 9 cycles as an illustration, not a convergence claim; the 20-30 figure is explicitly called "a hypothesis" [^5] |
| F3 | ddc-cycle described as "co-owned" convergence | Human has unilateral veto with no upper bound — asymmetric, closer to "human-closes" than symmetric "co-owned" [^7] |
| F4 | mattpocock tdd described as "agent owns convergence via checklist" | Test runner owns convergence (binary pass/fail); agent follows checklist discipline; user approval also required for plan [^7] |
| F5 | KB's convergence formula "all phases complete + user confirms + no open escalations" [^15] | Not found verbatim in any KB file — report author's analytical synthesis presented with citation weight [^8] |
| F6 | AGENT-CQ finding: AI questions "outperform human-generated" [^51] | Actual: outperform only on retrieval-based metrics (BM25, cross-encoder), not all quality dimensions [^9] |

---

## 5. Recommendation Feasibility Assessment

| Rec | Verdict | Key issue |
|-----|---------|-----------|
| **9.1** One-at-a-time as universal default | **Overstated** | mattpocock's own `to-issues` batches 4 questions simultaneously; `to-prd` forbids interviewing entirely. Source system contradicts the "universal" framing [^3] [^10] |
| **9.2** Make failure legible before filling gaps | **Well-supported** | DDC RED phase directly validates this [^5] |
| **9.3** Track convergence numerically | **Well-supported** | DDC's metrics are clearly more rigorous (though the demo trajectory is simulated, not empirical) [^5] |
| **9.4** Separate interactive from extraction skills | **Well-supported** | KB's two-family architecture demonstrates this [^8] |
| **9.5** Typed gap categories | **Partially feasible for KB** | Schema allows additive fields, but DDC's 6 categories need complete domain translation for Medicare/policy content [^10] |
| **9.6** Preserve uncertainty as first-class artifact | **Already exists in KB** | KB has `open_questions` (required frontmatter), `confidence` (required 1–5), and `## Open Questions` body section — all enforced by deterministic tooling [^10] |
| **9.7** Mutate at right frequency | **Well-supported** | Three patterns verified; but the DDC characterization (batched) is wrong — it's incremental [^7] |
| **9.8** Multi-perspective gap scanning | **Inferred, not demonstrated** | Report acknowledges this; no ablation study exists |
| **9.9** CONTEXT.md as cross-skill artifact | **Already exists in KB** | KB has 5 scoped CONTEXT.md files enforced by pre-commit hook. Format is deliberately different — adopting mattpocock format would require hook changes. Adding _Avoid_ lists is feasible without hook changes [^10] |
| **9.10** Gate ADR creation with conjunctive criteria | **Normative, not evidential** | Report doesn't show KB's 21 ADRs fail the three-gate test |
| **11.3** DDC RED→GREEN as AFK skill | **Hard-blocked** | ADR-014 §3 (operator cannot override to AFK), §4 (synthesis not on allowlist), §6 (AFK skips evidence-verifier/policy-arbiter). HITL equivalent already exists in persona pipeline [^10] |
| **11.3** mattpocock _Avoid_ lists | **Feasible** | Pre-commit hook is permissive of additional sections; no hook changes required; KB currently has zero term avoidance/disambiguation [^10] |

---

## 6. Verified Claims (what IS accurate)

To be fair, much of the report's substance is correct. Fully verified claims:

| Claim | Verification |
|-------|-------------|
| 27 skills / 6 buckets in mattpocock (exact counts per bucket) | ✅ All counts exact [^2] |
| `.out-of-scope/question-limits.md` exists and rejects limits | ✅ File exists with explicit design rationale [^2] |
| grill-with-docs: "update CONTEXT.md right there. Don't batch these up" | ✅ Verbatim match [^2] |
| ADR gating is conjunctive (all three required) | ✅ "all three are true" and "if any of the three is missing, skip" [^2] |
| CONTEXT-FORMAT.md has Language/Relationships/Example dialogue/Flagged ambiguities | ✅ All 4 sections present [^2] |
| DDC demand checklist has exactly 6 categories | ✅ Verbatim match in ddc-cycle SKILL.md [^5] |
| DDC anti-hallucination: "Do not speculate beyond what the knowledge base contains" | ✅ Verbatim in METHODOLOGY.md [^5] |
| ddc-demo gap trajectory 8→6→5→4→3→3→3→2→2→1→1→1→0 | ✅ Exact match cycle-by-cycle [^5] |
| RED phase has exactly 6 steps | ✅ Exact [^5] |
| Entity frontmatter: type, id, name, description, status + relationship fields | ✅ All fields verified [^5] |
| KB: 102 skills, 17 agent personas ("80+, 15+" is technically correct but undercounted) | ✅ Exact counts verified [^8] |
| `record-open-questions`: "Do not answer the question speculatively just to unblock automation" | ✅ Verbatim match [^8] |
| grill-me autopilot guard mechanism | ✅ Full mechanism and heading verified [^8] |
| context-engineering Python logic files with MAX_CONTEXT_IMPORTS=12, path traversal protection | ✅ All verified with exact code [^8] |
| KB CONTEXT.md uses "## Terms, ## Invariants, ## File Roles" (enforced by pre-commit hook) | ✅ Hook source confirmed [^8] [^10] |
| Holub et al. (arXiv:2601.14798): dynamic stopping outperforms fixed-step | ✅ Verbatim in abstract [^9] |
| Navakoti & Navakoti: paper exists, 46 entities, 9 cycles, 270 min | ✅ All statistics verified [^5] [^9] |

---

## 7. Summary Scorecard

### By category

| Category | Claims checked | Verified | Partially verified | Inaccurate/misleading | Unverifiable |
|----------|---------------|----------|-------------------|----------------------|-------------|
| mattpocock/skills | 13 | 6 (46%) | 4 (31%) | 3 (23%) | 0 |
| ea-toolkit/ddc | 13 | 6 (46%) | 4 (31%) | 3 (23%) | 0 |
| wryenmeek/knowledgebase | 14 | 5 (36%) | 5 (36%) | 3 (21%) | 1 (7%) |
| Academic papers | 8 | 2 (25%) | 4 (50%) | 2 (25%) | 0 |
| Cross-system comparisons | 8 | 2 (25%) | 3 (37.5%) | 3 (37.5%) | 0 |
| **Total** | **56** | **21 (37.5%)** | **20 (35.7%)** | **14 (25%)** | **1 (1.8%)** |

### Overall assessment

The report is a useful analytical framework with genuine insights (the grilling pattern taxonomy, the RED→GREEN structural parallel, the two-family architecture distinction). But it is undermined by:

1. **A refuted central thesis** — KB is derivative of mattpocock, not convergent with it
2. **Systematically inflated statistics** — all verifiable citation counts are wrong; skill counts include deprecated/unpublished items
3. **Missing enforcement infrastructure** — DDC's hooks and rules make it more comparable to KB than the report acknowledges
4. **Recommendations for things that already exist** — KB already has uncertainty preservation and cross-skill CONTEXT.md
5. **Counter-examples in the source data** — `to-issues` and `to-prd` undermine the universal applicability of the report's primary recommendation

The report would need to: reframe the thesis as "DDC and mattpocock converged independently; KB adopted from mattpocock and extended with governance"; correct all citation counts; add DDC's infrastructure to the comparison; remove recommendations that target KB features already in place; and acknowledge counter-examples within mattpocock/skills that complicate the "one-at-a-time" universal.

---

## Confidence Assessment

| Finding | Confidence | Basis |
|---------|-----------|-------|
| "Independently converged" thesis is refuted | **Very High** | Verbatim attribution lines in 4 SKILL.md files + test suite comment + ADR reference, confirmed by 2 independent subagents |
| All 3 citation counts are inflated | **High** | Semantic Scholar API queries; counts are snapshots that change over time but the magnitude of error (2.4× for Elicitron) is too large for drift |
| DDC mutation is incremental not atomic | **Very High** | `auto-commit.sh` hook + `settings.json` PostToolUse wiring confirmed verbatim |
| DDC hooks/rules/tooling exist | **Very High** | All files fetched and content verified with exact code/config |
| KB already has uncertainty preservation | **Very High** | `open_questions` and `confidence` are required blocking fields in `metadata-schema-contract.md` |
| KB already has cross-skill CONTEXT.md | **Very High** | 5 CONTEXT.md files at different scopes, enforced by pre-commit hook with exact `REQUIRED_SECTIONS` tuple |
| RED→GREEN as AFK is blocked by ADR-014 | **High** | ADR-014 §3, §4, §6 read directly; exhaustive allowlist does not include synthesis |
| `diagnose` has no grilling pattern | **High** | Full SKILL.md text searched; zero matches for grilling terminology |
| `to-issues` batches questions | **Very High** | Step 4 verbatim: 4 bullet questions with no sequencing constraint |
| Degen paper is a study protocol | **High** | Abstract says "will be" (future tense); describes proposed methodology not results |

---

## Footnotes

[^1]: Verified by `verify-kb-attributions` subagent. `search_code("mattpocock repo:wryenmeek/knowledgebase")` returned 8 files. All 4 SKILL.md attribution lines fetched and confirmed verbatim. `search_code("wryenmeek repo:mattpocock/skills")`, `search_code("ea-toolkit repo:mattpocock/skills")`, `search_code("mattpocock repo:ea-toolkit/ddc")`, `search_code("wryenmeek repo:ea-toolkit/ddc")` all returned 0 results.

[^2]: Verified by `verify-mattpocock-claims` subagent against commit `733d312884b3878a9a9cff693c5886943753a741`. All SKILL.md files fetched from `mattpocock/skills` main branch.

[^3]: Verified by `verify-counter-examples` subagent. `to-issues/SKILL.md` Step 4 "Quiz the user" (SHA: `9f6efbfe`); `to-prd/SKILL.md` opening line (SHA: `47a01d4e`); `qa/SKILL.md` Step 1 (SHA: `305e43fb`); `diagnose/SKILL.md` full text (SHA: `ed55bda2`); `setup-matt-pocock-skills/SKILL.md` Step 2 "one at a time" (SHA: `1ebc6e14`).

[^4]: Verified by `check-report-omissions` subagent. `.claude-plugin/plugin.json` lists 13 published skills; `CLAUDE.md` excludes personal/in-progress/deprecated from README and plugin.json.

[^5]: Verified by `verify-ddc-claims` subagent against `ea-toolkit/ddc` main branch. `.claude/skills/` directory listing, `.claude/agents/` directory listing, `ddc-cycle/SKILL.md`, `ddc-entity/SKILL.md`, `ddc-demo/SKILL.md`, `METHODOLOGY.md`, and arXiv:2603.14057 all fetched.

[^6]: Verified by `verify-ddc-infrastructure` subagent. `.claude/hooks/` (3 files), `.claude/rules/` (3 files), `.claude/settings.json`, `tooling/` (FastAPI backend + React frontend), `tools/context-gap-scanner/` (Firebase), `.github/copilot-instructions.md` all fetched and verified.

[^7]: Verified by `verify-comparison-claims` subagent. `ddc-cycle/SKILL.md` inline Steps 0-6 verified; `settings.json` PostToolUse auto-commit confirmed; `METHODOLOGY.md` TDD comparison table ("Engineers will recognize this structure"); mattpocock `CLAUDE.md` and plugin.json routing checked; KB `using-agent-skills/SKILL.md` routing categories confirmed.

[^8]: Verified by `verify-kb-claims` subagent against `wryenmeek/knowledgebase` main branch. All 14 claim-specific files fetched. Full `.github/skills/` and `.github/agents/` directory listings obtained.

[^9]: Verified by `verify-academic-claims` subagent. arXiv pages fetched for all 6 papers. Semantic Scholar API queried for citation counts: Elicitron `citationCount: 31`, AGENT-CQ `citationCount: 7`, Sami et al. `citationCount: 14`. Degen abstract confirmed future tense ("will be").

[^10]: Verified by `verify-recommendations` subagent. KB schema files (`metadata-schema-contract.md`, `ontology-entity-contract.md`, `taxonomy-contract.md`), pre-commit hook (`check_context_md_format.py`), ADR-014, all 5 CONTEXT.md files, and `route-wiki-task/SKILL.md` all fetched and verified.
