# Test Framework Pytest Migration
**Status:** In Progress

## Objective

Migrate the repository's test suite to pytest as the canonical framework while
keeping the main branch green after every incremental change. ADR-029 records
the policy decision; issue #224 lands the initial mechanical hook and CI ratchet.

## Current state

- Verified starting count: 61 unittest-style files under `tests/**`.
- Current count after the latest proof-of-concept migration: 58 files.
- Ratchet contract: `scripts.kb.contracts.MAX_UNITTEST_FILES = 58`.
- Primary command: `python3 -m pytest tests/`.

## Ratchet mechanism

1. `scripts/hooks/check_test_framework.py` rejects new unittest-style test files
   in the staged diff (and in CI PR diff mode).
2. The same hook rejects non-docstring modifications to existing unittest-style
   files unless the file is migrated to pytest in the same change.
3. `tests/kb/test_test_framework_ratchet.py` fails if the repository-wide count
   differs from `MAX_UNITTEST_FILES`, so each migration must decrement the
   baseline in the same change.
4. Each future migration decrements `MAX_UNITTEST_FILES` in the same change.

The hook is registered in `.pre-commit-config.yaml`, and the write-surface
matrix row is maintained in `AGENTS.md`.

## Migration plan

1. Prefer migrating the touched unittest-style file whenever test logic changes.
2. Convert low-risk files first: no `setUp`/`tearDown`, no heavy mocking, and no
   cross-test shared mutable state.
3. Convert `self.assert*` helpers to plain pytest assertions and
   `pytest.raises`.
4. Run `python3 -m pytest <path>` for every migrated file, then run the ratchet
   and contract tests.
5. Leave `tests/kb/test_framework_*` to a dedicated PR because the runbook still
   documents a unittest fast path for those files.

## Success criteria

- New tests use pytest idioms by default.
- The unittest-style file count monotonically decreases from 58 to 0.
- The runbook's primary command remains `python3 -m pytest tests/`.
- Any remaining unittest fast paths are explicitly tied to deferred migration
  ownership.
