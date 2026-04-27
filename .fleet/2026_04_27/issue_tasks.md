# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 22 issues on 2026-04-27T08:33:13.351Z

## Executive Summary

Found 9 actionable root causes spanning missing documentation, code boundary violations, redundant indexing operations, security gaps, performance gaps, and suboptimal CI workflow design. These have been transformed into 9 isolated execution tasks with absolutely no file-level collisions. All issues were addressable. Tasks are ordered strictly by risk (lowest risk first) to ensure easy wins merge prior to complex architectural changes. Test boundaries are explicitly mapped for all tasks.

## Root Cause Analysis

### RC-1: Missing .gitignore Entries for Local Secrets

**Related issues:** #12
**Severity:** Low
**Files involved:** `.gitignore`

#### Diagnosis

Common local caches and secret files (`.env.local`, `.claude/`) are not in `.gitignore`.

#### Proposed Solution

Append missing patterns to `.gitignore`.

```diff
# .gitignore
+.env.local
+.env.*.local
+.claude/
```

**Integration points:**
Append to the end of the existing `.gitignore` file.

**Edge cases and risks:**
None.

#### Test Plan

1. Verify `.env.local` is ignored by running `git check-ignore .env.local`.

---

### RC-2: Unstructured Optional Surface Utilities and Silent Drift

**Related issues:** #64, #65, #67
**Severity:** Medium
**Files involved:** `scripts/_optional_surface_common.py`, `scripts/kb/qmd_preflight.py`, `scripts/reporting/content_quality_report.py`, `scripts/reporting/quality_runtime.py`

#### Diagnosis

`scripts/_optional_surface_common.py` has grown into a catch-all module (551 lines), accreting reporting domain logic (`validate_report_artifact`, `write_report_artifact`) only needed by `scripts/reporting/`. Furthermore, it silently duplicated `WRITE_LOCK_PATH` without importing it from `contracts.py`, violating ADR-011. Similarly, `qmd_preflight.py` duplicated constants without `# keep in sync` comments.

```python
# scripts/_optional_surface_common.py:33
LOCK_PATH = "wiki/.kb_write.lock"

# scripts/kb/qmd_preflight.py:18-22
STATUS_PASS = "pass"
STATUS_FAIL = "fail"

REASON_CODE_OK = "ok"
REASON_CODE_INVALID_INPUT = "invalid_input"
```

#### Proposed Solution

Extract reporting symbols from `_optional_surface_common.py` into `scripts/reporting/_artifact.py`. Update callers. Replace hardcoded `LOCK_PATH` with a direct import. Add keep-in-sync comments in `qmd_preflight.py`.

```diff
# scripts/_optional_surface_common.py
-LOCK_PATH = "wiki/.kb_write.lock"
+from scripts.kb.contracts import WRITE_LOCK_PATH as LOCK_PATH

# scripts/kb/qmd_preflight.py
-STATUS_PASS = "pass"
+STATUS_PASS = "pass"  # keep in sync with scripts/_optional_surface_common.STATUS_PASS
```

**Integration points:**
Update imports in `content_quality_report.py` and `quality_runtime.py` to point to the new `_artifact.py` module.

**Edge cases and risks:**
Import cycles if `_artifact.py` requires items from `_optional_surface_common.py`. Mitigation: copy cleanly and ensure no circular deps.

#### Test Plan

1. Verify `pytest tests/` runs successfully without import errors.
2. Ensure `scripts/reporting/_artifact.py` exposes correct symbols via `__all__`.
3. Check `LOCK_PATH` substitution resolves correctly in existing calls.

---

### RC-3: Documentation Drift: Missing Fleet and Invalid Entity Generation

**Related issues:** #5, #66
**Severity:** High
**Files involved:** `docs/architecture.md`, `raw/inbox/SPEC.md`

#### Diagnosis

The TypeScript/Bun project in `scripts/fleet/` is omitted from `docs/architecture.md`. Further, SPEC.md incorrectly claims ingest updates entities.

#### Proposed Solution

Append a "Fleet orchestration" section to architecture.md. Remove references to entity generation.

**Integration points:**
Insert immediately after the CI-1..CI-5 automation model table. Remove paragraphs in SPEC.md.

