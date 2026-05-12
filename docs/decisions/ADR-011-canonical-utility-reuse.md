# ADR-011: Canonical Utility Re-Use Policy

## Status
Accepted

## Date
2026-04-19

## Context

A code-simplification audit of the knowledgebase codebase found six or more locations
duplicating helper logic that already existed in established utility modules:

- Two reporting scripts re-implemented the same two-line frontmatter parse wrapper.
- Two scripts defined near-identical private functions for parsing the `sources:` YAML
  key from frontmatter strings.
- `ingest.py` contained private `_ensure_not_symlink` and `_write_text_atomically`
  functions that reimplemented logic already present and tested in `write_utils.py`.
- Three non-test files redefined `TOPICAL_NAMESPACES` locally without drift guards,
  creating three independent sources of truth for a constant with one correct value.

The pattern emerged because the canonical modules existed and were used in some places,
but there was no documented rule requiring agents and developers to check them first.
New code drifted toward re-implementing helpers it was unaware of.

## Decision

**Four modules are the canonical utility library for this codebase.** Before implementing
any new helper function, constant, or utility, all agents and developers MUST search these
modules for existing functionality:

| Module | Scope |
|---|---|
| `scripts/kb/page_template_utils.py` | All frontmatter parsing, heading extraction, namespace constants (e.g. `TOPICAL_NAMESPACES`), and wiki-page structural helpers. |
| `scripts/kb/write_utils.py` | All safe file writes, atomic operations, symlink path checks, write-lock primitives, and rollback helpers. |
| `scripts/kb/contracts.py` | All status enums, reason codes, governed artifact contracts, and result type definitions. |
| `scripts/_optional_surface_common.py` | All optional-surface CLI framework, `SurfaceResult`, `run_surface_cli`, `JsonArgumentParser`, and shared CLI reason codes. |

**Rules:**

1. **Check before implementing.** If a suitable helper exists in a canonical module,
   import it rather than re-implementing it in the calling file.
2. **Extend, don't copy.** If a related helper exists but needs extending, extend the
   canonical module rather than creating a parallel private copy.
3. **Single canonical definition for module-level constants.** Constants such as
   `TOPICAL_NAMESPACES` must have exactly one definition in their canonical module.
   Any file that needs a local copy for testing or isolation must include a
   `# keep in sync with <module>.<CONSTANT>` drift guard comment.
4. **Add to `__all__`.** Any new public helper added to a canonical module must be
   listed in that module's `__all__`.

## Consequences

- Code review steps must include a "utility reuse" check (see `code-review-and-quality` SKILL.md).
- Incremental implementation must include a "Step 0: Check for existing utilities" phase
  (see `incremental-implementation` SKILL.md).
- `code-simplification` audits should flag any private helper that duplicates canonical
  module logic as a required fix, not an optional improvement.
- The canonical modules grow over time as new shared helpers are consolidated into them.
  This is expected and preferred over scattered private implementations.

## References

- `scripts/kb/page_template_utils.py` — canonical frontmatter and namespace helpers
- `scripts/kb/write_utils.py` — canonical write, lock, and path-safety helpers
- `scripts/kb/contracts.py` — canonical status enums, reason codes, and result types
- `scripts/_optional_surface_common.py` — canonical CLI surface framework
- `.github/skills/code-review-and-quality/SKILL.md` — utility reuse check in review workflow
- `.github/skills/incremental-implementation/SKILL.md` — Step 0 utility search phase
- `.github/skills/code-simplification/SKILL.md` — duplicate-helper detection
- `AGENTS.md` § Canonical utility modules — runtime enforcement of this policy
