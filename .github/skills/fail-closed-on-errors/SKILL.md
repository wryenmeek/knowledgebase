---
name: fail-closed-on-errors
description: Enforces fail-closed behavior when any step in a governed wiki workflow encounters an error, partial result, or missing prerequisite. Use when knowledgebase-orchestrator must stop a workflow sequence rather than allow incomplete or inconsistent state to propagate.
---

# Fail Closed on Errors

## Overview

This skill documents the fail-closed enforcement step for the `knowledgebase-orchestrator`
persona. When any governed workflow step produces an error, a partial result, or a
missing prerequisite, this skill ensures that downstream lanes do not open and that
the error is surfaced explicitly rather than silently bypassed. Fail-closed is the
default posture: any ambiguity stops the workflow and routes to human steward review.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Workflow-stop enforcement only. No write path is opened
  by this skill.

## When to Use

- Any step in a governed wiki workflow returns an error, partial result, or missing
  prerequisite
- `knowledgebase-orchestrator` must decide whether to retry, escalate, or halt
- A validator, linter, or intake check fails and downstream lanes must not proceed
- An operator needs to confirm that fail-closed behavior is correctly enforced
  before resuming a workflow

## Contract

- Input: the error or partial result from a prior step, the workflow context, and
  any available stop-condition flags
- Output: a structured stop record specifying the failed step, the error type,
  and the required recovery action (retry, escalate, or halt)
- Handoff: halt decisions route to human steward; recoverable errors route back
  through the appropriate lane with a revised plan

## Assertions

- Ambiguous or partial results always halt the workflow rather than proceeding
  with incomplete state
- No downstream write lane opens after a fail-closed stop
- The stop record must cite the specific error and failed step
- Silent bypass of errors is never permitted, even for low-severity findings on
  non-protected paths

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `.github/agents/knowledgebase-orchestrator.md`
