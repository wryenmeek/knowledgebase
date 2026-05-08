---
name: verified-research
description: "Produces research reports with built-in adversarial verification of every claim before inclusion. Use when conducting comparative analysis, codebase research, or any investigation where accuracy matters more than speed."
---

# Verified Research

## Overview

Research skill that applies a RED→GREEN verification cycle to every claim before it enters the report. Inline verification phases catch 7 systematic error types before they compound into thesis-level failures.

## When to Use

- Comparative analysis across repos, systems, or approaches
- Investigating unfamiliar codebases or academic literature
- Any research where the report will inform decisions or be cited later
- When accuracy and verifiability matter more than speed

## Procedure

### Phase 1 — Scope (RED)

Define the research boundary before collecting anything:

1. State the research questions explicitly.
2. List known sources (repos, papers, docs, APIs).
3. Identify what you do NOT know — produce a typed gap list.
4. State your working thesis as a **hypothesis**, not a conclusion.

### Phase 2 — Collect (GREEN)

Fill gaps from **primary sources only**:

1. For each source: explore the **full directory tree** — hooks/, rules/, tooling/, tests/, config — not just skills/ or src/.
2. Every factual claim gets an exact citation (file:line, URL, or API response).
3. Every number is verified at the primary source (API for citations, directory listing for counts).
4. Check publication/deprecation status of every artifact cited.

### Phase 3 — Verify (inline adversarial)

Before any claim enters the report, apply the **7-error checklist**:

| # | Error type | Check |
|---|-----------|-------|
| 1 | **Inflated statistics** | Is this number from the primary source or from memory? Verify at API/file. |
| 2 | **Misattributed framing** | Is this what the source says, or my interpretation? Label analytical frames explicitly. |
| 3 | **Missing counter-examples** | For every "all X do Y" claim — have I searched for exceptions in the same dataset? |
| 4 | **Omitted infrastructure** | Did I explore ALL top-level directories in each source, or just the obvious ones? |
| 5 | **Status confusion** | Is this artifact published, draft, deprecated, or personal? Check markers. |
| 6 | **Academic mischaracterization** | Is this a completed study or a protocol/proposal? Check tense and methodology. |
| 7 | **Recommending existing features** | Does the target already implement this? Check before recommending. |

### Phase 4 — Hunt counter-examples

For each comparative or universal claim:

1. Search the same source for evidence that **contradicts** the claim.
2. If counter-examples exist, either qualify the claim or remove the universality.
3. Document counter-examples in the report — they strengthen credibility.

### Phase 5 — Scan omissions

Before synthesis, ask:

1. What directories/files in each source did I NOT examine?
2. What published artifacts are missing from my analysis?
3. Are there cross-references between sources I haven't checked? (attribution lines, import statements, citations)
4. Does my thesis survive the attribution check? (Are repos truly independent, or does one cite the other?)

### Phase 6 — Audit framing

Review the draft for analytical honesty:

1. Separate "source says" from "I observe" — use explicit labels.
2. Mark analogies as analogies, not established knowledge.
3. State the thesis as supported-by-evidence, not proven-by-evidence.
4. Attach a confidence level (Very High / High / Medium / Low) to each major claim.

### Phase 7 — Synthesize

Produce the report with: a **lineage section** (derivation vs. convergence vs. independent), **per-claim citations** (file:line or URL), a **confidence table** (Very High / High / Medium / Low per major claim), **counter-examples included**, and **analytical frames labeled** ("this report's characterization" vs. "the source's term").

## Verification

1. Every statistic traces to a primary source (not model memory).
2. No universal claim lacks a counter-example search.
3. Recommendations have been feasibility-checked against the target.
4. The thesis survives the attribution/cross-reference check.
5. Analytical frames are labeled, not presented as source claims.

## Anti-patterns

- **Single-pass research** — collect and synthesize without verification.
- **Confirmation-only collection** — gathering only supporting evidence.
- **Memory-sourced numbers** — counts and versions from model memory are wrong more often than right.
- **Thesis-before-evidence** — concluding before checking for attribution or derivation between sources.

> Doc-only workflow. Informed by adversarial validation of `docs/research/context-solicitation-skill-design-patterns.md`.
