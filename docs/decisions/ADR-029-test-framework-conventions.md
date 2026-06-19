# ADR-029: Test framework conventions

**Date:** 2026-06-18

## Status

Accepted — amended in-place: strict pytest ratchet baseline updated to 58 and CI diff enforcement added (see § Amendment)

## Context

Issue #181 identified a long-running drift risk in the test suite: new and
modified tests can continue to use `unittest.TestCase`, leaving the repository
split between unittest idioms and pytest idioms. Issue #224 implements the
mechanical guardrail for that design.

The verified pre-implementation baseline was 61 files under `tests/**` matching
`unittest.TestCase` or `from unittest import TestCase`. This ADR records the
default answers for the open design questions in #181 so #224 can land with a
durable policy owner.

## Decision

Adopt **pytest** as the canonical test framework for new and changed tests.

Enforcement has two layers:

1. A local hook (`scripts/hooks/check_test_framework.py`) blocks newly staged
   unittest-style test files and blocks non-docstring staged modifications to
   existing unittest-style files until the touched file is migrated to pytest.
2. A CI ratchet test (`tests/kb/test_test_framework_ratchet.py`) asserts the
   repository-wide unittest-style file count equals
   `scripts.kb.contracts.MAX_UNITTEST_FILES`, so each migration must decrement
   the baseline in the same change.

### Open question resolutions from #181

1. **Strict block vs. soft prompt on modification:** choose **strict**. Any
   staged non-docstring modification to an existing unittest-style test file
   must migrate that file to pytest in the same change. This avoids a broad
   soft-warning path and forces incremental migration on every substantive
   touch. The local operator escape hatch is `--no-verify`; CI now exports
   `KB_TEST_FRAMEWORK_RATCHET_BASE_REF` so the hook evaluates PR diffs in
   `pre-commit run --all-files` mode too.
2. **Migration helper:** out of scope for this ADR. A helper may be proposed as a
   future enhancement after the ratchet proves useful.
3. **`tests/kb/test_framework_*` migration timing:** deferred to a dedicated PR.
   Those files remain referenced in `docs/mvp-runbook.md` through
   `python3 -m unittest tests.kb.test_framework_*` fast-path commands until that
   migration lands.

After the latest proof-of-concept migration, the ratchet baseline is
`MAX_UNITTEST_FILES = 58`.

## Alternatives considered

1. **Keep unittest and pytest equally canonical.** Rejected because it preserves
   mixed idioms and gives contributors no clear target for new tests.
2. **Warn only when unittest files are modified.** Rejected because soft prompts
   are easy to ignore and do not force the count downward.
3. **Migrate all unittest files in one PR.** Rejected because the suite is broad
   and the safer path is a mechanical ratchet plus small migrations.
4. **Include a migration helper in the first ratchet PR.** Rejected to keep #224
   mechanical and reviewable.

## Consequences

### Positive

- New tests have a single canonical style.
- Every substantive touch to an existing unittest-style file becomes an
  opportunity to reduce the migration backlog.
- CI exposes accidental count increases with a simple repository-wide contract.

### Negative

- Contributors touching legacy unittest-style tests must migrate those files in
  the same change.
- The hook must remain wired in `.pre-commit-config.yaml` and CI (`.github/workflows/pre-commit.yml`)
  so PR-diff enforcement stays active when contributors skip local hooks.

### Operational

- `python3 -m pytest tests/` is the primary local and CI test command.
- The runbook may retain unittest fast paths only for files with deferred
  migration ownership, especially `tests/kb/test_framework_*`.
- `MAX_UNITTEST_FILES` must only move downward after migrations, never upward
  without a new ADR amendment.

## Related decisions

- ADR-011: Canonical utility modules and single-definition rule for shared helpers
- ADR-016: Use `pre-commit` framework for local governance hooks

## Migration and rollback

To migrate a legacy unittest-style file:

1. Convert `unittest.TestCase` classes to pytest functions or fixtures.
2. Replace assertion helpers with plain `assert` statements and `pytest.raises`.
3. Run `python3 -m pytest <path>`.
4. Decrement `MAX_UNITTEST_FILES` in the same change.

Rollback is limited to hook wiring or hook implementation if false positives are
found. The pytest canonical decision remains accepted unless superseded by a
future ADR.

## Open questions

- Should a codemod or guided migration helper be added once the first several
  manual migrations reveal common rewrite patterns?
- Which dedicated PR will migrate `tests/kb/test_framework_*` and retire the
  runbook's unittest fast-path commands?

## Amendment

- **Date:** 2026-06-19
- **What changed:** Updated ratchet semantics to require exact baseline parity
  (`count == MAX_UNITTEST_FILES`), clarified that non-docstring modifications
  to legacy unittest files are blocked unless migrated in the same change, and
  documented CI PR-diff enforcement via `KB_TEST_FRAMEWORK_RATCHET_BASE_REF`.
- **Why:** The strict migration guard needed parity between local pre-commit and
  CI `--all-files` mode, plus explicit no-slack baseline enforcement.
- **What did not change:** Pytest remains the canonical framework, migrations are
  still incremental, and `MAX_UNITTEST_FILES` can only move downward.

## References

- GitHub issue #181
- GitHub issue #224
- `scripts/hooks/check_test_framework.py`
- `tests/kb/test_test_framework_ratchet.py`
