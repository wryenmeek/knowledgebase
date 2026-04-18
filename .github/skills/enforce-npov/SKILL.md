---
name: enforce-npov
description: Applies neutral-point-of-view and attribution policy to evidence-backed wiki work. Use when reviewing a draft, plan, or synthesis for due weight, unsupported inference, or contradiction handling.
---

# Enforce NPOV

## Overview

Use this skill to apply the repository's editorial constitution before any
durable follow-up advances. In MVP it is a doc-only workflow: assess due weight,
attribution, unsupported inference, and contradiction handling, then route the
result to the correct policy or escalation lane.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Policy review and handoff only. Do not silently rewrite
  contested content, approve original research, or bypass explicit escalation.

## When to Use

- A draft or proposed update needs neutral-point-of-view review
- Evidence could be overclaimed, under-attributed, or framed with the wrong due
  weight
- A change introduces unsupported inference or original research risk
- Conflicting sources or existing pages require an explicit policy outcome
- Governance must decide whether content can proceed, needs revision, or must be
  escalated

## Contract

- Input: evidence-backed draft text, synthesis notes, or a proposed wiki plan
- Decision model: classify the outcome as `allow`, `revise`, or `escalate`
  according to NPOV and contradiction rules
- Output: a policy finding with due-weight notes, attribution gaps,
  contradiction handling, and next action
- Handoff rule: revision requests return to the governed upstream lane;
  escalations produce open questions or conflict records instead of forced merges

## Assertions

- Claims must remain attributable to cited evidence with appropriate due weight
- Unsupported synthesis or original research is blocking
- Contradictions trigger explicit handling rather than silent overwrite behavior
- The skill never authorizes direct wiki writes on its own
- Policy ambiguity routes to escalation rather than guesswork

## Procedure

### Step 1: Review the evidence-backed claim set

Read the proposed draft, synthesis, or plan alongside the cited evidence and any
relevant existing pages or summaries.

### Step 2: Check neutral presentation

Evaluate whether the framing, emphasis, and attribution reflect the available
evidence instead of the editor's preferred narrative.

### Step 3: Check for unsupported inference

Look for synthesis leaps, omitted attribution, or claims that exceed what the
cited evidence can support.

### Step 4: Classify the policy outcome

Use one of three outcomes only:

- **allow**: policy concerns are satisfied for the next governed step
- **revise**: attribution or weighting gaps must be corrected upstream
- **escalate**: contradiction or ambiguity requires explicit arbitration

### Step 5: Route the follow-up

Return revision notes, open questions, or conflict-log recommendations without
forcing a merge or publication path open.

## Boundaries

- Do not treat stylistic preference as a policy violation without evidence
- Do not resolve contradictory sources by deleting one side silently
- Do not approve content that introduces unsupported original research
- Do not bypass policy logging or open-question follow-up when ambiguity remains

## Verification

- [ ] Due weight and attribution are explicitly reviewed
- [ ] Unsupported inference is separated from evidence-backed synthesis
- [ ] Contradictions produce a clear revise or escalate outcome
- [ ] The result does not authorize direct wiki writes by itself
- [ ] Remaining ambiguity is preserved for governance follow-up

## References

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`docs/ideas/wiki-curation-agent-framework.md`](../../../docs/ideas/wiki-curation-agent-framework.md)
- [`raw/processed/SPEC.md`](../../../raw/processed/SPEC.md)
- [`schema/page-template.md`](../../../schema/page-template.md)
