---
name: validate-inbox-source
description: Validates raw inbox material against the repository ingest boundary. Use when checking whether a candidate source can enter the governed intake lane before provenance registration or synthesis.
---

# Validate Inbox Source

## Overview

Use this skill at the untrusted-source boundary before any intake package moves
forward. In MVP it is primarily a workflow contract: verify that a candidate
artifact is in the right zone, has enough deterministic metadata to proceed,
and routes back to governed intake instead of being normalized ad hoc. The
attached helper stays read-only and validates declarative source registries
without opening a broader ingest runtime.

## Classification

- **Mode:** Workflow contract with attached deterministic helper
- **MVP status:** Active
- **Execution boundary:** Assessment, handoff, and read-only registry validation
  only. Do not mutate inbox material, invent new ingest paths, or bypass the
  governed intake lane.

## When to Use

- New material appears under `raw/inbox/`
- A request wants to ingest source content from an unexpected path
- A reviewer needs to decide whether a candidate artifact is intake-ready
- Provenance prerequisites are incomplete and the intake lane must fail closed
- Intake work needs a deterministic accept, reject, or escalate outcome

## Contract

- Input: a candidate artifact path plus any available source metadata
- Decision model: classify the candidate as `accept`, `reject`, or `escalate`
  for the governed intake lane
- Output: a short intake decision with boundary findings, missing prerequisites,
  and next required handoff
- Handoff rule: accepted candidates proceed to provenance registration and
  evidence review; rejected or ambiguous candidates stop without mutation

## Assertions

- Only material staged in `raw/inbox/` is eligible for this workflow
- Validation fails closed when source type, placement, or provenance metadata is
  incomplete
- The skill does not rewrite, normalize, or relocate the source itself
- Any durable ingest follow-up stays inside the existing knowledgebase control
  plane
- No shell, eval, or dynamic dispatch is introduced from this skill

## Commands

```bash
python3 .github/skills/validate-inbox-source/logic/validate_source_registry.py --path raw/processed/example.source-registry.json
```

## Procedure

### Step 0: Check rejection registry

Compute the `sha256` checksum of the candidate source bytes. Check `raw/rejected/`
for a record with a matching `sha256` frontmatter field.

- **Match found, `reconsidered_date` is null:** Surface the prior rejection to
  the operator: "This source was rejected on [date] because [reason]. Has
  anything changed? Proceed or close?" If the operator proceeds, route through
  `reconsider-rejected-source`. If the operator closes, stop.
- **Match found, `reconsidered_date` is set (non-null):** This source was
  previously reconsidered and may have been rejected again (same `sha256`). Surface both the
  original rejection and the reconsideration date: "This source was rejected on
  [date], reconsidered on [reconsidered_date], and rejected again. Significant
  new evidence is required to proceed." Route through
  `reconsider-rejected-source` only with explicit operator justification.
- **No match:** Continue to Step 1.

### Step 1: Confirm boundary placement

Verify that the candidate is staged under `raw/inbox/` and has not already been
moved into immutable storage.

### Step 2: Check deterministic intake prerequisites

Review the ingest checklist, source metadata, and any repository guardrails that
must be satisfied before provenance registration or synthesis begins.

### Step 3: Classify the intake outcome

Use one of three outcomes only:

- **accept**: candidate is correctly placed and intake-ready
- **reject**: candidate violates the boundary or lacks required prerequisites
- **escalate**: ambiguity remains and a human steward must decide

### Step 4: Prepare the handoff

Return the relevant path, boundary findings, missing prerequisites, and the next
lane such as provenance registration, evidence verification, or human review.

## Boundaries

- Do not ingest directly from paths outside `raw/inbox/`
- Do not alter source bytes during validation
- Do not create shadow manifests or sidecar state outside the governed flow
- Do not treat provisional evidence as intake-ready when required metadata is
  missing

## Verification

- [ ] Rejection registry check performed before intake proceeds
- [ ] Candidate path is checked against the inbox boundary
- [ ] Intake outcome is `accept`, `reject`, or `escalate`
- [ ] Missing provenance prerequisites are explicit
- [ ] Accepted work routes back to governed intake rather than direct drafting
- [ ] The workflow remains read-only and fail-closed

## References

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`raw/processed/SPEC.md`](../../../raw/processed/SPEC.md)
- [`schema/ingest-checklist.md`](../../../schema/ingest-checklist.md)
- [`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md)
- [`schema/rejection-registry-contract.md`](../../../schema/rejection-registry-contract.md)
- [`docs/decisions/ADR-013-rejected-source-registry.md`](../../../docs/decisions/ADR-013-rejected-source-registry.md)
