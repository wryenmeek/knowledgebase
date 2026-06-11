# Audit-Workspace `improve` Flow + Instruction Locality Ladder

**Status:** In Progress — 4 of 23 slices landed (Phase 0 Mechanism A #192, Phase 1 applyTo precommit #193, Phase 2 .github/.customizations.lock declaration #191, Phase 3 read-only scaffold #197); ADR-028 #190 pending. See § Slice progress (live) below for the authoritative status; plan body revised 2026-06-07 via grill-with-docs pass (see Appendix A for the 12 design decisions adopted on the user's behalf in autopilot mode).
**Origin:** Adapted from HSI's `docs/planned-work/audit-workspace-improve-flow.md` (2026-06-06), retargeted for this repo's customization surface

| Field | Value |
|---|---|
| Proposed ADR | **ADR-028: Instruction Locality Ladder for the Knowledgebase AI Ecosystem** (drafted in Phase 2; resolves K7 + K13 + Q5 trigger-frequency framing) |
| Related (informs, not supersedes) | `docs/ideas/github-customizations-governance.md` (Implemented; parity scaffolding only — does not address ratchet) |
| Related skill | `.github/skills/audit-knowledgebase-workspace/` (existing; extended in Phase 3) |
| Build entry point | **Phase 0 (Spike)** — Mechanism A (meta-rule override block) is validated in HSI and ships as the baseline; Mechanism B (UserPromptSubmit hook) is spike-tested and adopted as primary if it validates in CLI 1.0.60 |
| Vocabulary | "Locality N" = **trigger-frequency ordinal** (when the agent pays the prompt cost), not a destination taxonomy |
| Cross-surface targets | Copilot CLI 1.0.60 + VS Code Copilot Chat |
| Lock surface introduced | `.github/.customizations.lock` (sibling pattern to `wiki/.kb_write.lock` and `raw/.rejection-registry.lock`; never held simultaneously with either) |

---

## Slice progress (live)

As of 2026-06-10 the 23 vertical-slice issues (#190–#212) tracking this plan have the following state. This block is the authoritative status snapshot for the document body below — when individual phases are partially complete, the per-checkbox marks reflect what is on `main`, not what was originally proposed.

| Slice | Phase | Issue | State | Artifact on main |
|---|---|---|---|---|
| 1a | Phase 2 | [#190](https://github.com/wryenmeek/knowledgebase/issues/190) | **OPEN** (HITL, ready-for-human) | ADR-028 not yet drafted |
| 1b | Phase 2 | [#191](https://github.com/wryenmeek/knowledgebase/issues/191) | ✅ CLOSED | `CUSTOMIZATIONS_LOCK_PATH` declared in `scripts/kb/contracts.py`; runtime acquisition deferred to slice 9b / #209 |
| 2 | Phase 0/5 (Mechanism A) | [#192](https://github.com/wryenmeek/knowledgebase/issues/192) | ✅ CLOSED | Meta-rule override block, `Locality-4-Justification:` trailer template, CONTEXT.md terms — in `.github/copilot-instructions.md`, `AGENTS.md`, `docs/templates/locality-4-justification-trailer.md` |
| 3 | Phase 1 | [#193](https://github.com/wryenmeek/knowledgebase/issues/193) | ✅ CLOSED | `scripts/hooks/check_instructions_applyto_present.py` + matrix row |
| 4 | Phase 0 (Mechanism B spike) | [#194](https://github.com/wryenmeek/knowledgebase/issues/194) | OPEN (HITL) | Pending |
| 5a | Phase 6 | [#199](https://github.com/wryenmeek/knowledgebase/issues/199) | OPEN | Pending — superseded planning: the original "single pre-commit hook" is now split into pre-commit + commit-msg per the Phase 6 spec below |
| 5b | Phase 6 (soft budget) | [#200](https://github.com/wryenmeek/knowledgebase/issues/200) | OPEN | Pending — commit-msg-stage enforcement per the Phase 6 spec below |
| 5c | Phase 6 (advisory) | [#195](https://github.com/wryenmeek/knowledgebase/issues/195) | OPEN | Pending |
| 6 | Phase 3 (scaffold) | [#197](https://github.com/wryenmeek/knowledgebase/issues/197) | ✅ CLOSED | `.github/skills/audit-knowledgebase-workspace/{SKILL.md, logic/audit_workspace.py, references/locality-ladder.md}` |
| 7 | Phase 1.5 spike | [#196](https://github.com/wryenmeek/knowledgebase/issues/196) | OPEN (HITL) | Pending |
| 8a–8e | Phase 4 (classifier) | [#202](https://github.com/wryenmeek/knowledgebase/issues/202)–[#206](https://github.com/wryenmeek/knowledgebase/issues/206) | OPEN | Pending |
| 9a–9c | Phase 4 (`--apply`) | [#208](https://github.com/wryenmeek/knowledgebase/issues/208)–[#210](https://github.com/wryenmeek/knowledgebase/issues/210) | OPEN | Pending |
| 10 | Phase 7 (real-use) | [#212](https://github.com/wryenmeek/knowledgebase/issues/212) | OPEN (HITL) | Pending |
| qa-ab | QA gate | [#198](https://github.com/wryenmeek/knowledgebase/issues/198) | OPEN (HITL) | Pending |
| qa-d | QA gate | [#201](https://github.com/wryenmeek/knowledgebase/issues/201) | OPEN | Pending |
| qa-f | QA gate | [#207](https://github.com/wryenmeek/knowledgebase/issues/207) | OPEN (HITL) | Pending |
| qa-g | QA gate | [#211](https://github.com/wryenmeek/knowledgebase/issues/211) | OPEN | Pending |

**Rollup:** 4 of 23 slices CLOSED. **The original critical-path framing "no slices begin until #190 (ADR-028) merges" is no longer accurate** — slices 1b/2/3/6 were independently green-lit and merged ahead of #190 because each is independently buildable; the remaining slices still depend on #190 landing first. ADR-028 (#190) remains the lead artifact for the in-flight Phase 2 normative spec.

---

## Overview

`.github/copilot-instructions.md` has grown to **713 lines (+811/−98 in 6 months — an ~8.3:1 add:delete ratchet across 47 commits)**. The CLI built-in `/chronicle improve` is a primary driver — its hardcoded prompt always writes to the always-on global file, always produces "3-5 recommendations," and has zero locality logic. Roughly 14 chronicle-themed commits land every 2–3 weeks; many add multi-paragraph sections rather than tightening existing ones. The remaining growth comes from non-`/chronicle` agent-initiated and human-initiated edits with the same shape. *(Note: the May→June clean-window analysis below — `copilot-instructions.md` growing while skill count is flat — is the load-bearing observation; the 6-month aggregate is context.)*

This plan:

1. Adds an `improve` flow to the existing `audit-knowledgebase-workspace` skill that classifies every friction signal against a 9-level **locality ladder** (Locality 0..4) before recommending a destination.
2. Hard-redirects `/chronicle improve` (CLI builtin) to the new flow so the bad defaults are bypassed at every invocation. Mechanism A (meta-rule override block) is validated in HSI and ships as the baseline; Mechanism B (UserPromptSubmit hook) is **spike-tested and adopted as primary if it validates** — but the plan does not depend on B passing.
3. Closes the non-`/chronicle` channel via a Locality 3d pre-commit gate (blocking) + Locality 3c PostToolUse advisory (warning) on edits to **both** `.github/copilot-instructions.md` and `AGENTS.md` (this repo has two always-on top-level files; HSI has one).
4. Pairs every Locality 4 addition with a mandatory deletion candidate, OR requires a `Locality-4-Justification:` git trailer (auditable).
5. Works in **both** Copilot CLI and VS Code Copilot Chat.

## Goals

The locality ladder is fundamentally a **token-efficiency hierarchy**: it guides humans and agents to use the customization tools to prefer **targeted just-in-time delivery of context via progressive disclosure**, so tasks complete with the least amount of tokens wasted. The ratchet is what happens when this guidance is absent — additions default to Locality 4 (always-on) regardless of trigger conditions, and the always-on file grows monotonically.

Operational goals follow from this:

- **Token-cheapest viable tier wins.** Every new friction signal lands at the tier whose `(trigger frequency × per-fire cost)` is minimized for the rule's actual usage pattern. File-comment beats glob-instruction beats skill beats hook beats always-on, *given equal compliance*.
- **Right-locality writes by default.** The `improve` flow makes this the path of least resistance instead of always Locality 4.
- **Stop the ratchet (consequence, not goal).** Net-neutral or net-negative size on always-on files is a *symptom* of the efficiency goal being honored.
- **Cross-surface portability.** Same skill, same locality ladder, same hooks work in CLI and VS Code.
- **Self-healing first run.** First real-use should surface the largest current Locality 4 occupants as Locality 0/1/2/3 demotion candidates (notable: the 25+ subsections under "Codebase-specific patterns," "Operational patterns," and "Pre-Commit Hook Gotchas"–style entries).
- **Respect existing governance.** Any new `logic/` script must land with a write-surface matrix row in `AGENTS.md`, a CONTEXT.md `last_updated` bump where applicable, and a cascade-completeness test row — this repo's standing rules apply unchanged.

---

## Background — Why This Is Needed

### Quantitative evidence of the problem (sharpened 2026-06-07)

The original framing ("+2398 / −77 in 6 months") conflated **proportional growth** with **ratchet**. Re-segmenting:

| Window | Skills | `copilot-instructions.md` | `AGENTS.md` | Interpretation |
|---|---|---|---|---|
| 2026-04-15 → 2026-05-15 | 21 → 102 (**+385%**) | 73 → 473 (**+548%**) | not segmented (delta dominated by mass write-surface matrix-row landing for new script families) | **Roughly proportional growth** — not a ratchet, just keeping up with the customization-surface explosion |
| 2026-05-15 → 2026-06-07 | 102 → 102 (**0%**) | 473 → 674 (**+42.5%**) | net **+3** lines | **`copilot-instructions.md` is the only file ratcheting** |

The May→June window is the clean signal: instruction file grew 201 lines with **zero** customization-surface growth to justify it. `AGENTS.md` is flat in the same window (the +1716 over 6 months was almost entirely write-surface matrix rows landing alongside new script families — proportional and exempt from the ratchet gate by design).

**Multi-consumer caveat for `AGENTS.md` (Decision Q1 follow-up):** The +3-line clean-window number reflects **Copilot-CLI-driven growth only**. `AGENTS.md` is the cross-tool agent-guideline convention also consumed by Antigravity IDE and Gemini CLI (and any other agent following the `AGENTS.md` filename convention). Those tools have their own session-capture patterns, chronicle equivalents, and ratchet vectors that this repo has not yet measured. The plan therefore treats `AGENTS.md` at **blocking** urgency in Phase 6 (same tier as `copilot-instructions.md`), with the write-surface matrix table body carved out. Growth channels may differ per consumer; the gate is consumer-agnostic.

### Channel inventory for the May→June ratchet (3 channels, not 4)

| Channel | Net contribution | Example commits |
|---|---|---|
| **`/chronicle improve` and chronicle-themed commits** | +48 lines (**~24%**) | `ac2ff13`, `058827d`, `7d3fa14`, `f52f460`, `0508889` |
| **Post-feature-work session-capture** (agent-initiated lessons-learned bundled into feat/fix commits) | +145 lines (**~72%**) | `e2dc59c` "capture GitHub Actions security patterns from CI hardening session" (+48/−0), `892a487` "feat: enforce pinned qmd runtime" (+31/−1), `b179cb6` "CI-5/CI-6 documentation deltas" (+1/−1), `2772e37` ready-for-agent backlog fix (+2/−0) |
| **Anomalous CLI auto-checkpoint** | +73 lines (one commit: `c347741`) | One-off in 6 months — **not** a recurring channel; treated as outlier in this plan |

The plan's primary lever is **Phase 6's pre-commit gate**, which catches all three channels uniformly at the commit boundary. The `/chronicle improve` redirect (Phase 0 + Phase 5) addresses ~24% of the ratchet; the gate addresses the rest.

### Root cause: CLI builtin has hardcoded bad defaults

The `/chronicle improve` command is a first-class CLI builtin. The hardcoded prompt:

| Hardcoded bias | Result |
|---|---|
| Destination = `.github/copilot-instructions.md` | Every recommendation lands in always-on global |
| Count = "3-5 recommendations" | Forces output even when zero items warrant a global rule |
| Guardrail = "seen happen more than once" (N≥2) | Permits promotion at N=2 |
| Zero locality logic | No "should this be a hook? a skill? a scoped instruction?" |
| Zero pruning step | Additions only; never asks "what stale entry should we remove?" |

This repo *partially* tightens the builtin via the "`/chronicle improve` deterministic flow" rule in `copilot-instructions.md`, which adds a delta-amend pass and a dedup hygiene rule. **That helps but does not change the fundamental destination bias** — the cheapest mechanism the rule has is still "edit `copilot-instructions.md`," because no locality ladder, no scoped instructions directory, and no commit-time gate exists yet.

### Mechanism for redirecting `/chronicle improve` — two paths, verified in parallel

The CLI binary cannot be modified. Two override mechanisms are candidates:

1. **Meta-rule in `.github/copilot-instructions.md`** (HSI's original approach, **validated in production**): the override block sits at the top of the file the CLI prompt forces the agent to read first, instructing the agent to ignore the builtin prompt's destination and invoke the audit skill instead. Agent-compliance-dependent in theory; HSI deployment confirms compliance in practice.
2. **`UserPromptSubmit` hook intercepting `/chronicle improve`** (Locality 3e): mechanically deterministic in theory; the hook fires before the builtin prompt is processed and can inject skill-invocation context or rewrite the prompt. **Unverified in CLI 1.0.60** — UserPromptSubmit is not documented as a supported event for this redirect pattern. Cross-surface bonus *if* it validates: works in VS Code too, removing the "VS Code users must invoke skill manually" gap.

**Mechanism A is the baseline** (ships unconditionally). **Mechanism B is a Phase 0 spike enhancement** — adopted as primary if it validates; otherwise dropped silently. (Decision Q2 in Appendix A.)

### Existing accountability gaps (this repo)

| Accountability mechanism | Exists? |
|---|---|
| Locality ladder document | ❌ |
| Triage decision tree in `/chronicle improve` | ⚠️ partial (delta-first + dedup hygiene rules exist, but no ladder) |
| `.github/instructions/*.instructions.md` directory with `applyTo:` | ❌ (no directory exists today) |
| Lint that flags single-file lore in always-on globals | ❌ |
| Size budget on `copilot-instructions.md` or `AGENTS.md` | ❌ |
| Expiry / sunset metadata on lore entries | ❌ |
| Pre-commit gate on always-on file edits | ❌ |
| CI freshness check on `.github/**` | ✅ `github-customizations-freshness.yml` (drift detection; no size-ratchet logic yet) |
| Audit skill for the framework workspace | ✅ `audit-knowledgebase-workspace` (doc-only; no `improve` flow yet) |

---

## The Locality Ladder (Locality 0 → Locality 4)

> **Naming.** "Locality" avoids collision with any existing tier vocabulary in this repo. Each Locality names *when* the agent pays the context cost. The ladder is fundamentally a **token-efficiency hierarchy** — lower tiers minimize wasted tokens by deferring context delivery until needed (progressive disclosure / JIT). Reading the table top-to-bottom: **per-turn cost grows from 0 to full-body; conditional cost (paid only when triggered) is the JIT principle in action.**

| Locality | Trigger | Mechanism | Token cost per turn | Conditional cost when triggered |
|---|---|---|---|---|
| **0** | File read | Code comment / `# noqa: X` rationale / docstring | **0** | File body (paid only when reading that file) |
| **1** | File matches glob (passive JIT — *metadata-table only in CLI*) | `.github/instructions/<scope>.instructions.md` **with required `applyTo:` frontmatter** | **~1 row metadata** (every turn, fixed) | File body on agent-`view` when path matches; **compliance-dependent** (Locality 2 equivalence — see below) |
| **2** | User invocation | `.github/skills/<name>/SKILL.md` | **0** | Full skill body when invoked |
| **3a** | Tool call (active JIT inject) | `PreToolUse` hook → returns context string | **0** | Injected string before specific tool actions |
| **3b** | Tool call (block/gate) | `PreToolUse` hook → non-zero exit | **0** | Block + reason (e.g., extending `simplify-ignore.sh`) |
| **3c** | After file edited | `PostToolUse` hook filtered on edit tool + path glob | **0** | Injected string after edits to specific paths |
| **3d** | Pre-commit framework | `.pre-commit-config.yaml` hook | **0** | Block/warn at `git commit` time |
| **3e** | User submits prompt | `UserPromptSubmit` hook | **0** | Injected string when prompt content matches |
| **4** | Always-on | `.github/copilot-instructions.md` **AND** `AGENTS.md` | **Full file body** (every turn, no exception) | n/a — cost is always paid |

### Sidebar: how Copilot CLI 1.0.60 actually handles `.github/instructions/`

Verified by reading the bundled CLI source (`~/.copilot/pkg/<platform>/<version>/app.js`, function `BXo` around line 256, and the loader at line 4326):

```javascript
// Splitter (simplified from BXo):
for (let n of t)
  if (n.type === "vscode" && n.applyTo) r.push(n);   // applyTo files → metadata-table bucket
  else e.push({content: n.content, source: o, ...}); // no-applyTo files → always-loaded bucket
```

- **Files WITH `applyTo:` frontmatter:** contents are **NOT** loaded every turn. Only a metadata table row (`applyTo` glob + path + description) is injected, accompanied by a prompt: *"Here is a list of instruction files that contain rules... If you have not already read the file, use the `view` tool to acquire it. Make sure to acquire the instructions before making any changes to the code."* **Agent compliance required.**
- **Files WITHOUT `applyTo:` frontmatter:** **full contents loaded every turn** — hidden Locality 4 ratchet via the always-loaded bucket. Phase 1 enforces `applyTo:` as a required invariant via pre-commit hook.
- **Cursor `.cursor/rules/*.mdc` files** are also recognized by the CLI (see `app.js` around line 4701) with `globs:` + `alwaysApply:` frontmatter. When `alwaysApply: true`, behaves like a no-`applyTo:` instruction file (always-loaded). When `alwaysApply: false`, behaves like an `applyTo:` instruction file (metadata-only). Out of scope for the locality ladder but worth knowing for users with mixed Cursor/Copilot workflows.
- **Other recognized locations** documented by the CLI's `/help` output but out of scope for this plan: `CLAUDE.md`, `GEMINI.md`, `$HOME/.copilot/copilot-instructions.md`, and the `COPILOT_CUSTOM_INSTRUCTIONS_DIRS` env var.

**Reference links** (for future ADR maintenance and CLI version drift detection):
- CLI docs (instruction discovery): `/help` output of `copilot` CLI; see `Copilot respects instructions from these locations:` block. Mirrored in `fetch_copilot_cli_documentation` output for this CLI version.
- GitHub Docs (path-specific instructions format): <https://docs.github.com/copilot/how-tos/configure-custom-instructions/add-repository-instructions> — defines `applyTo:` glob syntax and `excludeAgent:` keyword.
- CLI source (table-injection mechanism): `~/.copilot/pkg/<platform>/<cli-version>/app.js`, splitter at the function emitting `"Here is a list of instruction files that contain rules for modifying or creating new code"`. (Bundled minified JS; greppable by string literal.)
- Cursor `.mdc` format: <https://docs.cursor.com/context/rules-for-ai> (loaded via the same internal model in `app.js` around the `mPs="rules"` constant).

### Locality 2 compliance equivalence (Decision Q4 follow-up)

Because the CLI table-injection mechanism **requires agent compliance** (the agent must `view` the instruction file when matching paths are in context), Locality 1 inherits the same compliance shape as Locality 2 (skill invocation: agent must read the skill body to act on it). Implications baked into Phase 4's classifier:

- The **token-cost advantage** of Locality 1 over Locality 4 is real (~1 metadata row vs full file body, every turn).
- The **determinism advantage** of Locality 1 over Locality 2 is **illusory** — both depend on agent compliance.
- Demotion calculus: Locality 4 → Locality 0 (file comments) is the only **strictly deterministic** demotion. Locality 4 → Locality 1 and Locality 4 → Locality 2 are token-cost demotions with compliance-dependent enforcement.
- The classifier emits a `compliance_risk: "deterministic" | "agent-dependent"` field on every demotion finding (Phase 4 schema) so dry-run reports surface this explicitly.

### Two-file scope for Locality 4 (with urgency tiers)

This repo has **two** always-on top-level instruction files: `.github/copilot-instructions.md` (Copilot-CLI agent behavior) and `AGENTS.md` (repository operational rules + write-surface matrix; cross-tool consumed by Antigravity IDE, Gemini CLI, and other tools following the `AGENTS.md` filename convention). Both are functionally always-on (`AGENTS.md` is documented as a REPO_ROOT layout sentinel in `scripts/init.py`).

**Both files are gated at blocking urgency** in Phase 6, with the write-surface matrix table body in `AGENTS.md` carved out. Reasoning per Decision Q3:
- `.github/copilot-instructions.md` is Copilot-CLI-specific; observable ratchet evidence in this repo is dominated by this file.
- `AGENTS.md` is consumed by multiple agent tools (Antigravity IDE, Gemini CLI, Aider, etc.). The "+3 line clean window" in this repo only measures Copilot-CLI-driven growth; other consumers can drive their own growth patterns via different channels. Lower urgency would create a blind spot.

The Phase 5 override block ships to **both** `.github/copilot-instructions.md` and `AGENTS.md` (slice 2 / #192 landed both copies; verified by the Locality 0 invariant comment now sitting as the first H2 in each file). HSI-validated effectiveness applies specifically to Copilot CLI reading `copilot-instructions.md`; the `AGENTS.md` placement is precautionary multi-consumer coverage mirroring Decision Q3 — agent-compliance for Antigravity IDE, Gemini CLI, and other `AGENTS.md` consumers is unverified and treated as belt-and-suspenders. Phase 6's pre-commit gate covers both files at the same urgency tier regardless.

The write-surface matrix table body in `AGENTS.md` is **exempt** from the ratchet check — it grows as the codebase grows, by design. Phase 6's gate must allowlist the matrix table. (Decision Q3 in Appendix A.)

### Locality assignment (5-step efficiency check)

The check is **not** "prove this CAN'T live anywhere lower before promoting it to Locality 4." It's the inverse and goal-aligned: **find the tier that delivers this rule with minimum expected token waste across its actual trigger pattern.** A candidate stays at Locality 4 only if all five lower-locality tiers produce worse expected token efficiency given the rule's trigger conditions.

1. **Can it live at Locality 0 (file comment)?** Rule sits at a single point in code → 0 tokens-per-turn, body cost only when that file is read. Cheapest deterministic tier. **Always pick this if viable.**
2. **Can a plausible `applyTo:` glob be authored (Locality 1)?**
    - Bar: "no glob currently exists" is **not** sufficient. Bar is "no glob *could* be authored that targets the affected files." If a glob could exist, author it — even a brand-new `.github/instructions/<name>.instructions.md` file is cheaper than a Locality 4 entry (~1 row metadata per turn vs full file body).
    - **Locality-2-equivalent compliance:** Locality 1 requires agent compliance with the read-on-demand prompt. Token-cost advantage real; determinism advantage illusory (see Locality 2 compliance equivalence subsection). Classifier flags this in `compliance_risk`.
    - **Sub-context awareness.** Friction concentrated in one of this repo's known surfaces — `scripts/kb/**`, `scripts/fleet/**`, `scripts/github_monitor/**`, `scripts/drive_monitor/**`, `scripts/ingest/**`, `scripts/validation/**`, `scripts/reporting/**`, `scripts/maintenance/**`, `scripts/context/**`, `scripts/hooks/**`, `.github/skills/**`, `.github/agents/**`, `wiki/**`, `schema/**`, `docs/decisions/**`, `tests/kb/**` — MUST be considered for a per-context Locality 1 glob even though `.github/instructions/` is empty today.
3. **Is it a discrete multi-step workflow (Locality 2)?** Fits "user invokes; agent runs steps." Note: 102 skills already exist; the bar is "could this be a skill or a `references/` checklist under an existing skill?" 0 tokens-per-turn; full body cost only when invoked.
4. **Can a hook event fire it (Locality 3a–3e)?** 0 tokens-per-turn; injected context paid only on triggering event.
    - Triggered by a tool call → `PreToolUse` injection (3a) or gate (3b)
    - Triggered by a file edit → `PostToolUse` injection (3c)
    - Gateable at commit → pre-commit hook (3d) (this repo already uses pre-commit heavily — `check_adr_cross_ref.py`, `check_stub_archive_path.py`, `check_context_md_format.py`, etc., per `scripts/hooks/`)
    - Promptable from prompt content → `UserPromptSubmit` hook (3e)
5. **Need is unpredictable from any signal AND applies to >50% of sessions** — only then does always-on full-body cost beat any conditional injection. Locality 4 is the **last resort**, not the default.

**Escape hatch.** Candidates that survive the 5-step efficiency check but have no plausible deletion candidate must be committed with a `Locality-4-Justification: <reason>` git trailer. Grep-able for periodic audit (`git log --grep "Locality-4-Justification"`). Trailer use is rate-limited by the Phase 6 soft budget so it doesn't become a default bypass.

### Deletion-candidate categories (mandatory per Locality 4 addition)

Two classes, hybrid detection (see Phase 4):

1. **Stale** — *deterministic detection:*
    - Cites a file/script/symbol no longer in repo (regex-extract paths/symbols → check `git ls-files` / `rg`)
    - Cites a fixed bug — closed GitHub issue (`gh issue view <N> --json state`)
    - Superseded by an ADR — walk `docs/decisions/` for `## Status` "amended" / "extended" / numbered supersession references
2. **Redundant-up-the-ladder** — *LLM-judgment with mandatory citation:*
    - Locality 4 bullet duplicating a Locality 3 hook's enforcement
    - Locality 4 bullet duplicating a Locality 2 skill's procedure (high-risk in this repo: 102 skills mean many candidate covers exist)
    - Locality 4 bullet duplicating a Locality 1 scoped instruction's guidance
    - **Citation requirement:** every "redundant" claim MUST cite the lower-locality artifact path *and* the snippet from that artifact that allegedly covers the candidate. Uncited claims are dropped.

### What the ladder would do to today's always-on globals (illustrative)

| Current Locality 4 entry | Disqualification | Correct locality |
|---|---|---|
| `FRAMEWORK_BOUNDARY_DOCS` table (test-monitored literal strings in `docs/ideas/wiki-curation-agent-framework.md`) | Locality 0 (comment in the doc itself, near the table) + Locality 3d (a pre-commit check on the listed files) | **Locality 0 + Locality 3d** |
| Drive-monitor test patterns (sys.modules stub injection idiom) | Locality 1 (glob: `tests/drive_monitor/**/*.py`) | **Locality 1** |
| Jules SDK `.env` loading rule | Locality 1 (glob: `scripts/fleet/**/*.ts`) OR Locality 0 (comment in a Jules helper) | **Locality 1** |
| ADR evolution pattern | Locality 1 (`docs/decisions/ADR-*.md`) — fires only when editing an ADR | **Locality 1** |
| Mermaid diagram syntax rules | Locality 1 (`docs/research/**/*.md` and `docs/ideas/**/*.md` — files most likely to contain Mermaid) | **Locality 1** |
| Build/lint commands at top of file | Locality 1 (`**/*.py` and `scripts/fleet/**/*.ts` split) OR Locality 3a (`PreToolUse` on `bash` injecting test commands on demand) | **Locality 1 or Locality 3a** |
| "Pickup where you left off" resume protocol | Locality 3e (`UserPromptSubmit` matching `pickup` / `where you left off` / typo variants) | **Locality 3e** |
| "Fleet deployed" continuation signal | Locality 3e (`UserPromptSubmit` matching `fleet deployed`) | **Locality 3e** |
| Multiple "is an execution directive" rules | Locality 3e (`UserPromptSubmit` matching each phrase) | **Locality 3e** |
| `/chronicle improve` deterministic flow | Locality 3e (`UserPromptSubmit` matching `/chronicle improve`) — once Phase 5 redirect is in place, this becomes redundant with the skill itself | **Locality 3e or Delete (covered by Phase 5 redirect + Phase 3 skill)** |
| Cross-functional review hard rule | Locality 2 (already covered by `quality-pass-chain` skill — bullet may be redundant-up-the-ladder if citation is found) | **Locality 2 (verify citation) or keep at 4** |

This is illustrative — Phase 4's real classifier produces the binding output.

---

## Cross-Surface Compatibility — Copilot CLI + VS Code Copilot Chat

### What works in both surfaces

| Plan element | CLI | VS Code |
|---|---|---|
| `.github/copilot-instructions.md` (Locality 4) | ✅ | ✅ |
| `.github/instructions/*.instructions.md` + `applyTo:` (Locality 1) | ✅ | ✅ |
| `.github/skills/*/SKILL.md` (Locality 2) | ✅ | ✅ (Agent Skills open standard) |
| `.github/hooks/hooks.json` location | ✅ | ✅ (same hook format across CLI, VS Code, Claude Code) |
| `PreToolUse` block + `additionalContext` (Locality 3a, 3b) | ✅ | ✅ |
| `UserPromptSubmit` (Locality 3e) | ✅ | ✅ |
| `SessionStart`, `Stop` | ✅ (already used: `session-start.sh`, `simplify-ignore.sh`) | ✅ |

### What's CLI-only (designed around)

| Event / feature | Resolution |
|---|---|
| `postEdit` event | **Locality 3c uses `PostToolUse` + `tool_name == "edit"` filter + path glob inside hook script.** Same UX, works in both surfaces. |
| `preCommit`, `preRun`, `postRun`, `sessionEnd` | Not needed for this plan; CLI-only features remain CLI-only |
| `/chronicle improve` slash command | Doesn't exist in VS Code. Redirect block is a no-op there; VS Code users invoke `/audit-knowledgebase-workspace improve` directly (or "audit my workspace for friction") to trigger the same flow. Block is self-documenting. |

### Pre-build prerequisite — hook event casing

✅ **Already done in this repo.** `.github/hooks/hooks.json` uses PascalCase (`SessionStart`, `PreToolUse`, `PostToolUse`, `Stop`). No migration micro-PR is needed. New hooks introduced by this plan are PascalCase from day 1.

---

## Implementation Phases

> **Numbering note.** Phase 0 is an enhancement spike. Mechanism A is HSI-validated and ships unconditionally; Phase 0 only determines whether Mechanism B is added as primary. Phase 0 outcome does **not** gate Phases 1–7.

### Phase 0 — Spike: test UserPromptSubmit hook (Mechanism B); ship Mechanism A regardless

Mechanism A (meta-rule override block) is already validated in the HSI deployment and ships unconditionally as Phase 5 work. Phase 0's purpose is narrower: empirically verify whether Mechanism B (UserPromptSubmit hook) actually intercepts `/chronicle improve` in Copilot CLI 1.0.60. If yes, B is adopted as primary and A becomes belt-and-suspenders. If no, B is dropped silently and Phase 5 ships A-only (matching HSI shape).

**Mechanism A: meta-rule override block (HSI-validated; no spike needed) — ✅ landed via slice 2 (#192)**

- [x] No Phase 0 work required for A. It ships in Phase 5 unconditionally per HSI precedent. *(Override block now present in `.github/copilot-instructions.md` and `AGENTS.md`; Locality 0 invariant comment guards its position.)*
- [ ] Test stub deferred to Phase 7 (real-use validation), not gated here.

**Mechanism B: `UserPromptSubmit` hook (Locality 3e) — Phase 0 spike**

- [ ] Add a `UserPromptSubmit` entry to `.github/hooks/hooks.json` pointing at a new `bash .github/hooks/chronicle-improve-intercept.sh`.
- [ ] Implement the hook: if stdin JSON's `prompt` field starts with `/chronicle improve`, inject `additionalContext` instructing the agent to invoke the audit skill's `improve` flow; otherwise no-op.
- [ ] Create a stub `improve` flow in `.github/skills/audit-knowledgebase-workspace/SKILL.md` that prints `REDIRECT-B WORKED — UserPromptSubmit mechanism` and exits.
- [ ] In a fresh CLI session, invoke `/chronicle improve`.
- [ ] **Pass B:** agent prints `REDIRECT-B WORKED` (or invokes the skill which prints it).
- [ ] **Cross-surface bonus:** repeat the test in VS Code Copilot Chat — `UserPromptSubmit` should fire there too if the event is shared, closing the "VS Code has no /chronicle command" gap.

**Decision rules:**

- [ ] **B passes:** keep both. Hook is primary (mechanically deterministic); meta-rule is belt-and-suspenders. Phase 5 ships both.
- [ ] **B fails:** drop Mechanism B silently; revert `hooks.json` and remove the hook script. Phase 5 ships A-only (HSI shape). **The plan continues uninterrupted.**
- [ ] **Acceptance:** session-transcript evidence captured (whether B passed or failed). Drop or keep B accordingly.
- [ ] **On Phase 0 close:** draft `docs/decisions/ADR-028-instruction-locality-ladder.md` with status `Proposed` (**draft-only checkpoint**, not yet `Accepted`). The Phase 0 draft records the spike outcome (B-pass or B-fail) and the intended Phase 5 mechanism mix. ADR-028 is **promoted to `Accepted` in Phase 2** once the Phase 1.5 spike has captured the agent-compliance rate and the normative ladder spec is in place. This ordering prevents accepting an ADR before the evidence and normative content it cites exist.
- [ ] **Estimated time:** ~30 minutes (single spike against B; A needs no test work).

### Phase 1 — Prerequisite: establish `.github/instructions/` convention *(partially landed via slice 3 / #193)*

The repo has no `.github/instructions/` directory today. Locality 1 mechanism needs one before it can be used. **Status:** the pre-commit guard (`scripts/hooks/check_instructions_applyto_present.py`) is on main; the `.github/instructions/` directory itself, its `README.md` convention doc, freshness-workflow path addition, and write-surface matrix row are still pending.

- [ ] Create `.github/instructions/` with a `README.md` describing the convention: filename pattern (`<scope>.instructions.md`), **required frontmatter** (`applyTo:` glob — **non-optional**; `description:` optional), CLI behavior note ("metadata-only injection; agent must `view` file when paths match"), VS Code compatibility note.
- [ ] Add cascade-test row in `tests/kb/test_doc_cascade_completeness.py`: "When a new `.github/instructions/*.instructions.md` is added, bump `last_updated` in `.github/skills/CONTEXT.md`" (treat instructions as part of the customization surface).
- [ ] Add `.github/instructions/` to the `github-customizations-freshness` workflow's monitored paths.
- [ ] Add write-surface matrix row for `.github/instructions/**` in `AGENTS.md` (`read-only only`; no logic).
- [x] **Hidden-ratchet pre-commit guard.** Add `scripts/hooks/check_instructions_applyto_present.py` that fails commit when any staged `.github/instructions/*.instructions.md` file is missing `applyTo:` frontmatter. Justified by the CLI source-code finding: a frontmatter-less file is loaded fully every turn (silent Locality 4). Wire into `.pre-commit-config.yaml`. Add a write-surface matrix row for the new hook (`read-only only`). *(Landed via slice 3 / #193 with write-surface matrix row in `AGENTS.md`.)*
- [ ] **Do NOT pre-create instruction files for the 16 sub-context globs.** Per Decision Q8: lazy creation only. Empty instruction files are themselves Locality 1 ratchet shape.
- [ ] **Acceptance:** Directory exists, convention documented (with required-`applyTo:` rule), freshness CI picks up new files, pre-commit hook fails on frontmatter-less files, no test failures.

### Phase 1.5 — Spike: empirically test agent compliance with `applyTo:` read-on-demand (Decision Q4, revised)

**What we already know (no spike needed):** Copilot CLI 1.0.60 **does load** `.github/instructions/*.instructions.md` files (confirmed in `/help` output) and **does honor `applyTo:`** as a metadata-table mechanism (confirmed by reading bundled `app.js`, function `BXo`). The CLI injects a table of `(applyTo, sourcePath, description)` rows and instructs the agent to `view` the file when paths match — see the "Sidebar: how Copilot CLI 1.0.60 actually handles `.github/instructions/`" subsection in Background.

**What the spike tests:** whether the agent reliably **complies** with the read-on-demand prompt when working on matching paths. This is a **compliance test**, not a feature test. (Same compliance class as Mechanism A in Q2.)

- [ ] Create a probe instruction file `.github/instructions/probe.instructions.md` with `applyTo: "docs/probe-target.md"` and a distinctive instruction string (e.g., "ACK: probe instruction loaded — when responding about docs/probe-target.md, prepend the literal string `PROBE-LOADED` to your reply.").
- [ ] Create the matching `docs/probe-target.md` with a trivial question.
- [ ] In a fresh CLI session, run `/env` first and verify the probe row appears in the injected instructions table. Capture transcript.
- [ ] Then ask the agent about `docs/probe-target.md` (without explicitly telling it to read the instruction file).
- [ ] **Pass:** agent autonomously reads `probe.instructions.md` via `view` and prepends `PROBE-LOADED` to its reply. Records baseline compliance rate over ≥3 fresh-session attempts.
- [ ] **Soft fail:** agent ignores the table-injection prompt. Record the failure mode; Phase 4 classifier must treat Locality 1 demotions as compliance-risk-tagged, and the dry-run report must surface this risk for every Locality 1 finding.
- [ ] Repeat in VS Code Copilot Chat to record cross-surface compliance behavior (informational only — VS Code is not the canonical surface per Decision Q9).
- [ ] Clean up probe files after recording the result.
- [ ] **Acceptance:** ADR-028 records the observed compliance rate (pass count / attempt count) per surface. Phase 4 classifier's `compliance_risk` field is grounded in this measurement, not in assumption.

### Phase 2 — Locality ladder normative spec + ADR-028 (resolves K7 + K13 + Q5)

- [ ] Draft `docs/decisions/ADR-028-instruction-locality-ladder.md` covering (this is where Phase 0's draft is **promoted to status `Accepted`** — Phase 0 lands it as `Proposed`, and the spike evidence captured in Phase 1.5 is folded in before the status change):
    - **Purpose statement (Decision Q5, revised).** The ladder is a **token-efficiency hierarchy** that guides humans and agents to deliver context via the token-cheapest viable tier. Each locality is a JIT / progressive-disclosure trade-off characterized by `(trigger frequency × per-fire cost)`. The ratchet is what happens when this guidance is absent. Trigger-frequency is one input to the efficiency calculation, not the destination axis. Reading the ladder table top-to-bottom shows the trade-off explicitly: per-turn cost grows from 0 to full-body; conditional cost is paid only when triggered.
    - **CLI `applyTo:` mechanism — verbatim from the sidebar in Background.** Document that Locality 1 in CLI is a **metadata-table-only** mechanism; the agent must `view` the file on demand. Include the source-code reference paths (`app.js` function `BXo`; mirror the JS splitter snippet). Document the Phase 1.5 measured compliance rate per surface.
    - **Locality 2 compliance equivalence** (Decision Q4 revised): Locality 1 and Locality 2 share the same compliance shape (agent must read on demand). The token-cost advantage of Locality 1 is real; the determinism advantage is not. The classifier emits a `compliance_risk` field on every demotion finding so this is surfaced explicitly in dry-run reports.
    - **Hidden-ratchet invariant.** `.github/instructions/*.instructions.md` files WITHOUT `applyTo:` are silently loaded every turn (always-loaded bucket per the CLI splitter). Phase 1 enforces required-`applyTo:` via pre-commit hook.
    - **Sidebar: other recognized instruction locations.** Out-of-scope for the ladder but documented for completeness: `CLAUDE.md`, `GEMINI.md`, `$HOME/.copilot/copilot-instructions.md`, `COPILOT_CUSTOM_INSTRUCTIONS_DIRS` env var, Cursor `.cursor/rules/*.mdc`. Reference links to the GitHub Docs page and the CLI source-code locations are reproduced from the Background sidebar.
    - Motivation (May→June ratchet evidence; 3-channel inventory).
    - The 9-locality table.
    - The 5-step disqualification chain for Locality 4 promotion.
    - The two deletion-candidate classes.
    - The `Locality-4-Justification:` trailer escape and its **soft budget** (Decision Q10): max 1 trailer per 10 commits to global rules sections within a rolling window; beyond that, the gate hard-fails until a paired deletion lands. **Trailer validation is a `commit-msg` stage concern, not pre-commit** — document the two-stage hook split (Phase 6 spec): pre-commit checks `net_section_delta = additions − deletions ≤ 0` inside non-exempt regions; commit-msg parses the trailer via `git interpret-trailers --parse` and enforces the soft budget. Both must be wired via `pre-commit install --hook-type pre-commit --hook-type commit-msg`. **Canonical trailer text-of-record:** `docs/templates/locality-4-justification-trailer.md` (shipped in slice 2 / #192); contributors should copy-paste from that template rather than freehand the trailer.
    - The two-file scope with **blocking urgency on both files** (Decision Q3, revised per multi-consumer reality): `copilot-instructions.md` AND `AGENTS.md` both gated at blocking; `AGENTS.md` has a write-surface matrix table carve-out.
    - **K13 resolved (Decision Q7):** new lock `.github/.customizations.lock` follows the sibling pattern established by `wiki/.kb_write.lock` (ADR-005) and `raw/.rejection-registry.lock` (ADR-013). No ordering relationship with either; never held simultaneously. Lock-file cleanup pattern added to `scripts/init.py --fresh` mode.
    - Verified surface matrix from Phase 1.5 (CLI agent-compliance rate per surface).
- [ ] Create `.github/skills/audit-knowledgebase-workspace/references/locality-ladder.md` mirroring the ADR's normative tables with worked examples (use the "illustrative" table above as a seed).
- [ ] Symlink or include from the SKILL.md so it loads only when the skill is invoked (progressive disclosure).
- [ ] Update `docs/decisions/README.md` index with the new ADR row (enforced by `tests/kb/test_adr_readme_status_sync.py` and the pre-commit `check_adr_cross_ref.py` hook).
- [x] Add `.github/.customizations.lock` to `GOVERNANCE_LOCK_FILES` in `scripts/kb/contracts.py` (the pre-commit `check_governance_lock_files.py`-style hook prevents accidental staging). *(Landed via slice 1b / #191: path constant `CUSTOMIZATIONS_LOCK_PATH` registered in `scripts/kb/contracts.py`; runtime lock-file acquisition is deferred to slice 9b / #209 when `--apply` write-capability lands.)*
- [ ] **Acceptance:** ADR-028 is `Accepted`, README index updated, `references/locality-ladder.md` is the single source of truth, lock constant registered, trigger-frequency framing explicit in the ADR's opening section.

### Phase 3 — Extend `audit-knowledgebase-workspace` SKILL.md with `improve` flow

- [ ] Extend `.github/skills/audit-knowledgebase-workspace/SKILL.md` to expose two flows:
    - **Default flow**: structural lint only — *byte-identical* to current behavior (the existing reference/command/wrapper integrity audit).
    - **`improve` flow**: two-mode contract:
        - **Dry-run (default):** Phase A structural audit → Phase B mine session store + classify by locality + emit dry-run report. No file mutations.
        - **`--apply` (write-capable wiring deferred to Phase 4):** In Phase 3 the flag is documented and recognized but **MUST refuse with a "matrix-row pending Phase 4" message** while the surface row remains `read-only only`. Phase 4 enables it once the narrow-write matrix-row amendment, lock acquisition, and classifier all land; behavior at that point is: consume the dry-run report; user accepts the whole report OR selects individual items; agent applies accepted items in one batch (deletions + demotions + new artifact creation), leaves changes staged for user review/commit.
- [x] **Ships a stub classifier** at `.github/skills/audit-knowledgebase-workspace/logic/audit_workspace.py` returning an empty findings list. Keeps SKILL.md end-to-end demoable on its own; Phase 4 swaps in the real classifier without touching SKILL.md. *(Landed via slice 6 / #197 — note the filename is `audit_workspace.py`, not `improve_workspace.py` as earlier drafts of this plan said; Phase 4 work below targets the same file.)*
- [ ] **Write-surface matrix row — Phase 3 lands as `read-only only`** (Decision Q6: split matrix-row landing across Phase 3 + Phase 4 so the matrix tracks code reality at each boundary):
    - Path: `.github/skills/audit-knowledgebase-workspace/logic/**`
    - Runtime mode: `read-only only` (stub classifier returns one hardcoded finding; no writes)
    - Writable paths: **none** at Phase 3
    - Reads: session-store query templates, `.github/copilot-instructions.md`, `AGENTS.md`, `.github/skills/**` (frontmatter-only via index cache), `.github/hooks/**`
    - Locks: none required for read-only mode
    - Hard-fail conditions: missing dry-run input, unsupported destination, classifier output failing JSON schema validation
- [ ] Phase 4 amends this row to add narrow write capability for `--apply` mode (see Phase 4 spec).
- [ ] **Dry-run report schema (load-bearing for Phase 7).** Report emits BOTH human-readable markdown AND a fenced JSON block. The schema below includes the classifier fields that Phase 4 / Phase 7 acceptance depends on, so tests and consumers built against this contract from Phase 3 onward stay forward-compatible:
    ```json
    {
      "findings": [
        {
          "source_file": "string — .github/copilot-instructions.md | AGENTS.md",
          "source_section": "string — H2/H3 heading or signal identifier",
          "proposed_destination": "one of: Delete | Locality 0 | Locality 1 | Locality 2 | Locality 3a | Locality 3b | Locality 3c | Locality 3d | Locality 3e | Locality 4 | OutOfBand",
          "deletion_candidate": "string path+snippet | null",
          "rationale": "string",
          "citation": "string artifact path + snippet | null (required when proposed_destination = Delete via redundant-up-the-ladder)",
          "compliance_risk": "one of: deterministic | agent-dependent — required on every finding; Locality 1, Locality 2, Locality 3e, and Locality 4 mechanism-A destinations MUST report 'agent-dependent'",
          "expected_token_efficiency_rank": "integer — relative cost rank of (estimated trigger frequency × per-fire cost) across candidate destinations; lower is cheaper; required on every finding",
          "cache_strategy": "one of: mtime_first_para | hybrid_signature — which skill-corpus indexing strategy generated the finding; Phase 3 stub MAY emit 'mtime_first_para' as the only value; required on every finding"
        }
      ]
    }
    ```
    Phase 3's stub classifier MUST emit all seven always-required fields (`source_file`, `source_section`, `proposed_destination`, `rationale`, `compliance_risk`, `expected_token_efficiency_rank`, `cache_strategy`) — the two conditionally-nullable fields (`deletion_candidate`, `citation`) may be `null` when not applicable. Stub findings are hardcoded; values may be placeholder but the seven required keys are mandatory so the JSON schema validator in Phase 3 acceptance is exercised against the same shape Phase 4 / Phase 7 will rely on.
- [ ] Progressive disclosure: Phase B / `--apply` mechanics live in `logic/` scripts loaded only when the flow is requested. SKILL.md root stays small.
- [ ] **CONTEXT.md cascade:** bump `last_updated` in `.github/skills/CONTEXT.md`.
- [ ] **Cascade-test rows** updated where required (write-surface matrix test, framework-skills test).
- [ ] **Acceptance (Phase 3, read-only only — `--apply` mutation acceptance moves to Phase 4 alongside the write-capable matrix-row amendment):** Default invocation produces no change vs today; `improve` (dry-run) produces a locality-classified report with the canonical JSON block (stub returns exactly one hardcoded finding so end-to-end wiring is exercised without depending on Phase 4); the `--apply` flag is wired so it can be invoked but **MUST refuse with a clear "matrix-row pending Phase 4" exit** while the surface row remains `read-only only`. Phase 4 reasserts this acceptance with mutation enabled once the matrix row, lock requirements, and classifier all land. All matrix-row, CONTEXT.md, and cascade-test obligations satisfied.

### Phase 4 — `logic/audit_workspace.py` classifier (hybrid algorithm) + matrix-row amendment

- [ ] Replace the Phase 3 stub with the real classifier:
    - `session_store_sql` query templates for friction signals (chronicle commits, repeated user prompts, repeated context loads, hook bypasses, retry loops).
    - **11-bin classifier** (input: friction signal; output: one of `Delete | Locality 0 | Locality 1 | Locality 2 | Locality 3a | Locality 3b | Locality 3c | Locality 3d | Locality 3e | Locality 4 | OutOfBand` + rationale + `compliance_risk` field + `expected_token_efficiency_rank` field + `cache_strategy` field + suggested artifact path). Output schema matches the Phase 3 canonical JSON block (the `OutOfBand` value is the cross-skill handoff route described below). **Optimization objective (Decision Q5 revised):** for each finding, propose the tier that **minimizes expected token waste across the rule's actual usage pattern**, computed as `(estimated trigger frequency × per-fire cost)`. Not "find the lowest locality number" — find the cheapest *for this rule's expected trigger pattern*. The `compliance_risk` field (Decision Q4 revised) is `"deterministic"` (Locality 0 + Locality 3a/3b/3c/3d) or `"agent-dependent"` (Locality 1, Locality 2, Locality 3e, Locality 4 mechanism-A). Locality 1 demotions inherit Locality-2-equivalent compliance shape — dry-run report MUST surface this for every Locality 1 finding so the reviewer can decide whether the token-cost advantage justifies the compliance dependency. The `cache_strategy` field (Decision Q11) records which skill-corpus indexing strategy generated the finding (`"mtime_first_para"` baseline; `"hybrid_signature"` if Phase 7 retro escalates per K15 upgrade trigger) so successive runs can be diffed to detect late-caught false-negatives. **Locality 1 destination availability assumes CLI behavior verified by reading `app.js`** (no separate gating on Phase 1.5 — that spike measures agent compliance rate, not feature presence). Prompt MUST mention per-context Locality 1 globs (`scripts/kb/**`, `scripts/fleet/**`, `scripts/github_monitor/**`, `scripts/drive_monitor/**`, `scripts/ingest/**`, `scripts/validation/**`, `scripts/reporting/**`, `scripts/maintenance/**`, `scripts/context/**`, `scripts/hooks/**`, `.github/skills/**`, `.github/agents/**`, `wiki/**`, `schema/**`, `docs/decisions/**`, `tests/kb/**`) as **viable destinations the classifier may propose lazily** — but **do not pre-create empty instruction files** (Decision Q8).
    - **Hybrid deletion-candidate generator:**
        - **Stale (deterministic):** path/symbol extraction → `git ls-files` / `rg` check; issue ref extraction → `gh issue view --json state`; ADR-supersession walker over `docs/decisions/`.
        - **Redundant-up-the-ladder (LLM judgment with mandatory citation):** loads every lower-locality artifact as comparison corpus; emits redundancy claims only with cited artifact path + snippet. Uncited claims are dropped.
    - **Skill-corpus indexing (Decision Q11):** Cache SKILL.md frontmatter + first paragraph only (not full bodies); refresh on file mtime change. Accepts the false-negative on first pass when a SKILL body changes meaningfully but the first paragraph doesn't — the next chronicle session that surfaces the missed redundancy will catch it. **Document this tradeoff in the SKILL.md `improve` flow contract.**
    - **Cross-skill suggestions are out-of-band (Decision Q12):** if the classifier identifies a redundancy or demotion target that would require editing another skill's `SKILL.md` or another agent's persona file, the finding is emitted with `proposed_destination: "OutOfBand"` and routes to a framework-engineer handoff. The `--apply` mode refuses to touch cross-skill files.
- [ ] **Write-surface matrix row — amend with narrow write capability for `--apply` mode** (Decision Q12 blast-radius containment):
    - Path: `.github/skills/audit-knowledgebase-workspace/logic/**`
    - Runtime mode: `read-only only` for `--dry-run` (default); `blocking-only with narrow write capability` for `--apply`
    - **Apply-mode CREATE paths:** `.github/instructions/<scope>.instructions.md` (new files only), `.github/hooks/*.sh` + `.github/hooks/hooks.json` updates (new hook scripts and registration entries only — never modify existing hook scripts)
    - **Apply-mode MODIFY paths:** `.github/copilot-instructions.md`, `AGENTS.md` (subject to Phase 6 gate's matrix carve-out), `.github/skills/audit-knowledgebase-workspace/**` (self-owned scope only)
    - **Apply-mode FORBIDDEN paths:** any other skill's `SKILL.md` or `logic/**` or `references/**`; any agent's persona file in `.github/agents/`; any prompt template in `.github/prompts/`; anything under `wiki/`, `raw/`, `schema/`, `scripts/`, `tests/`, or `docs/` other than ADR creation for new ADRs the classifier proposes
    - Locks: `.github/.customizations.lock` (introduced in ADR-028) — acquired once for the entire batch, released after all apply-mode writes complete; never held simultaneously with `wiki/.kb_write.lock` or `raw/.rejection-registry.lock`
    - `--approval approved` flag required for `--apply` mode
    - Hard-fail conditions: missing `--approval`, lock unavailable, dry-run report not provided, ratchet violation (apply that would add to a file without paired deletion or trailer + budget room), cross-skill write attempt, trailer-budget exhaustion (per Decision Q10)
- [ ] Unit tests in `tests/kb/test_improve_workspace_classifier.py` covering: each locality bin, the stale detector, the citation-required gate dropping uncited redundancy claims, the schema validator, the OutOfBand routing for cross-skill suggestions, the cross-skill-write hard-fail in `--apply` mode.
- [ ] **Acceptance:** Running the classifier produces the expected locality and artifact path; every "redundant" finding includes a citation; uncited findings dropped; cross-skill suggestions emit OutOfBand and `--apply` refuses cross-skill writes; skill-corpus index keeps a typical run under per-call token budget.

### Phase 5 — Override block in `copilot-instructions.md` AND `AGENTS.md`

- [ ] Insert the override block as the **first H2 under the H1 title**, before any other content section, in **both** `.github/copilot-instructions.md` and `AGENTS.md`. (Slice 2 / #192 has already landed both copies; this Phase 5 entry now governs the position invariant going forward.) Required structure (showing `copilot-instructions.md`; substitute `# AGENTS` for the AGENTS.md copy):

    ```markdown
    # Copilot project instructions

    <!-- LOCALITY-0-INVARIANT: This H2 MUST remain the first H2 under the H1. -->
    <!-- Position is load-bearing for the /chronicle improve hard-redirect. -->
    <!-- Do not move, demote, or insert another H2 above it without ADR-028 revision. -->

    ## ⚠️ Slash-Command Override: /chronicle improve → audit-knowledgebase-workspace skill

    When the user runs `/chronicle improve` (Copilot CLI built-in), do not
    execute Steps 2-3 of the built-in prompt. Instead, invoke the
    `audit-knowledgebase-workspace` skill and follow its `improve` flow
    exclusively. That skill owns: session-store mining, locality-ladder
    classification (Locality 0..4), deletion-pairing for every Locality 4
    addition across BOTH `.github/copilot-instructions.md` AND `AGENTS.md`,
    and writes to the chosen locality — not necessarily either always-on
    file.

    VS Code Copilot Chat users: there is no `/chronicle` command — invoke
    `/audit-knowledgebase-workspace improve` directly (or "audit my
    workspace for friction") to trigger the same flow.

    Fallback only if the skill is unavailable: apply
    `.github/skills/audit-knowledgebase-workspace/references/locality-ladder.md`
    manually.

    ## <existing first content section>
    ```

- [ ] **Pre-commit hook to enforce Locality 0 invariant:** add `scripts/hooks/check_override_block_position.py` that verifies the override block is the first H2 in **both** `copilot-instructions.md` and `AGENTS.md` whenever either file is staged. Wire into `.pre-commit-config.yaml`.
- [ ] **Write-surface matrix row** for the new hook (`read-only only`; standard hook hard-fail behavior).
- [ ] **Acceptance:** The override block is the first H2 in both files (verifiable via `grep -n '^## ' .github/copilot-instructions.md AGENTS.md | grep ':1:' | head -2`, which should report the H2 line per file), the ⚠️ emoji prefix is present, the Locality 0 invariant comment block sits immediately above it, and the pre-commit hook blocks any reordering attempt in either file.

### Phase 6 — Close the non-`/chronicle` growth channel

The redirect intercepts only the explicit `/chronicle improve` invocation. The remaining growth comes from non-`/chronicle` agent-initiated and human-initiated additions. This phase plugs the remaining channels at the only persistent boundary: `git commit`.

- [ ] **Locality 3d gate — split across `pre-commit` and `commit-msg` stages** on any commit touching `.github/copilot-instructions.md` **or** `AGENTS.md` — **blocking on both files** per Decision Q3 (multi-consumer reality for `AGENTS.md`). The split is required because git's `pre-commit` stage runs *before* the commit message exists and only receives staged file paths, so the `Locality-4-Justification:` trailer is not visible at `pre-commit` time. `commit-msg` is the only stage that receives the finalized commit-message file path:
    - **Definition of "global rules sections" for the ratchet check:**
        - `copilot-instructions.md`: everything *below the override block* (i.e., from the second H2 onward). The override block itself is **exempt**.
        - `AGENTS.md`: everything *except* the `## Write-surface matrix` table body. Matrix rows are mandated by other rules and grow with the codebase by design.
    - **Default behavior on violation:** **blocking** (hard-fails the commit) for both files. Lowering `AGENTS.md` to advisory would create a blind spot for non-Copilot-CLI consumers (Antigravity IDE, Gemini CLI).
    - **Stage 1 — `pre-commit` hook (`scripts/hooks/check_locality_ratchet.py`).** Read-only; receives staged file paths. Compares the staged diff against HEAD inside the non-exempt regions of each gated file and computes `net_section_delta = additions − deletions` *within the non-exempt sections only* (NOT additions-only). Passes when `net_section_delta ≤ 0`, so a net-negative replacement (e.g., a 3-line stale rule replaced by a 1-line rule: +1/−3, delta = −2) passes even though additions > 0. When `net_section_delta > 0`, the hook records a sentinel marker (e.g., emits a structured stderr line and exits 0 only if the commit-msg stage will run) and **defers the final pass/fail to the commit-msg stage** so the trailer escape can still apply.
        - Actual deferral mechanism: when `net_section_delta > 0`, the pre-commit hook exits **non-zero with a message naming the file(s) and the required `Locality-4-Justification:` trailer**, but documents that the trailer is checked by the commit-msg stage. Operators who add the trailer get a clean pass at commit-msg; those who don't are blocked at pre-commit. (Implementations may instead write a per-repo state file the commit-msg stage consumes; the contract is "trailer-aware pass/fail end-to-end," not the specific signaling mechanism.)
    - **Stage 2 — `commit-msg` hook (`scripts/hooks/check_locality_justification_trailer.py`).** Read-only; receives the path to the prospective commit-message file as `$1`. Reads the message file, looks for a `Locality-4-Justification: <reason>` trailer (RFC-5322 trailer format, parsed via `git interpret-trailers --parse`), and enforces the soft budget below. When the pre-commit stage signaled a positive `net_section_delta`, the commit-msg stage passes iff the trailer is present **and** within budget. When the pre-commit stage already passed on `net_section_delta ≤ 0`, the commit-msg stage is a no-op for that commit.
    - **Wiring.** Add both hooks to `.pre-commit-config.yaml`: `check_locality_ratchet.py` with `stages: [pre-commit]`, and `check_locality_justification_trailer.py` with `stages: [commit-msg]`. Both hooks must be installed via `pre-commit install --hook-type pre-commit --hook-type commit-msg`; update the repo's setup docs to include the `--hook-type commit-msg` step.
    - Block the commit unless EITHER:
        - The Stage 1 `net_section_delta = additions − deletions` *inside global rules sections* is `≤ 0` (any addition paired with at least an equivalent deletion of stale or redundant-up-the-ladder content; a net-negative replacement passes even when additions > 0), OR
        - The Stage 2 commit-msg hook confirms a `Locality-4-Justification: <reason>` trailer is present — **subject to the soft budget below**.
    - **Trailer soft budget (Decision Q10):** the commit-msg hook runs `git log --grep "Locality-4-Justification" --since="<rolling-window>"` over the last 10 commits to global rules sections. If 1 trailer is already present in that window, the commit-msg gate hard-fails until a paired-deletion commit lands. Numerically tunable; document the default ratio (1-in-10) in ADR-028. Budget is **per-file** (separate counts for `copilot-instructions.md` and `AGENTS.md`) so a noisy week on one file doesn't starve the other. Contributors should paste the trailer text from `docs/templates/locality-4-justification-trailer.md` (shipped in slice 2 / #192) to ensure the format matches what `git interpret-trailers --parse` will accept.
    - On block, both hooks print locality-ladder demotion candidates from `improve --dry-run` so the author can choose to demote, pair, or justify.
    - Implementation: `scripts/hooks/check_locality_ratchet.py` (pre-commit; read-only matrix row; `net_section_delta` computation on either file's non-exempt regions) **plus** `scripts/hooks/check_locality_justification_trailer.py` (commit-msg; read-only matrix row; trailer parse via `git interpret-trailers --parse` and soft-budget check via `git log`). Add a write-surface matrix row for each new hook.
- [ ] **Locality 3c PostToolUse advisory** on `edit` tool filtered to `.github/copilot-instructions.md` or `AGENTS.md`:
    - After any in-session edit, inject context: *"You just edited `<file>`. Did you classify this against the locality ladder? Consider whether this rule belongs at Locality 0, 1, 2, or 3 before committing. The pre-commit hook will require a paired deletion or `Locality-4-Justification:` trailer."*
    - Non-blocking; advisory only.
    - Implementation: extend `.github/hooks/hooks.json` PostToolUse array with a new entry; wire to a new `.github/hooks/locality-advisory.sh`.
- [ ] **Cascade obligations:**
    - Write-surface matrix rows for **all three** new hooks (`check_locality_ratchet.py`, `check_locality_justification_trailer.py`, and the `locality-advisory.sh` PostToolUse advisory).
    - `.pre-commit-config.yaml` registers `check_locality_justification_trailer.py` with `stages: [commit-msg]`. Repo setup docs (`docs/mvp-runbook.md` or equivalent) updated to instruct contributors to run `pre-commit install --hook-type pre-commit --hook-type commit-msg` so the commit-msg stage actually fires locally.
    - CONTEXT.md `last_updated` bump in `.github/skills/CONTEXT.md` (covers hooks per the domain mapping).
    - `tests/kb/test_doc_cascade_completeness.py` row if a new doc-cascade obligation is introduced.
    - `tests/kb/test_ci_permission_asserts.py` does **not** apply (no new workflow).
- [ ] **Acceptance:** A test commit that adds a line to `copilot-instructions.md` or `AGENTS.md` (outside the exempted regions) without pairing or trailer is blocked at the **pre-commit** stage. A net-negative replacement (e.g., +1/−3 inside non-exempt sections) passes pre-commit because `net_section_delta ≤ 0`, even though additions > 0. A commit with a `Locality-4-Justification:` trailer succeeds at the **commit-msg** stage (and is grep-able via `git log --grep "Locality-4-Justification"`), while a commit that adds the trailer beyond the rolling soft-budget hard-fails at commit-msg. PostToolUse advisory fires on edits and does not block. End-to-end test confirms that `pre-commit install --hook-type pre-commit --hook-type commit-msg` is required for the trailer-escape path to function.

### Phase 7 — First real-use exercise (validation, not feature work)

- [ ] In a fresh CLI session, invoke `/chronicle improve` against the current `copilot-instructions.md` + `AGENTS.md`. Capture the dry-run report.
- [ ] In a fresh VS Code Copilot Chat session, invoke `/audit-knowledgebase-workspace improve`. Capture the dry-run report.
- [ ] **Expected output (both surfaces):** demotion proposals for the largest current Locality 4 occupants — at minimum the "Codebase-specific patterns," "Operational patterns," and protocol/directive entries enumerated in the illustrative table above. Each with cited rationale and a non-Locality-4 destination.
- [ ] Compute set-equivalence between the two reports (parse each into `{source_file, source_section, proposed_destination, deletion_candidate_or_none}` tuples).
- [ ] **Cross-surface conflict resolution (Decision Q9):** **CLI output is canonical**. Where VS Code disagrees, file follow-up classifier-improvement issues but do **not** block acceptance. Reasoning: CLI is the surface generating the chronicle ratchet, so CLI agreement is the load-bearing requirement.
- [ ] **Acceptance:**
    - **Must-pass subset:** the illustrative-table entries appear in the **CLI report** with non-Locality-4 destinations and cited rationale.
    - **Cross-surface overlap:** set-overlap on findings beyond the must-pass subset is ≥80% between CLI and VS Code outputs. Below 80%, file an issue and proceed; do not block on overlap alone.
    - If even one must-pass entry is left at Locality 4 in the CLI report, the spec or classifier has a gap that must be diagnosed before declaring acceptance.
- [ ] **Cache-strategy upgrade-trigger tracking (Decision Q11).** Each chronicle run emits a per-finding `cache_strategy: "mtime_first_para"` field. Phase 7 retro adds a quarterly tally column to the dry-run report log: `cache_false_negatives_caught_late` — count of redundancy findings flagged on run N+1 that should have been caught on run N because the corresponding skill body changed but the first paragraph did not. Computed deterministically by diffing successive run JSON outputs (no manual classification). If the 90-day running count crosses **≥3 with ≥10 lines of Locality 4 growth each** before catch, open a follow-up issue to evaluate Option 3 (hybrid mtime + first-paragraph signature). Below threshold, the mtime-only strategy stays.

---

## Decision Knobs — Proposed Defaults (open for user override)

| # | Knob | Proposed default |
|---|---|---|
| K1 | Locality 4 promotion test | 5-step disqualification chain; "no plausible glob can be authored" required; sub-context globs explicitly considered |
| K2 | Deletion-candidate classes | Stale + redundant-up-the-ladder; mandatory per Locality 4 addition (unless trailer present) |
| K3 | What "stale" means | Cites missing file/symbol, closed issue, or superseded ADR — deterministic detection |
| K4 | Hook localities in scope | All 5 sub-localities (3a–3e); 3c uses `PostToolUse` + filter, not `postEdit` |
| K5 | Other `/chronicle *` subcommands (`tips`, `cost-tips`) | No redirect (already deterministic-flow-tightened in `copilot-instructions.md`) |
| K6 | Override block placement | First H2 under H1 title, ⚠️ emoji prefix, Locality 0 invariant comment block; CLI + VS Code in same block |
| K7 | Apply mode contract | `improve` dry-run emits report only; `--apply` mutates only items accepted; user accepts whole report OR selects items |
| K8 | Classifier algorithm | Hybrid: deterministic for "stale"; LLM-judgment for "redundant-up-the-ladder" with mandatory citation. Uncited claims dropped. |
| K9 | Non-`/chronicle` growth channels | Closed by Locality 3d pre-commit gate (**blocking on both `copilot-instructions.md` and `AGENTS.md`**, matrix-table carve-out for `AGENTS.md`) + Locality 3c PostToolUse advisory (warning). Multi-consumer reasoning per Decision Q3. |
| K10 | Novel Locality 4 escape hatch | `Locality-4-Justification: <reason>` git trailer with **1-in-10 rolling-window soft budget** (Decision Q10). Beyond budget, gate hard-fails until paired-deletion commit lands. Auditable via `git log --grep`. |
| K11 | Cross-surface output equivalence (Phase 7) | **CLI output canonical (Decision Q9);** VS Code disagreement files follow-up issues but does not block. Must-pass subset enforced on CLI only; ≥80% cross-surface overlap on findings beyond must-pass is a target, not a blocker. |
| K12 | Per-context Locality 1 destinations | Classifier prompt explicitly considers the 16 sub-context globs listed in Phase 4 — but **lazy creation only** (Decision Q8). No empty instruction files are pre-created. |
| K13 | Write lock for `--apply` writes outside `wiki/` | **Resolved at Phase 2 (Decision Q7):** new `.github/.customizations.lock` introduced in ADR-028. Sibling pattern to `wiki/.kb_write.lock` and `raw/.rejection-registry.lock`; never held simultaneously with either. |
| K14 | Two-file scope (vs HSI's one-file scope) | Both `.github/copilot-instructions.md` AND `AGENTS.md` are Locality 4. **Blocking on both (Decision Q3, revised):** `AGENTS.md` is cross-tool consumed (Antigravity IDE, Gemini CLI, etc.); growth vectors differ per consumer and only the Copilot-CLI-driven channel is measured in-repo. Write-surface matrix table is carved out. |
| K15 | Skill-corpus index for classifier prompt budget | Cache SKILL.md frontmatter + first paragraph only; invalidate on file mtime change. **Accepts false-negatives when body changes but first paragraph doesn't** (Decision Q11); self-correcting on next chronicle session. **Upgrade path monitored:** Phase 4 classifier emits a `cache_strategy: "mtime_first_para"` field on every redundancy finding; Phase 7 retro tallies false-negatives caught by the *next* chronicle session per quarter. If the running 90-day count crosses a threshold (proposed: ≥3 false-negatives where the missed redundancy cost ≥10 lines of Locality 4 growth before being caught), reconsider Option 3 (hybrid mtime + first-paragraph signature check). Threshold and signal columns added to Phase 7 acceptance log so the data accumulates without separate tracking. |
| K16 | Redirect mechanism (Phase 0) | **Mechanism A (meta-rule) is HSI-validated and ships unconditionally** (Decision Q2 revised). Mechanism B (UserPromptSubmit hook) is a Phase 0 spike enhancement — adopted as primary if it validates in CLI 1.0.60; dropped silently if not. Phase 0 outcome does NOT gate Phases 1–7. |
| K17 | `--apply` write blast radius | **Narrowed (Decision Q12):** create-only for `.github/instructions/**` + `.github/hooks/**`; modify-only for `copilot-instructions.md`, `AGENTS.md`, `.github/skills/audit-knowledgebase-workspace/**`. NEVER modifies another skill's files. Cross-skill findings route as `OutOfBand` to framework-engineer handoff. |
| K18 | Locality semantic axis | **Token-efficiency hierarchy (Decision Q5, revised).** Trigger-frequency is one *input* to the efficiency calculation `(trigger frequency × per-fire cost)`; the goal is not "find a low frequency" but "find the tier that minimizes expected token waste for the rule's actual usage pattern." Locality numbers remain monotonic for teachability; the per-turn / conditional cost columns on the ladder table show the trade-off explicitly. Ratchet prevention follows from the efficiency goal being honored, not the other way around. |

---

## Acceptance Criteria for the Whole Plan

The plan is **complete** when:

1. All 8 phases (Phase 0 through Phase 7) are `[x]`.
2. **Cross-surface portability:** `/chronicle improve` (CLI) and `/audit-knowledgebase-workspace improve` (VS Code) produce set-equivalent dry-run output on the same input — same `{source_file, source_section, proposed_destination, deletion_candidate}` tuple set, ≥80% overlap on findings beyond the must-pass subset.
3. **Must-pass classifier subset:** The dry-run report proposes a non-Locality-4 destination for each entry in the illustrative table (Phase 4 worked examples), with cited rationale. If even one is left at Locality 4, the spec or classifier has a gap.
4. **Deletion-pairing or trailer enforcement:** Every commit touching `copilot-instructions.md` or `AGENTS.md` (in non-exempt regions) either pairs a deletion or carries a `Locality-4-Justification:` trailer. Mechanically forced by Phase 6.
5. **Net shrinkage:** Both always-on files net-shrink after the first `improve --apply` run (proof the ratchet is broken). A structural consequence of (4), not a behavioral hope.
6. **Standing governance unbroken:**
    - Write-surface matrix rows present for every new logic surface and every new hook.
    - CONTEXT.md `last_updated` bumped in every affected domain.
    - All cascade-completeness tests pass.
    - ADR-028 is `Accepted` and indexed in `docs/decisions/README.md`.
    - Pre-commit hooks (existing + new) all pass on a clean tree.

## Out of Scope

- **Replacing other `/chronicle` subcommands** (`tips`, `cost-tips`). They are advisory/read-only; their deterministic-flow tightening already lives in `copilot-instructions.md` and stays put.
- **The `audit-knowledgebase-workspace` default flow's existing behavior.** Default flow is byte-identical to today; only the new `improve` flow is added.
- **Refactoring the 102-skill surface.** The classifier *reads* skills as a comparison corpus; it does not propose splitting, merging, or deleting skills (that's a separate concern owned by `skill-size-refactoring.md` and framework-engineer reviews).
- **CI workflow changes beyond `github-customizations-freshness` path additions.** No new workflows; no token-profile additions.
- **Wiki content rules.** This plan touches `.github/**` and root-level `AGENTS.md` only. `wiki/**` governance is unchanged.

## Known Risks

| Risk | Mitigation |
|---|---|
| Agent fails to honor hard-redirect meta-rule | **Mechanism A is HSI-validated in production**, so this risk is empirically retired. If Mechanism B also passes its Phase 0 spike, hook serves as belt-and-suspenders. Override block is first H2 (load-bearing placement; pre-commit invariant check in Phase 5) |
| `PostToolUse` payload format differs between surfaces | The `tool_input.files` field is documented for both; hook script normalizes by reading from stdin JSON or env vars |
| Classifier mis-tiers a signal | Dry-run is read-only + per-item user approval; `--apply` only mutates accepted items; redundancy claims require mandatory citations. Mistakes are reviewable before commit; Phase 6 gate blocks regressions |
| Classifier prompt cost blows up against 102-skill corpus | Phase 4 uses a cached frontmatter+first-paragraph index, not full bodies. Index refresh is one-shot per `.github/skills/` change |
| Locality 1 demotions create false sense of determinism | **Decision Q4 (revised):** CLI `applyTo:` is metadata-table-only; agent must `view` on demand. Phase 4 classifier emits `compliance_risk: "agent-dependent"` on every Locality 1 finding. Locality 0 (file comment) is the only deterministic demotion target |
| Frontmatter-less file in `.github/instructions/` becomes silent Locality 4 ratchet | Phase 1 pre-commit hook `check_instructions_applyto_present.py` blocks staging of any `.github/instructions/*.instructions.md` file missing `applyTo:` frontmatter |
| Pre-commit gate over-blocks legitimate edits | Escape hatch is the `Locality-4-Justification:` trailer; auditable so it doesn't normalize into a bypass |
| Two-file scope (Phase 6) misses the AGENTS.md write-surface matrix carve-out | Phase 6 explicitly exempts the `## Write-surface matrix` table body; cascade tests already enforce matrix rows exist for new surfaces |
| New `.github/.customizations.lock` proposal collides with future write surfaces | K13 is deferred to Phase 3 design; resolve before any `--apply` write code lands |
| ADR-028 collides with an in-flight ADR proposal | Last ADR in repo is ADR-027 (`infrastructure-validation-trigger-model`); 028 is currently unclaimed. Verify at Phase 2 kickoff |

---

## See Also

- `.github/skills/audit-knowledgebase-workspace/SKILL.md` — the skill being extended
- `.github/copilot-instructions.md` — primary always-on file (674 lines at 2026-06-07 baseline; ratcheting — current size will exceed this as slices land)
- `AGENTS.md` — secondary always-on file (110 lines at 2026-06-07 baseline; includes write-surface matrix; clean-window growth +3 before slice-2 override block landed)
- `docs/ideas/github-customizations-governance.md` — Implemented; established CONTEXT.md parity and freshness CI for `.github/**` (this plan builds on that scaffold but solves a different problem)
- `docs/ideas/skill-size-refactoring.md` — adjacent concern (skill bloat, not instruction bloat)
- `scripts/kb/github_customizations_graph.py` + `scripts/kb/github_customizations_freshness.py` — existing customization-surface tooling
- `.github/workflows/github-customizations-freshness.yml` — existing freshness CI
- HSI origin doc: `hot-springs-island/docs/planned-work/audit-workspace-improve-flow.md` (Locality 0/1/2/3 vocabulary, 5-step disqualification chain, deletion-candidate model)
- VS Code customization docs:
    - <https://code.visualstudio.com/docs/agent-customization/custom-instructions>
    - <https://code.visualstudio.com/docs/agent-customization/agent-skills>
    - <https://code.visualstudio.com/docs/agent-customization/hooks>
- Agent Skills open standard: <https://agentskills.io>

---

## Appendix A — `grill-with-docs` decision log (2026-06-07)

This plan was revised via the `grill-with-docs` skill in autopilot mode. The user was unavailable; the agent posed 12 questions, adopted its own recommended answers, and applied them as edits. Every decision is reversible — the user can override any of them by editing the plan and the corresponding section.

| # | Question | Decision | Reversal cost |
|---|---|---|---|
| Q1 | Is the "+2398/−77 in 6 months" framing accurate? | **Reframed.** Rewrote Background with sharper May→June data (+201 lines in `copilot-instructions.md` only; AGENTS.md flat +3). 3-channel inventory (chronicle 24%, post-feat-work session-capture 72%, anomalous auto-checkpoint 1 commit). | Low — Background is prose-only |
| Q2 | Why rely on agent compliance with a meta-rule when `UserPromptSubmit` is mechanically deterministic? | **Mechanism A is HSI-validated and ships unconditionally** (revised per user input). Mechanism B is a Phase 0 spike enhancement — adopted as primary if it validates; dropped silently if not. Phase 0 is no longer load-bearing. | Low — Phase 0 narrowed; A unconditional |
| Q3 | Is AGENTS.md actually always-on in CLI? | **Treat as always-on, blocking gate** (revised per multi-consumer evidence). `AGENTS.md` is consumed by Antigravity IDE, Gemini CLI, and other tools following the `AGENTS.md` filename convention. The "+3 clean-window" measurement only reflects Copilot-CLI-driven growth; lowering urgency would create a blind spot for non-CLI consumers. Phase 6 gates both files at blocking with matrix-table carve-out on `AGENTS.md`. | Low — Phase 6 default flips (both blocking) |
| Q4 | Does CLI honor `applyTo:` globs? | **Confirmed by CLI source code** (`app.js` function `BXo`): yes, but as a **metadata-table mechanism**, not a content-loader. Agent must `view` the file on demand. Locality 1 inherits Locality-2-equivalent compliance shape (Decision Q4 revised). Phase 1.5 spike repurposed to **empirically measure agent compliance rate**. Phase 1 adds required-`applyTo:` pre-commit hook (frontmatter-less files become silent Locality 4 ratchet). Phase 4 classifier emits `compliance_risk` field on every demotion. Cursor `.mdc` files documented as sidebar. | High — sidebar added to ADR-028; classifier schema adds `compliance_risk` field; new pre-commit hook in Phase 1 |
| Q5 | Does the ladder conflate "where rule lives" with "when rule fires"? | **Reframed as token-efficiency hierarchy** (revised per user goal statement). Ladder table grows a "Token cost per turn" + "Conditional cost when triggered" column pair making the trade-off scannable. Disqualification chain becomes a 5-step **efficiency check** with token-minimization framing. ADR-028 purpose flips from "prevent ratchet" to "guide humans+agents to JIT progressive disclosure for token efficiency; ratchet prevention is consequence." Phase 4 classifier optimizes `(trigger frequency × per-fire cost)` and emits `expected_token_efficiency_rank` field. K18 retitled to "Token-efficiency hierarchy." | Medium — Goals + ladder table + section heading + ADR purpose + classifier schema |
| Q6 | Matrix row for a stub overstates write capability. | **Split matrix-row landing across Phase 3 (read-only) + Phase 4 (amend with apply write paths).** | Low — Phase 3/4 row text |
| Q7 | K13 lock decision blocks Phase 3, not deferred to it. | **Resolved in Phase 2 (ADR-028).** New `.github/.customizations.lock` follows sibling pattern. | Medium — touches ADR + init.py + contracts.py |
| Q8 | Pre-create 16 instruction files for known sub-contexts? | **No. Lazy creation only.** Classifier proposes new files on demand. | Low — Phase 1/4 text only |
| Q9 | Cross-surface portability: who wins on disagreement? | **CLI canonical** (it's the ratchet surface). VS Code disagreement files follow-up issues. | Low — Phase 7 acceptance clarification |
| Q10 | Trailer escape has no rate limit. | **1-in-10 rolling-window soft budget.** Beyond budget, gate hard-fails until paired-deletion commit. | Medium — adds check_locality_ratchet.py logic |
| Q11 | Skill-corpus cache may miss redundancy when body changes but first paragraph doesn't. | **Accept false-negatives + monitor upgrade path** (revised per user input). Self-correcting on next chronicle session. Phase 4 classifier emits `cache_strategy` field; Phase 7 retro tracks false-negative count per quarter so Option 3 (hybrid signature check) becomes a data-driven trigger, not a guess. | Low — Phase 4 documentation + Phase 7 retro field |
| Q12 | `--apply` matrix row allows writing other skills' SKILL.md files. | **Narrowed.** `--apply` may CREATE under `.github/instructions/**` + `.github/hooks/**`; MODIFY only `copilot-instructions.md`, `AGENTS.md`, `.github/skills/audit-knowledgebase-workspace/**`. Cross-skill findings route as `OutOfBand` to framework-engineer. | Medium — Phase 3/4 matrix rows + classifier OutOfBand routing |

### Codebase facts gathered during grilling (data the plan now stands on)

- `copilot-instructions.md` line history: 73 (Apr-15) → 473 (May-15) → 674 (Jun-7).
- Skill count history: 21 (Apr-15) → 102 (May-15) → 102 (Jun-7). Skill growth has been flat for ~3 weeks; instruction growth has not.
- `AGENTS.md` line history: clean-window May→Jun net +3 (Copilot-CLI-driven only; Antigravity IDE / Gemini CLI growth channels not measured in-repo).
- Existing lock files: `wiki/.kb_write.lock`, `raw/.rejection-registry.lock`. Both follow ADR-005 semantics. New `.github/.customizations.lock` follows the same pattern.
- `scripts/init.py` REPO_ROOT sentinel includes `AGENTS.md` — confirming functional always-on status.
- "Checkpoint from Copilot CLI" commits: **1 in 6 months.** Not a channel.
- Pre-commit hook precedent in this repo: `scripts/hooks/check_adr_cross_ref.py`, `check_stub_archive_path.py`, `check_context_md_format.py` — `check_locality_ratchet.py` joins this family at the `pre-commit` stage; `check_locality_justification_trailer.py` is the first repo hook to run at the `commit-msg` stage and requires `pre-commit install --hook-type commit-msg` on contributor machines.

### Unresolved questions deferred to implementation

- Phase 0 (B spike) outcome dictates Phase 5 mechanism mix (A+B vs A-only). Mechanism A always ships.
- Phase 1.5 outcome dictates Locality 1's availability across surfaces. Cannot pre-decide.
- Exact rolling-window definition for the trailer budget (commits-touching-target-files vs all commits) — tune during Phase 6 implementation based on observed false-positive rate.

### CONTEXT.md term additions (landed early in slice 2 / #192 with `ADR-028 (pending)` hedges)

The grilling pass surfaced four new repo-specific terms that have **already been added** to `.github/skills/CONTEXT.md` as part of slice 2 / #192, with each entry hedged as `(introduced in ADR-028 — pending issue #190)` so the cross-reference stays accurate until the ADR is `Accepted`. When ADR-028 lands in Phase 2 and the status flips to `Accepted`, the same commit must remove the `(pending)` hedges and bump `last_updated` in `CONTEXT.md`. Canonical definitions (used both for the on-disk entries and as the ADR-028 author's reference):

| Term | Definition for CONTEXT.md |
|---|---|
| **instruction ratchet** | The pattern where always-on instruction files (e.g., `.github/copilot-instructions.md`) grow monotonically add-only, decoupled from customization-surface growth. Measured by net line change in a window where skill count is flat. |
| **Locality** | A trigger-frequency ordinal for instruction destinations (Locality 0–4); frequency increases monotonically. Locality 4 = every turn (always-on); Locality 0 = only when a single file is read. See ADR-028. |
| **trailer soft budget** | The rolling-window cap on `Locality-4-Justification:` git trailers (default 1 per 10 commits to global rules sections) that prevents the escape hatch from normalizing into bypass. Enforced by `scripts/hooks/check_locality_justification_trailer.py` at the `commit-msg` stage (paired with the pre-commit `check_locality_ratchet.py` line-delta check). |
| **customizations lock** | The file `.github/.customizations.lock` — concurrency guard for `--apply` mode writes to `.github/**` (introduced in ADR-028). Sibling to `wiki/.kb_write.lock` and `raw/.rejection-registry.lock`; never held simultaneously with either. |

On Phase 2 ADR-028 acceptance, the cascade is: (a) drop `(pending)` hedges in each CONTEXT.md entry above, (b) bump `last_updated` in `.github/skills/CONTEXT.md`, (c) `tests/kb/test_adr_readme_status_sync.py` and `check_adr_cross_ref.py` will catch any forgotten hedge.