**Edge cases and risks:**
None, purely documentation.

#### Test Plan

1. Verify document renders correctly and contains required keywords.
2. Confirm section resides correctly after CI-1..CI-5 table.
3. Validate "entity" references are stripped from SPEC.md.

---

### RC-4: Unnecessary Index Rebuilds and Misleading Flags in Persist Query

**Related issues:** #7, #8, #17
**Severity:** Medium
**Files involved:** `scripts/kb/persist_query.py`

#### Diagnosis

`persist_query.py` executes index generation unconditionally even when analysis text hasn't changed. The CLI also defines a no-op flag `--result-json`.

```python
# scripts/kb/persist_query.py:350-353
analysis_changed = write_text_if_changed(analysis_absolute, analysis_markdown)
index_updated = _update_index_if_changed(request.wiki_root)
state_changed = analysis_changed or index_updated
```

#### Proposed Solution

Condition index regeneration on `analysis_changed`. Remove `--result-json`. Make contradiction policy flags accurate.

```diff
# scripts/kb/persist_query.py
-index_updated = _update_index_if_changed(request.wiki_root)
+index_updated = _update_index_if_changed(request.wiki_root) if analysis_changed else False
```

**Integration points:**
Update argument parsing logic to enforce contradiction logic directly.

**Edge cases and risks:**
Removing the flag might break older invocation scripts relying on `--result-json`.

#### Test Plan

1. Run persist_query twice with identical inputs and verify second run exits early without rebuilding index.
2. Pass `--result-json` to CLI and assert it throws `unrecognized arguments`.

---

### RC-5: Update Index Performance and Missing Write Lock

**Related issues:** #3, #18, #19
**Severity:** High
**Files involved:** `scripts/kb/update_index.py`, `scripts/kb/lint_wiki.py`

#### Diagnosis

`update_index.py` with `--write` writes to `wiki/index.md` without securing `wiki/.kb_write.lock`, violating standard concurrency spec. The scripts also lack timing telemetry and perform redundant stat calls.

```python
# scripts/kb/update_index.py:311-329
def generate_and_write_index(wiki_root: Path) -> bool:
    generated = generate_index_content(wiki_root)
    # ... writes without lock
    atomic_replace_governed_artifact(repo_root, "wiki/index.md", generated)
```

#### Proposed Solution

Wrap `generate_and_write_index` writes in `with exclusive_write_lock(wiki_root.parent):`. Implement stat caching and timing wrappers.

```diff
# scripts/kb/update_index.py
+from scripts.kb.write_utils import exclusive_write_lock
...
def generate_and_write_index(wiki_root: Path) -> bool:
-    generated = generate_index_content(wiki_root)
+    with exclusive_write_lock(wiki_root.parent):
+        generated = generate_index_content(wiki_root)
```

**Integration points:**
Inside `generate_and_write_index` immediately prior to file writes. Add decorators for time output.

**Edge cases and risks:**
Lock contention might cause unexpected hangs if `atomic_replace` is too slow.

#### Test Plan

1. Test lock acquisition and deterministic fail-closed behavior on lock contention.
2. Confirm index generation path is guarded.

---

### RC-6: ADR-011 Violation and Synthetic SourceRef SHA in Ingest

**Related issues:** #4, #63
**Severity:** High
**Files involved:** `scripts/kb/ingest_render.py`, `scripts/kb/ingest.py`, `tests/kb/test_ingest.py`, `tests/kb/test_ingest_render.py`

#### Diagnosis

`ingest.py` violates module boundary rules by importing underscore-prefixed symbols (e.g. `_PROVISIONAL_GIT_SHA`) from its sibling `ingest_render.py`. Furthermore, `_PROVISIONAL_GIT_SHA` uses a synthetic all-zero SHA which violates the requirement for real provenance logic.

```python
# scripts/kb/ingest.py:14-16
from scripts.kb.ingest_render import (
    SourceProvenance,
    _PROVISIONAL_GIT_SHA,
```

#### Proposed Solution

Remove leading underscores for cross-boundary symbols in `ingest_render.py`, export via `__all__`, and update usages. In the same phase, replace `PROVISIONAL_GIT_SHA` usage with a `git rev-parse HEAD` or `GITHUB_SHA` resolution string.

