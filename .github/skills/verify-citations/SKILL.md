---
name: verify-citations
description: Verifies citation readiness and provenance completeness before policy or publication follow-up. Use when checking SourceRef-backed evidence packages or draft citations for deterministic gaps.
---

# Verify Citations

## Overview

Use this skill to verify evidence packages without overstating current MVP
runtime guarantees. Today it is a doc-only workflow centered on SourceRef
readiness, provenance completeness, and citation shape; broad claim-inventory or
hallucination-detection automation remains post-MVP work.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Evidence review and handoff only. Do not add a new
  citation crawler, semantic fact-checking runtime, or external verification
  service in MVP.

## When to Use

- An intake package claims to be ready for policy review
- Draft citations need SourceRef-shape or provenance verification
- Evidence is provisional, incomplete, or internally contradictory
- A reviewer needs a deterministic pass, fail, or escalate outcome for citation
  readiness
- Policy review should be blocked until citation gaps are resolved

## Contract

- Input: an intake package or draft citation set with SourceRef and provenance
  metadata
- Decision model: classify the evidence as `pass`, `fail`, or `escalate` for the
  next governance step
- Output: a citation-readiness report listing valid evidence, missing
  prerequisites, provisional markers, and blocking gaps
- Handoff rule: passing packages can move to policy review; failed or ambiguous
  packages stop and return for evidence remediation

## Assertions

- Verify SourceRef prerequisites before evaluating downstream readiness
- Treat provisional-only, checksum-mismatched, or non-authoritative evidence as
  blocking when deterministic review cannot proceed
- Keep current MVP scope focused on provenance and citation-shape verification
- Route unresolved conflicts to escalation instead of silently downgrading them
- Do not invent new verification runtimes or out-of-band side effects

## Procedure

### Step 1: Inventory the cited evidence

List the cited raw artifacts, SourceRefs, checksums, and provenance status so
review is grounded in explicit evidence rather than free-form claims.

### Step 2: Verify citation prerequisites

Check SourceRef shape, authoritative-versus-provisional markers, checksum
expectations, and any other ingest prerequisites required by the current
knowledgebase contracts.

### Step 3: Classify the readiness outcome

Use one of three outcomes only:

- **pass**: evidence is citation-ready for the next governance step
- **fail**: required citation prerequisites are missing or invalid
- **escalate**: contradictory or ambiguous evidence requires human review

### Step 4: Hand off the result

Return blocking gaps, remediations needed, and the next destination such as
`policy-arbiter` or a return to intake/evidence remediation.

## Boundaries

- Do not present post-MVP claim-level verification as a landed runtime guarantee
- Do not approve packages that rely only on unresolved provisional evidence when
  deterministic review requires authoritative provenance
- Do not mutate page content or raw artifacts from this skill
- Do not bypass `policy-arbiter` when evidence is incomplete or disputed

## Verification

- [ ] SourceRef and provenance prerequisites are explicitly checked
- [ ] Evidence outcome is `pass`, `fail`, or `escalate`
- [ ] Blocking gaps are named before policy review proceeds
- [ ] Post-MVP citation automation is kept out of the MVP runtime claim
- [ ] The workflow remains deterministic and fail-closed

## References

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`raw/processed/SPEC.md`](../../../raw/processed/SPEC.md)
- [`schema/ingest-checklist.md`](../../../schema/ingest-checklist.md)
- [`schema/metadata-schema-contract.md`](../../../schema/metadata-schema-contract.md)
