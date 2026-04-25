---
name: grill-me
description: "Stress-tests a plan, spec, or decision through relentless one-at-a-time questioning. Use when validating assumptions, when a plan needs adversarial review, or before committing to a spec. Walks every decision branch until all are resolved."
---

# Grill Me

## Overview

Adversarial interview that stress-tests decisions before they become specs. One question at a time — never batch. The griller recommends its own answer to each question so the conversation stays productive.

## When to Use

- Before `spec-driven-development` or after `idea-refine`
- When a plan has unexamined assumptions or needs adversarial validation
- Before committing to a contract change in `schema/`

## Procedure

1. The user (or upstream agent) presents a plan, spec draft, or decision.
2. The griller identifies the weakest or most ambiguous point.
3. The griller asks **ONE question** about that point.
4. The griller proposes what it thinks the answer should be — with reasoning.
5. The user confirms, corrects, or explores further.
6. Repeat from step 2 until no unresolved branches remain.

### Output

A decision log of all Q&A pairs:
```
Q1: [question]
  Proposed: [griller's recommendation]
  Resolved: [final answer]

Q2: ...
```

This log feeds directly into `spec-driven-development` as resolved decisions.

## Gate

All decision branches must be resolved before spec work begins. If the user answers "I don't know" to a question, that becomes an **explicit open question** in the spec — not a silent assumption.

## Anti-patterns

- **Batching questions** — one at a time forces depth.
- **Accepting vague answers** — push for specifics or escalate to open question.
- **Skipping the proposal** — always recommend an answer; it anchors discussion.

> Doc-only workflow. Adapted from mattpocock/skills `grill-me`. Focused on plan/decision stress-testing.
