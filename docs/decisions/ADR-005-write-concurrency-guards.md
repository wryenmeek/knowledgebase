# ADR-005: Enforce write concurrency with workflow group and local file lock

## Status
Accepted — amended in-place: governance sibling meta-lock protocol (see § Amendment)

## Date
2026-04-12

## Context

Concurrent write-capable runs can race while updating shared wiki artifacts
(`wiki/index.md`, `wiki/log.md`, and generated pages). Workflow-level controls
alone do not cover all local write races, while local locks alone do not guard
parallel workflow dispatch.

## Decision

Use a dual-layer concurrency control model:

1. workflow-level `concurrency.group` for write-capable CI paths,
2. local exclusive lock file (`wiki/.kb_write.lock`) inside write-capable scripts.

Lock contention must fail closed, return non-zero, and emit
`reason_code=lock_unavailable` in machine-readable envelopes.

## Alternatives considered

### Workflow concurrency only

- **Pros:** simple CI-level guard.
- **Cons:** does not prevent all runtime-level local lock races.
- **Rejected:** insufficient protection for script-level shared state.

### Local lock only

- **Pros:** protects local write critical sections.
- **Cons:** weaker control over workflow-level parallelization and queue behavior.
- **Rejected:** insufficient end-to-end orchestration for CI write paths.

## Consequences

- Write race conditions are substantially reduced.
- Failure mode is explicit and diagnosable.
- Automation remains deterministic under parallel triggering conditions.

## Amendment

- **Date:** 2026-06-19
- **What changed:** The sibling governance lock set (`wiki/.kb_write.lock`,
  `raw/.rejection-registry.lock`, `.github/.customizations.lock`,
  `raw/.github-sources.lock`, `raw/.drive-sources.lock`,
  `raw/.wiki-processing-checkpoint.lock`) now acquires under a shared meta-lock
  protocol using `raw/.governance-meta.lock`: acquire meta-lock, probe other
  sibling locks with `LOCK_SH | LOCK_NB`, acquire target sibling lock, then
  release meta-lock while retaining the target lock for the critical section.
- **Why:** Entry-time checks alone could not prevent cross-process races where one
  process held `.github/.customizations.lock` while another later acquired a sibling
  governance lock.
- **What did not change:** Existing stale unlocked lock-file reclaim behavior for
  sibling lock files and ADR-012/ADR-021 lock-ordering rules for GitHub/Drive
  monitor locks (`wiki/.kb_write.lock` acquired before monitor registry locks).

## References

- `raw/processed/SPEC.md` (Assumptions and Defaults; Concurrency controls; Runtime prerequisite checks; CI quality gate requirements)
