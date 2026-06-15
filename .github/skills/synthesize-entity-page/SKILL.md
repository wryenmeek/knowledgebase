---
name: synthesize-entity-page
description: Drafts a policy-cleared entity wiki page from a verified evidence package. Use when evidence-verifier and policy-arbiter have cleared a source intake for entity synthesis, and the synthesis-curator persona must produce a schema-aligned page draft.
---

# Synthesize Entity Page

## Overview

This skill documents the entity-page synthesis step for the `synthesis-curator` persona.
Its executable logic directory includes both `logic/synthesize_entity_page.py`
(standalone entity-only entry point) and `logic/synthesize_combined.py`
(CI-3 entry point). CI-3 uses `synthesize_combined.py` to acquire
`wiki/.kb_write.lock` once, then synthesize entity and concept drafts inside
the same critical section. Entity page behavior remains append-only on updates
(new SourceRef + open_questions; existing prose is never overwritten).

**Blocking-only with narrow write capability.** Has `logic/` dir for CI-3 synthesis stage.

## Classification

- **Mode:** Blocking-only with narrow write capability
- **MVP status:** Active
- **Execution boundary:** Standalone `synthesize_entity_page.py` writes
  `wiki/entities/**` while holding `wiki/.kb_write.lock`. CI-3's
  `synthesize_combined.py` (same logic directory) writes `wiki/entities/**` and
  `wiki/concepts/**` under one lock acquisition.

## When to Use

- `evidence-verifier` has confirmed provenance completeness for the source package
- `policy-arbiter` has cleared the package for entity synthesis
- The `synthesis-curator` lane needs a stable workflow reference for entity drafting
- A new real-world entity (person, organization, program, policy) needs a canonical page

## Contract

- Input: extraction bundle JSON produced by `extract_entities.py`
- Output: `wiki/entities/<slug>.md` pages (created or updated); CI-3 combined
  flow also writes `wiki/concepts/<slug>.md`
- Lock: standalone acquires `wiki/.kb_write.lock` before entity writes; CI-3
  combined flow acquires once and reuses it for entity + concept writes.
  Programmatic callers that already hold `wiki/.kb_write.lock` in this process
  may pass `lock_already_held=True`; the runtime verifies the held lock and
  fails closed if the flag is used without it.
- Skip: soft-skipped bundles produce no writes; ambiguous matches and slug collisions
  are skipped (logged to stderr) and counted in the results dict

## Assertions

- No entity page is written without a valid extraction bundle
- `wiki/.kb_write.lock` is held for the entire write batch
- New page slugs that collide with existing files are skipped (fail-closed)
- Ambiguous dedup matches (>1 candidate) are skipped (fail-closed)
- SourceRef citations use the `source_ref` from the extraction bundle

## Procedure

### Step 1: Read extraction bundle

Load the JSON bundle from `extract_entities.py`. If `soft_skipped: true`, exit cleanly.

### Step 2: Acquire wiki write lock (single lock in CI-3)

CI-3's `synthesize_combined.py` acquires `wiki/.kb_write.lock` once, then calls
`_write_entity_drafts` followed by `_write_concept_drafts` before releasing.
When `synthesize_entity_page.py` is invoked standalone, it acquires/releases the
lock around entity writes only. Non-CLI callers may skip the nested acquisition
with `lock_already_held=True` only after acquiring the wiki write lock in the
same process.

### Step 3: Scan existing entity pages

Scan `wiki/entities/*.md` for dedup candidates using `scan_existing_pages`.

### Step 4: For each entity — create or update

- If >1 dedup match: skip, log to stderr.
- If 1 match: call `append_to_existing_page` (SourceRef + open_questions only).
- If 0 matches: check for slug collision; skip if slug file exists; otherwise create
  with `write_text_capturing_previous_safe`.

### Step 5: Write concepts in combined flow

`synthesize_combined.py` invokes concept synthesis while the same lock is still held.

### Step 6: Release lock

Lock is released when the enclosing `with exclusive_write_lock(...)` block exits.

## Boundaries

- Write path is limited to `wiki/entities/**` while holding `wiki/.kb_write.lock`
- Do not read source files directly — use the extraction bundle only
- Do not merge or edit existing entity prose
- Standalone `synthesize_entity_page.py` must not open secondary write paths
  (concepts/index/log); the approved CI-3 exception is `synthesize_combined.py`
  orchestrating both entity and concept writes under one lock

## Verification

- [ ] Extraction bundle loaded and parsed successfully
- [ ] `wiki/.kb_write.lock` was acquired before any write
- [ ] CI-3 combined flow keeps entity + concept writes inside the same lock scope
- [ ] All created pages pass `validate_draft_frontmatter`
- [ ] Ambiguous and slug-collision cases are skipped with stderr log
- [ ] Lock released after batch completes

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `schema/page-template.md`
- `schema/ontology-entity-contract.md`
- `schema/metadata-schema-contract.md`
- `.github/agents/synthesis-curator.md`
