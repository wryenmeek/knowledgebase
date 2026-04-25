---
name: edit-article
description: "Improves prose clarity and structure of wiki pages without altering factual content or citations. Use when content is factually correct but reads as AI-generated or is unclear, after detect-ai-tells and enforce-npov have passed. Prose-only: restructure, tighten, clarify."
---

# Edit Article

## Overview

Prose restructuring pass — improve clarity, flow, and readability. This skill assumes factual correctness and NPOV compliance have already been verified. It is NOT a validation skill.

## When to Use

- After `detect-ai-tells` and `enforce-npov` have passed
- When wiki page prose reads as AI-generated or monotone
- When content is factually correct but unclear or verbose

Doc-only workflow.

## Prerequisites

- `detect-ai-tells` ✓ — AI generation markers resolved
- `enforce-npov` ✓ — attribution and due weight verified

Do not run this skill until both prerequisites have passed.

## What this skill does

- Tighten verbose phrasing
- Reduce passive voice
- Eliminate redundancy
- Improve paragraph flow and transitions
- Restructure sentences for clarity
- Vary sentence cadence to avoid monotone rhythm

## What this skill does NOT do

- No fact-checking
- No citation verification
- No NPOV assessment
- No frontmatter changes
- No adding or removing factual content

## Hard constraints

1. **ALL SourceRef citations must be preserved exactly** — no rewording, no relocation relative to their claim.
2. **Frontmatter must not be modified.**
3. **No new claims may be introduced.**
4. **No existing claims may be removed or weakened.**
5. **Section headings may be reworded for clarity but not reordered.**

## Verification

After applying edits, verify:
1. `git diff` shows zero changes to lines containing `repo://` (SourceRef preservation).
2. `git diff` shows zero changes inside the YAML frontmatter block (frontmatter preservation).
3. No new sentences introduce factual claims absent from the original (no new claims).
4. No original sentences containing factual claims are deleted (no claim removal).
5. Section heading order in the table of contents is unchanged (heading order preservation).

## Workflow position

Run AFTER `detect-ai-tells` and `enforce-npov`. Typically the last prose pass before publication. If edits are substantial enough to re-trigger AI-tells concerns, re-run `detect-ai-tells` on the result.

> Adapted from mattpocock/skills `edit-article`. KB variant narrows to prose-only restructuring to avoid overlap with existing validation skills.
