---
name: improve-codebase-architecture
description: "Identifies architecture improvement opportunities and produces structured proposals. Use when reviewing system design, spotting structural issues, or planning architecture evolution."
---

# Improve Codebase Architecture

## Overview

Surface architecture improvement opportunities through structured analysis and produce actionable proposals as ADRs or GitHub Issues.

## When to Use

- During code review when structural issues are spotted
- When a module or subsystem has grown unwieldy
- When planning the next phase of system evolution
- When dependency patterns suggest coupling problems

Doc-only workflow.

## Procedure

1. **Audit current state**: identify modules, dependencies, coupling patterns, and pain points.
2. **Classify improvement type**:
   - **Decomposition** — split a module that has too many responsibilities
   - **Consolidation** — merge redundant modules or eliminate duplication
   - **Interface cleanup** — clarify boundaries, reduce coupling
   - **Pattern alignment** — adopt a consistent pattern across modules
3. **Assess migration cost**: how much work to implement? What breaks during migration?
4. **Propose improvement**: create an ADR or GitHub Issue with:
   - Current state diagram (ASCII is fine)
   - Proposed state diagram
   - Migration path (incremental steps)
   - Risks and rollback plan
5. **Link to existing work**: reference related ADRs, issues, or prior refactoring.

## Verification

1. Proposal has current state, proposed state, and migration path.
2. Migration path is incremental (no big-bang rewrites).
3. Risks are identified with concrete mitigation steps.