```python
# scripts/kb/ingest_render.py
import os, subprocess
def get_git_sha():
    return os.environ.get("GITHUB_SHA") or subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()

__all__ = ["get_git_sha", "build_source_ref", "build_provisional_source_provenance", "render_source_page", "escape_quotes", "SourceProvenance"]
```

**Integration points:**
Update references across `ingest.py` and `test_ingest.py` to use the un-prefixed names and dynamic SHA functions.

**Edge cases and risks:**
Renaming functions could break tests referencing the private variables directly. Process subcalls may fail outside git repo contexts.

#### Test Plan

1. Grep for `_PROVISIONAL_GIT_SHA` in tests and confirm zero matches.
2. Run `test_ingest.py` to ensure pipeline runs without `ImportError`.
3. Mock `git rev-parse` and ensure fallback is handled.

---

### RC-7: CI-2 Duplicate YAML and Missing Verification Matrix Coverage

**Related issues:** #6, #16
**Severity:** High
**Files involved:** `.github/workflows/ci-2-analyst-diagnostics.yml`, `tests/kb/test_matrix.py`

#### Diagnosis

Verification matrix items missing test coverage, and no enforcement of coverage threshold in CI. Additionally CI-2 wastes runtime duplicating yaml parse steps.

#### Proposed Solution

Add coverage thresholds to the CI validation step and remove duplicate parse.

```yaml
# .github/workflows/ci-2-analyst-diagnostics.yml
- run: python3 -m coverage report --fail-under=90
```

**Integration points:**
Add step after pytest execution in CI-2. Drop secondary parse path.

**Edge cases and risks:**
Might block PRs if coverage slips below 90%.

#### Test Plan

1. Run CI locally and assert coverage gate triggers failure if below threshold.

---

### RC-8: Symlink Traversal Vulnerability in Write Paths

**Related issues:** #2, #13
**Severity:** High
**Files involved:** `scripts/kb/path_utils.py`, `tests/kb/test_path_utils.py`

#### Diagnosis

Symlinks under allowlisted paths can be followed outside the repo bounds.

```python
# scripts/kb/path_utils.py:51-60
def resolve_within_repo(repo_root: Path, raw_path: str) -> Path:
    # Does not check resolve bounds accurately.
    pass
```

#### Proposed Solution

Add `safe_write_path` guard using `resolve().is_relative_to()`.

```python
def safe_write_path(repo_root: Path, target: Path) -> Path:
    resolved = target.resolve()
    if not resolved.is_relative_to(repo_root):
        raise ValueError("Symlink traversal outside repo root")
    return resolved
```

**Integration points:**
Call inside path resolution utilities before write operations.

**Edge cases and risks:**
`resolve()` forces filesystem stats, which can slow down batched writes.

#### Test Plan

1. Create malicious symlink and verify write fails cleanly.

---

### RC-9: CI-3 Workflow Suboptimal Scaling and Security

**Related issues:** #9, #11, #14, #15
**Severity:** High
**Files involved:** `.github/workflows/ci-3-pr-producer.yml`, `tests/kb/test_ci3_contracts.py`

#### Diagnosis

CI-3 lacks authoritative dispatch approval, relies on an ad-hoc `rm -f` for locks, and suffers from inefficient GITHUB_OUTPUT handoffs and unbatched loops for ingest.

```yaml
# .github/workflows/ci-3-pr-producer.yml:515
- run: rm -f wiki/.kb_write.lock
```

#### Proposed Solution

Enforce GitHub environment protections, remove `rm -f`, and replace output strings with workspace JSON files for batched steps. Add contract tests for verification.

```diff
# .github/workflows/ci-3-pr-producer.yml
- - run: rm -f wiki/.kb_write.lock
```

**Integration points:**
Update workflow YAML blocks for CI-3 manual dispatch to require "environment: production".

**Edge cases and risks:**
Changing outputs to workspace files requires steps down the line to parse JSON correctly.

#### Test Plan

