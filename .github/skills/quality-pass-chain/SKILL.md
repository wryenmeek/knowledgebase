---
name: quality-pass-chain
description: "Runs the post-implementation quality pass in the correct order. Use when completing a non-trivial implementation before merge. Four-step development gate: code-review-and-quality → code-simplification → test-driven-development → documentation-and-adrs. shipping-and-launch is a separate pre-deployment gate."
---

# Quality Pass Chain

## Overview

Orchestrates the post-implementation quality pass. Later passes often expose issues the earlier ones miss — run in order, don't skip steps.

## When to Use

- After completing a non-trivial implementation, before merge
- When multiple quality skills need to run in the right order
- Any change that touches more than documentation

Doc-only workflow.

## Development Quality Gate

Run these four steps sequentially after completing implementation:

### Step 1: `code-review-and-quality` — REQUIRED

Correctness, security, architecture. Block merge if findings warrant.

### Step 2: `code-simplification` — RECOMMENDED

Clarity, dead code, loop invariants. Non-blocking, but address obvious issues before moving on.

### Step 3: `test-driven-development` — REQUIRED

Coverage gaps and edge cases. **Address gaps in the SAME commit** — test coverage gaps are first-class review findings, not follow-up housekeeping.

### Step 4: `documentation-and-adrs` — REQUIRED

SKILL.md, architecture.md, README.md, docstrings. Block merge if ADRs are incomplete for decisions made during implementation.

## Pre-Deployment Gate (separate)

`shipping-and-launch` runs before merge to the production branch. It covers the pre-launch checklist, monitoring setup, and rollback plan. This is **NOT** step 5 of the development quality pass — it is a separate gate that runs at deployment time.

## Why this order?

Code review finds bugs → simplification makes fixes clearer → tests codify the fixes → docs record the decisions. Each pass feeds the next.

## When to skip steps

| Change type | Skip |
|---|---|
| Bug-fix only | May skip `code-simplification` |
| Documentation only | May skip all but `documentation-and-adrs` |
| Schema/contract change | Run full chain — no skips |
| New surface or skill | Run full chain — no skips |

Use judgment, but err on the side of running the full chain. Skipping a step that would have caught an issue is more expensive than running an unnecessary pass.

## Integration with existing guidance

This skill codifies the "Post-implementation quality-pass order" from the project instructions. The order and rules here are canonical — if they diverge from inline comments elsewhere, this skill governs.
