---
name: record-open-questions
description: Captures unresolved evidence or policy gaps in a reusable, schema-aligned form. Use when a wiki page, draft, or review cannot safely close a question without escalation or later follow-up.
---

# Record Open Questions

## Overview

Use this skill when the right outcome is to preserve uncertainty rather than hide
it. In MVP it is a doc-only workflow that structures unresolved questions for
page frontmatter, handoff artifacts, and later governance review without making
unsupported decisions on the system's behalf.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Structured documentation and handoff only. Do not
  resolve uncertainty by speculation or invent new persistence surfaces.

## When to Use

- Evidence is incomplete but still worth preserving as an open question
- Policy review blocks a conclusion that cannot be safely forced
- A draft needs schema-aligned `open_questions` content
- A handoff artifact must tell the next reviewer what remains unresolved
- Human stewardship is required before durable follow-up can continue

## Contract

- Input: one unresolved question plus its affected page, evidence context, and
  blocking reason
- Output: a schema-aligned open-question record with concise wording, why it is
  unresolved, and what follow-up is required
- Persistence rule: questions belong in existing page metadata or governed
  handoff artifacts, not ad hoc ledgers
- Handoff rule: unresolved blocking questions route to the next governance lane
  or a human steward rather than being guessed away

## Assertions

- Open questions are concrete, scoped, and tied to evidence or policy gaps
- The skill preserves uncertainty without implying a resolved answer
- Question wording fits existing metadata and page-template contracts
- Blocking questions remain visible to downstream governance review
- No new runtime, queue, or external tracker is introduced from this skill

## Procedure

### Step 1: Isolate the unresolved issue

State exactly what is unknown, disputed, or blocked, and identify the affected
page, claim, or decision.

### Step 2: Capture why it is unresolved

Record the evidence gap, policy conflict, or authority boundary that prevents a
safe resolution today.

### Step 3: Write the smallest reusable question

Phrase the question so it can live in page metadata or a handoff artifact without
needing surrounding prose to remain understandable.

### Step 4: Route the follow-up

Specify the next governance lane or human decision needed before the question can
be closed.

## Boundaries

- Do not convert open questions into hidden TODO prose outside the governed
  schema
- Do not pretend a blocking issue is merely advisory when it stops safe progress
- Do not create a parallel persistence store for unresolved questions in MVP
- Do not answer the question speculatively just to unblock automation

## Verification

- [ ] Question text is concrete and schema-aligned
- [ ] The blocking reason is explicit
- [ ] Follow-up ownership is named
- [ ] Uncertainty is preserved instead of guessed away
- [ ] No unsupported persistence surface is introduced

## References

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md)
- [`schema/page-template.md`](../../../schema/page-template.md)
- [`raw/processed/SPEC.md`](../../../raw/processed/SPEC.md)