1. Verify workflow YAML passes `actionlint`.
2. Confirm the removed locking step doesn't cause pipeline failures.

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Harden .gitignore for Local Secrets | RC-1 | #12 | `.gitignore` | Low |
| 2 | Refactor Optional Surface Common Utilities | RC-2 | #64, #65, #67 | `scripts/_optional_surface_common.py`, `scripts/kb/qmd_preflight.py`, `scripts/reporting/content_quality_report.py`, `scripts/reporting/quality_runtime.py`, `scripts/reporting/_artifact.py`, `tests/kb/test_optional_surface_scripts.py`, `tests/kb/test_qmd_preflight.py` | Low |
| 3 | Document Fleet Orchestration and Resolve Entity Generation Drift | RC-3 | #5, #66 | `docs/architecture.md`, `raw/inbox/SPEC.md` | Low |
| 4 | Fix Persist Query Index Rebuild and Flags | RC-4 | #7, #8, #17 | `scripts/kb/persist_query.py`, `tests/kb/test_persist_query.py` | Medium |
| 5 | Enforce Write Lock and Optimize update_index | RC-5 | #3, #18, #19 | `scripts/kb/update_index.py`, `scripts/kb/lint_wiki.py`, `tests/kb/test_update_index.py`, `tests/kb/test_lint_wiki.py` | Medium |
| 6 | Deprivatize ingest_render.py Symbols and Replace Synthetic SHA | RC-6 | #4, #63 | `scripts/kb/ingest_render.py`, `scripts/kb/ingest.py`, `tests/kb/test_ingest.py`, `tests/kb/test_ingest_render.py` | High |
| 7 | Enforce Coverage Gate, Tests, and Fix YAML Dup | RC-7 | #6, #16 | `.github/workflows/ci-2-analyst-diagnostics.yml`, `tests/kb/test_matrix.py` | High |
| 8 | Harden Write Paths against Symlink Traversal | RC-8 | #2, #13 | `scripts/kb/path_utils.py`, `tests/kb/test_path_utils.py` | High |
| 9 | Refactor CI-3 Workflow | RC-9 | #9, #11, #14, #15 | `.github/workflows/ci-3-pr-producer.yml`, `tests/kb/test_ci3_contracts.py` | High |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `.gitignore` | 1 | Modify |
| `scripts/_optional_surface_common.py` | 2 | Modify |
| `scripts/kb/qmd_preflight.py` | 2 | Modify |
| `scripts/reporting/content_quality_report.py` | 2 | Modify |
| `scripts/reporting/quality_runtime.py` | 2 | Modify |
| `scripts/reporting/_artifact.py` | 2 | Create |
| `tests/kb/test_optional_surface_scripts.py` | 2 | Modify |
| `tests/kb/test_qmd_preflight.py` | 2 | Modify |
| `docs/architecture.md` | 3 | Modify |
| `raw/inbox/SPEC.md` | 3 | Modify |
| `scripts/kb/persist_query.py` | 4 | Modify |
| `tests/kb/test_persist_query.py` | 4 | Modify |
| `scripts/kb/update_index.py` | 5 | Modify |
| `scripts/kb/lint_wiki.py` | 5 | Modify |
| `tests/kb/test_update_index.py` | 5 | Modify |
| `tests/kb/test_lint_wiki.py` | 5 | Modify |
| `scripts/kb/ingest_render.py` | 6 | Modify |
| `scripts/kb/ingest.py` | 6 | Modify |
| `tests/kb/test_ingest.py` | 6 | Modify |
| `tests/kb/test_ingest_render.py` | 6 | Modify |
| `.github/workflows/ci-2-analyst-diagnostics.yml` | 7 | Modify |
| `tests/kb/test_matrix.py` | 7 | Modify |
| `scripts/kb/path_utils.py` | 8 | Modify |
| `tests/kb/test_path_utils.py` | 8 | Modify |
| `.github/workflows/ci-3-pr-producer.yml` | 9 | Modify |
| `tests/kb/test_ci3_contracts.py` | 9 | Modify |

## Unaddressable Issues

Issues that require changes outside this repository (backend API, infrastructure, product decisions):

| Issue | Reason | Suggested Owner |
|-------|--------|-----------------|
| None | All issues were addressable. | N/A |
