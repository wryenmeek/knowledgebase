# ADR-030: CLI write-confirmation flag migration

**Date:** 2026-06-19

## Status

Accepted

## Context

Issue #182 identified long-running ambiguity in write-capable optional-surface
scripts that used `--approval {none|approved}`. The flag acted as a
deny-by-default write-confirmation ceremony, but the naming implied an
authorization boundary that does not exist.

At the same time, the repository depends on explicit write intent for
copy-paste safety, CI misconfiguration safety, and structured runtime audit
evidence in `SurfaceResult.approval`.

## Decision

Adopt a ratcheted migration from `--approval` to `--apply` for optional-surface
CLI entrypoints.

1. `--apply` is the preferred write-confirmation spelling for write-capable
   optional-surface scripts.
2. `--approval approved` remains a backward-compatible alias during a
   deprecation window through **2026-12-31** for in-scope optional-surface
   scripts.
3. Passing both forms in one invocation is invalid and must fail closed.
4. `--approval=...` (equals-sign spelling) is rejected; only
   `--approval approved` is accepted during the compatibility window.
5. The `SurfaceResult.approval` JSON field name remains unchanged for backward
   compatibility with existing CI/log consumers.
6. The pattern is explicitly **not** a security boundary. It is a deliberate
   write-confirmation and auditability control.
7. Migration is enforced by a local ratchet hook
   (`scripts/hooks/check_approval_flag.py`) plus a repository baseline test
   (`tests/kb/test_approval_migration_ratchet.py` and
   `MAX_APPROVAL_FLAG_SCRIPTS`).
8. Scope and removal criteria:
   - In scope: optional-surface writer CLIs that currently use shared
     write-confirmation parser plumbing.
   - Transitional special case: `scripts/kb/checkpoint_registry.py` remains
     grandfathered during this window because its bootstrap compatibility lane
     is managed by its own migration slice.
   - Removal criteria: by 2026-12-31, set `MAX_APPROVAL_FLAG_SCRIPTS == 0` and
     remove compatibility-only runbook/workflow invocations that still require
     `--approval approved`.

## Alternatives considered

1. Keep `--approval` unchanged (codify as-is). Rejected: preserves misleading
   naming and recurring command noise.
2. Collapse write confirmation into existing mode enums. Rejected: conflates
   operational mode with write confirmation and increases combinatorial CLI
   complexity.

## Consequences

### Positive

- Clearer write intent in operator and CI commands (`--apply`).
- Default-deny behavior remains unchanged.
- Existing JSON logs remain stable (`approval` field retained).
- Controlled migration avoids high-churn all-at-once refactors.

### Negative

- Temporary dual-spelling support adds short-term complexity.
- Ratchet exemptions are required for known transition surfaces.
- Rejecting `--approval=...` may break legacy one-token invocations; callers
  must use `--apply` or `--approval approved`.

## Migration and rollback

Migration:

1. Prefer `--apply` in workflows and runbook commands.
2. When touching scripts that still spell `--approval`, migrate that script in
   the same change.
3. Decrement `MAX_APPROVAL_FLAG_SCRIPTS` in `scripts/kb/contracts.py` in the
   same commit that migrates or removes a legacy `--approval` script. The
   ratchet test enforces strict equality (`==`, tightened from `<=` in PR #317),
   so an off-by-one in either direction hard-fails CI — adding a non-exempt
   script without decrementing fails, and decrementing without removing a
   script also fails. The strict-equality form prevents silent ratchet drift.

Rollback:

- Keep `--apply` support and continue accepting `--approval approved` alias if
  a regression appears; do not remove default-deny behavior.

## Related decisions

- [`ADR-005`](ADR-005-write-concurrency-guards.md) — Write-capable
  optional-surface commands still acquire declared locks before `--apply`
  writes; the flag migration does not weaken lock requirements.
- [`ADR-022`](ADR-022-afk-uses-scripts-hitl-uses-copilot-cli.md) — Keeps
  AFK write automation in deterministic scripts while preserving Copilot CLI
  for HITL; `--apply` is the script-side confirmation ceremony.

## References

- GitHub issue #182
- `scripts/_optional_surface_common.py`
- `scripts/hooks/check_approval_flag.py`
- `tests/kb/test_approval_migration_ratchet.py`
