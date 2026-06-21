# ADR-031: Lock holder PID/start-time tracking for lock-unavailable UX

**Date:** 2026-06-19

## Status

Accepted — extends ADR-005

## Context

Write-capable surfaces use non-blocking `flock` via
`scripts/kb/write_utils.py::exclusive_write_lock()`. When contention occurs,
`LockUnavailableError` could only report `lock_unavailable:<path>` plus a
generic hint to either retry or remove a stale lock file. Operators had to
guess whether the holder process was active.

The issue contract for #183 requires disambiguation without changing `flock`
semantics or adding new dependencies.

This ADR extends ADR-005's lock-unavailable contract with lock-holder metadata
hashing while preserving the existing `reason_code=lock_unavailable` envelope.

## Decision

Adopt Resolution A:

1. After `flock(... LOCK_EX | LOCK_NB)` succeeds, write lock-file metadata in a
   truncate-first format:
   - `{pid}\t{start_time_unix_seconds}\n`
2. On `LockUnavailableError`, read and parse the lock file when possible.
3. Use `os.kill(pid, 0)` liveness probing plus Linux process start-time checks
   (`/proc/<pid>/stat` + `/proc/stat btime`) to detect PID reuse.
4. Populate structured fields on `LockUnavailableError`:
   - `holder_pid: int | None`
   - `holder_alive: bool | None`
   - `holder_started_at: str | None` (UTC ISO-8601 string)
   - `holder_context_hash: str | None` (`sha256` over canonical lock metadata)
5. Keep fail-safe fallback behavior: if lock metadata cannot be read or trusted,
   preserve the prior generic lock-unavailable hint, and sanitize lock-unavailable
   messages/context to expose only `holder_context_hash` (not raw PID/start-time).

## Alternatives considered

1. **Mtime heuristic only (Resolution B):** rejected; cannot reliably
   distinguish long-running holders from stale files.
2. **Third-party lock library (Resolution C):** rejected; dependency and
   migration cost outweighs value for this focused UX improvement.

## Consequences

### Positive

- Operators can distinguish active holders from stale metadata without manual
  guesswork.
- `SurfaceResult` consumers can branch on structured holder context.
- Change applies uniformly across all lock-path variants that use
  `exclusive_write_lock()`.
- The `holder_context_hash` privacy trade-off is explicit: callers get a
  stable SHA-256 fingerprint over raw PID/start-time context without leaking
  the PID or process start time into unauthenticated logging surfaces.

### Trade-offs

- Lock files now contain operational metadata bytes.
- Linux start-time probing relies on `/proc`; non-Linux fallback remains
  generic.

### Governance scope note

Lock-file bytes are governance-internal runtime metadata. No
`governed_artifact_contract_for_path()` row claims lock-file contents, so this
change does not alter governed artifact contracts.

## Related decisions

- [`ADR-005`](ADR-005-write-concurrency-guards.md) — Enforce write
  concurrency with workflow group and local file lock. This ADR extends
  `ADR-005`'s `lock_unavailable` envelope with holder PID/start-time metadata
  for actionable diagnostics.

## References

- GitHub issue #183
- `scripts/kb/write_utils.py`
- ADR-005: write concurrency guards
