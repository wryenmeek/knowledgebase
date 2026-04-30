# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 23 issues on 2026-04-30T00:39:39.402Z

## Executive Summary

Identified 4 actionable root causes spanning 6 issues, addressing critical shell injection vulnerabilities, architectural doc gaps, code bloat, and ADR-011 violations. The remaining issues are either larger feature work, performance optimizations, or require external changes, and are marked as unaddressable for this run.

## Root Cause Analysis

### RC-1: Shell injection via inputs in workflow run blocks

**Related issues:** #72
**Severity:** Critical
**Files involved:** `.github/workflows/fleet-dispatch.yml`, `.github/workflows/fleet-merge.yml`

#### Diagnosis

Direct interpolation of `${{ inputs.* }}` in `run:` blocks allows arbitrary command execution if an attacker crafts a malicious `base_branch` input. For example, in `fleet-dispatch.yml`:

```yaml
        run: |
          set -euo pipefail
          git pull --ff-only origin "${{ inputs.base_branch || 'main' }}"
```

#### Proposed Solution

Move inputs to the `env` context and reference them as environment variables inside the shell script:

```yaml
        env:
          FLEET_BASE_BRANCH: ${{ inputs.base_branch || 'main' }}
        run: |
          set -euo pipefail
          git pull --ff-only origin "$FLEET_BASE_BRANCH"
```

#### Test Plan

1. Verify GHA workflow syntax is valid.
2. Verify no direct `${{ inputs.* }}` remain within `run:` blocks.

---

### RC-2: Bloated common utility with missing sync guards and duplication

**Related issues:** #64, #65, #67
**Severity:** Medium
**Files involved:** `scripts/_optional_surface_common.py`, `scripts/kb/qmd_preflight.py`, `scripts/reporting/content_quality_report.py`, `scripts/reporting/quality_runtime.py`

#### Diagnosis

`_optional_surface_common.py` contains reporting-specific logic (`validate_report_artifact`, `write_report_artifact`) which should be in `scripts/reporting`. It also hardcodes `LOCK_PATH` instead of importing it from contracts, and `qmd_preflight.py` duplicates constants without `# keep in sync` comments, violating ADR-011.

#### Proposed Solution

1. Create `scripts/reporting/_artifact.py` and move the reporting functions/constants into it.
2. Update callers (`content_quality_report.py`, `quality_runtime.py`) to import from `_artifact.py`.
3. In `_optional_surface_common.py`, replace `LOCK_PATH = ...` with `from scripts.kb.contracts import WRITE_LOCK_PATH as LOCK_PATH`.
4. Add `# keep in sync` comments to `STATUS_PASS`, `STATUS_FAIL`, `REASON_CODE_OK`, and `REASON_CODE_INVALID_INPUT` in `qmd_preflight.py` and reference ADR-011 in `_optional_surface_common.py`.

#### Test Plan

1. Run `python3 -m unittest discover -s tests/kb -p "test_*.py"`.

---

### RC-3: Undocumented Fleet orchestration layer

**Related issues:** #66
**Severity:** Low
**Files involved:** `docs/architecture.md`

#### Diagnosis

The TypeScript fleet orchestration logic (`scripts/fleet/*`) is active and has CI workflows but is completely absent from `docs/architecture.md`.

#### Proposed Solution

Add a "Fleet orchestration" section to `docs/architecture.md` immediately following the `CI-1..CI-5` table. Document its purpose, runtime (Bun/TypeScript), verification command (`bun build ...`), and CI integration.

#### Test Plan

1. Verify markdown formatting is correct.

---

### RC-4: Cross-boundary private imports violate ADR-011

**Related issues:** #63
**Severity:** Low
**Files involved:** `scripts/kb/ingest_render.py`, `scripts/kb/ingest.py`, `tests/kb/test_ingest.py`

#### Diagnosis

`ingest.py` imports underscore-prefixed symbols from sibling module `ingest_render.py`, violating ADR-011.

#### Proposed Solution

Remove leading underscores from `_PROVISIONAL_GIT_SHA`, `_build_source_ref`, `_build_provisional_source_provenance`, `_render_source_page`, and `_escape_quotes` in `ingest_render.py`. Add an `__all__` list. Update imports and usages in `ingest.py` and `tests/kb/test_ingest.py`.

