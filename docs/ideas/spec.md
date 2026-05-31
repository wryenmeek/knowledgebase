# Spec: Post-MVP Rollout and Packaging

**Status:** Implemented — all phases complete (2026-05-14)

> Archived to `raw/inbox/post-mvp-rollout-packaging-spec.md` for wiki source intake.
> Full design proposal and implementation notes are in the archived copy.

## Verification matrix and CI migration rules

### Current MVP suites that stay green in every phase

| Domain | Representative suites |
|---|---|
| Skill-local helpers | `tests.kb.test_context_import_helpers`, `tests.kb.test_documentation_helpers` |
| Wrapper modes | `tests/kb/test_skill_wrappers.py`, `tests/kb/test_framework_write_surface_matrix.py` |
| Repo-level scripts | `tests/kb/test_ci_permission_asserts.py`, `tests/kb/test_unit_verification_matrix.py` |
| Workflow lanes | `tests/kb/test_ci1_workflow.py`, `tests/kb/test_ci2_workflow.py`, `tests/kb/test_ci3_workflow.py` |

| Migration stage | Rule |
|---|---|
| Pre-script | Keep existing MVP suites green before any packaging expansion. |
| Script-expansion | Add new package-family tests while preserving unchanged MVP contracts. |
| Final consolidation | Preserve full-matrix parity before treating a script surface as authoritative. |
