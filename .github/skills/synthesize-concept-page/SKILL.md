---
name: synthesize-concept-page
description: Drafts a policy-cleared concept wiki page from a verified evidence package. Use when evidence-verifier and policy-arbiter have cleared a source intake for concept synthesis, and the synthesis-curator persona must produce a schema-aligned page draft.
---

# Synthesize Concept Page

## Overview

This skill documents the concept-page synthesis step for the `synthesis-curator` persona.
It has an executable logic directory (`logic/synthesize_concept_page.py`) that is invoked
by the CI-3 PR Producer workflow. The script acquires `wiki/.kb_write.lock`, then either
creates new `wiki/concepts/<slug>.md` draft pages or appends to existing ones
(append-only: new SourceRef + open_questions; existing prose is never overwritten).

Concepts describe recurring ideas, policies, or patterns — not unique real-world entities.

**Blocking-only with narrow write capability.** Has `logic/` dir for CI-3 synthesis stage.

## Classification

- **Mode:** Blocking-only with narrow write capability
- **MVP status:** Active
- **Execution boundary:** Direct write to `wiki/concepts/**` while holding
  `wiki/.kb_write.lock`. New pages are created from the extraction bundle;
  existing pages receive append-only updates only.

## When to Use

- `evidence-verifier` has confirmed provenance completeness for the source package
- `policy-arbiter` has cleared the package for concept synthesis
- A recurring idea, category, or definition needs a canonical wiki page
- The `synthesis-curator` lane needs a stable workflow reference for concept drafting

## Contract

- Input: extraction bundle JSON produced by `extract_entities.py`
- Output: `wiki/concepts/<slug>.md` pages (created or updated)
- Lock: acquires `wiki/.kb_write.lock` before any wiki write; releases on completion
- Skip: soft-skipped bundles produce no writes; ambiguous matches and slug collisions
  are skipped (logged to stderr) and counted in the results dict

## Assertions

- No concept page is written without a valid extraction bundle
- `wiki/.kb_write.lock` is held for the entire write batch
- New page slugs that collide with existing files are skipped (fail-closed)
- Ambiguous dedup matches (>1 candidate) are skipped (fail-closed)
- The page type must be `concept` — do not use this skill for entity pages

## Procedure

### Step 1: Read extraction bundle

Load the JSON bundle from `extract_entities.py`. If `soft_skipped: true`, exit cleanly.

### Step 2: Acquire wiki write lock

Call `exclusive_write_lock` under `wiki/.kb_write.lock`. Fail closed if lock unavailable.

### Step 3: Scan existing concept pages

Scan `wiki/concepts/*.md` for dedup candidates using `scan_existing_pages`.

### Step 4: For each concept — create or update

- If >1 dedup match: skip, log to stderr.
- If 1 match: call `append_to_existing_page` (SourceRef + open_questions only).
- If 0 matches: check for slug collision; skip if slug file exists; otherwise create
  with `write_text_capturing_previous_safe`.

### Step 5: Release lock

Lock is released when the `with exclusive_write_lock(...)` block exits.

## Boundaries

- Write path is limited to `wiki/concepts/**` while holding `wiki/.kb_write.lock`
- Do not read source files directly — use the extraction bundle only
- Do not merge or edit existing concept prose
- Do not open any secondary write path for entities, index, or log inside this script

## Verification

- [ ] Extraction bundle loaded and parsed successfully
- [ ] `wiki/.kb_write.lock` was acquired before any write
- [ ] All created pages pass `validate_draft_frontmatter`
- [ ] Ambiguous and slug-collision cases are skipped with stderr log
- [ ] Lock released after batch completes

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `schema/page-template.md`
- `schema/taxonomy-contract.md`
- `schema/metadata-schema-contract.md`
- `.github/agents/synthesis-curator.md`