#### Test Plan

1. Run `python3 -m unittest discover -s tests/kb -p "test_*.py"`.

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Fix Shell injection via inputs.base_branch in fleet workflows | RC-1 | #72 | `.github/workflows/fleet-dispatch.yml`, `.github/workflows/fleet-merge.yml` | Low |
| 2 | Refactor _optional_surface_common and extract report artifact IO | RC-2 | #64, #65, #67 | `scripts/_optional_surface_common.py`, `scripts/kb/qmd_preflight.py`, `scripts/reporting/content_quality_report.py`, `scripts/reporting/quality_runtime.py`, `scripts/reporting/_artifact.py`, `tests/kb/test_optional_surface_scripts.py`, `tests/kb/test_qmd_preflight.py` | Low |
| 3 | Document fleet orchestration layer in architecture.md | RC-3 | #66 | `docs/architecture.md` | Low |
| 4 | Deprivatize cross-boundary symbols in ingest_render | RC-4 | #63 | `scripts/kb/ingest_render.py`, `scripts/kb/ingest.py`, `tests/kb/test_ingest.py` | Low |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `.github/workflows/fleet-dispatch.yml` | fix-shell-injection-fleet-workflows | Modify |
| `.github/workflows/fleet-merge.yml` | fix-shell-injection-fleet-workflows | Modify |
| `scripts/_optional_surface_common.py` | refactor-optional-surface-common-and-extract-artifact-io | Modify |
| `scripts/kb/qmd_preflight.py` | refactor-optional-surface-common-and-extract-artifact-io | Modify |
| `scripts/reporting/content_quality_report.py` | refactor-optional-surface-common-and-extract-artifact-io | Modify |
| `scripts/reporting/quality_runtime.py` | refactor-optional-surface-common-and-extract-artifact-io | Modify |
| `scripts/reporting/_artifact.py` | refactor-optional-surface-common-and-extract-artifact-io | Create |
| `tests/kb/test_optional_surface_scripts.py` | refactor-optional-surface-common-and-extract-artifact-io | Modify |
| `tests/kb/test_qmd_preflight.py` | refactor-optional-surface-common-and-extract-artifact-io | Modify |
| `docs/architecture.md` | document-fleet-orchestration-layer | Modify |
| `scripts/kb/ingest_render.py` | deprivatize-cross-boundary-symbols-ingest-render | Modify |
| `scripts/kb/ingest.py` | deprivatize-cross-boundary-symbols-ingest-render | Modify |
| `tests/kb/test_ingest.py` | deprivatize-cross-boundary-symbols-ingest-render | Modify |

## Unaddressable Issues

Issues that require changes outside this repository (backend API, infrastructure, product decisions):

| Issue | Reason | Suggested Owner |
|-------|--------|-----------------|
| #19 | Large scope beyond simple issue tasks, requires telemetry integration | Maintainers |
| #18 | Complex performance optimization requiring detailed metric profiles | Maintainers |
| #17 | Complex performance optimization requiring detailed metric profiles | Maintainers |
| #16 | Complex performance optimization requiring detailed metric profiles | Maintainers |
| #15 | Complex performance optimization requiring detailed metric profiles | Maintainers |
| #14 | Complex performance optimization requiring detailed metric profiles | Maintainers |
| #13 | Requires extensive new security tests across multiple files | Maintainers |
| #12 | gitignore change, low risk but better handled separately | Maintainers |
| #11 | Requires GitHub settings/environment changes not just code | Maintainers |
| #9 | Optional step, requires changes to github actions workflow | Maintainers |
| #8 | Optional CLI flag change requiring deprecation process | Maintainers |
| #7 | Optional CLI flag change | Maintainers |
| #6 | Requires extensive new tests to increase coverage | Maintainers |
| #5 | Requires significant logic change or spec change | Maintainers |
| #4 | Requires significant changes to ingest logic | Maintainers |
| #3 | Requires locking mechanism integration in update_index | Maintainers |
| #2 | Requires new shared safe-write guard implementation | Maintainers |
