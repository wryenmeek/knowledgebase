# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 23 issues on 2026-04-30T01:11:30.227277+00:00

## Executive Summary

Found 3 addressable root causes covering 22 issues related to security vulnerabilities (shell injection, symlinks escapes), code hygiene (leaked domain logic, cross-boundary imports), documentation, and performance. One issue is marked unaddressable.

## Root Cause Analysis

### RC-1: Shell injection via ${{ inputs.* }} in run blocks

**Related issues:** #72
**Severity:** Critical
**Files involved:** `.github/workflows/fleet-dispatch.yml`, `.github/workflows/fleet-merge.yml`

#### Diagnosis

GitHub Actions workflow files use `${{ inputs.base_branch }}` directly inside `run:` blocks. This allows an attacker to inject arbitrary shell commands via the input parameter.
For example in `fleet-dispatch.yml`:
```yaml
          BASE="${{ inputs.base_branch || 'main' }}"
```

#### Proposed Solution

Map the inputs to environment variables in the `env:` context and use bash variable expansion in the run scripts.

```yaml
        env:
          INPUT_BASE_BRANCH: ${{ inputs.base_branch || 'main' }}
        run: |
          BASE="${INPUT_BASE_BRANCH}"
```

#### Test Plan

1. Dispatch workflow with payload branch name like `main"; echo "hacked"` -> executes safely as a literal string.

---

### RC-2: Duplicated constants and domain-leakage in _optional_surface_common

**Related issues:** #64, #65, #67
**Severity:** Medium
**Files involved:** `scripts/_optional_surface_common.py`, `scripts/kb/qmd_preflight.py`, `scripts/reporting/content_quality_report.py`, `scripts/reporting/quality_runtime.py`

#### Diagnosis

`_optional_surface_common.py` acts as a grab-bag and has accumulated reporting logic and duplicated constants.
```python
# scripts/_optional_surface_common.py
LOCK_PATH = "wiki/.kb_write.lock"
```

#### Proposed Solution

Extract reporting functions to `scripts/reporting/_artifact.py`. Import `LOCK_PATH` from `scripts.kb.contracts`. Add `# keep in sync` comments.
```python
from scripts.kb.contracts import WRITE_LOCK_PATH as LOCK_PATH
```

#### Test Plan

Run pytest suite to ensure all imports and schemas still work.

---

### RC-3: KB scripting read/write bugs, perf, CI workflows, and documentation

**Related issues:** #2, #3, #4, #5, #6, #7, #8, #9, #11, #12, #13, #14, #15, #16, #17, #18, #63, #66
**Severity:** High
**Files involved:** `scripts/kb/ingest_render.py`, `scripts/kb/ingest.py`, `scripts/kb/update_index.py`, `scripts/kb/lint_wiki.py`, `scripts/kb/write_utils.py`, `scripts/kb/persist_query.py`, `raw/inbox/SPEC.md`, `docs/architecture.md`, `.github/workflows/ci-2-analyst-diagnostics.yml`, `.github/workflows/ci-3-pr-producer.yml`, `.gitignore`

#### Diagnosis

This cluster has highly overlapping test files and covers a number of interconnected scripting and CI issues.
- `ingest.py` imports private underscore-prefixed symbols from its sibling `ingest_render.py`, violating ADR-011. Also uses synthetic SHA and one-by-one ingest.
- Update index lacks a lock.
- `scripts/kb/write_utils.py` fails to bounds-check symlinks after `resolve()`.
- CI workflows parse YAML redundantly, miss coverage gates, delete lock files manually, and lack workflow auth protections.
- Multiple workflows and specs have drift.

```python
# scripts/kb/update_index.py
def generate_and_write_index(wiki_root: Path) -> bool:
    content = _generate_index(wiki_root)
    # ... writes without lock
```

#### Proposed Solution

Remove the leading underscore from these symbols in `ingest_render.py`, export them via `__all__`, and update the callers. Use real SHA and implement batch processing.
Add exclusive_write_lock to update_index. Remove extra stat calls.
Add bounds checks `Path.resolve().is_relative_to()`. Fix workflow pipelines. Fix spec drifts.

```python
PROVISIONAL_GIT_SHA = "0" * 40
__all__ = ["PROVISIONAL_GIT_SHA"]

from scripts.kb import write_utils
with write_utils.exclusive_write_lock(wiki_root.parent):
    # write

resolved = path.resolve()
if not resolved.is_relative_to(repo_root):
    raise OSError("Escape attempted")
```

#### Test Plan
Run `pytest tests/kb/`. Run tests/kb/test_update_index.py and verify concurrent locking blocks correctly. Run tests/kb/test_write_utils.py with a symlink traversing to `/etc/passwd` to ensure failure. Ensure coverage check in CI passes.

---


## Task Plan

| # | Task | Root Cause | Issues | Risk |
|---|------|-----------|--------|------|
| 1 | Fix shell injection in fleet workflows | rc-fleet-shell-injection | #72 | Medium |
| 2 | Refactor optional surface common | rc-optional-surface-refactor | #64, #65, #67 | Medium |
| 3 | Fix KB write, indexing, persist, perf, CI, and doc issues | rc-kb-write-perf-ci-docs | #2, #3, #4, #5, #6, #7, #8, #9, #11, #12, #13, #14, #15, #16, #17, #18, #63, #66 | High |

## File Ownership Matrix

| File | Task | Change Type |
|---|---|---|
| `.github/workflows/fleet-dispatch.yml` | task-fix-shell-injection | Modify/Create |
| `.github/workflows/fleet-merge.yml` | task-fix-shell-injection | Modify/Create |
| `scripts/_optional_surface_common.py` | task-refactor-optional-surface | Modify/Create |
| `scripts/kb/qmd_preflight.py` | task-refactor-optional-surface | Modify/Create |
| `scripts/reporting/content_quality_report.py` | task-refactor-optional-surface | Modify/Create |
| `scripts/reporting/quality_runtime.py` | task-refactor-optional-surface | Modify/Create |
| `scripts/reporting/_artifact.py` | task-refactor-optional-surface | Modify/Create |
| `tests/kb/test_optional_surface_scripts.py` | task-refactor-optional-surface | Modify/Create |
| `tests/kb/test_qmd_preflight.py` | task-refactor-optional-surface | Modify/Create |
| `scripts/kb/ingest_render.py` | task-kb-write-perf-ci-docs | Modify/Create |
| `scripts/kb/ingest.py` | task-kb-write-perf-ci-docs | Modify/Create |
| `scripts/kb/update_index.py` | task-kb-write-perf-ci-docs | Modify/Create |
| `scripts/kb/lint_wiki.py` | task-kb-write-perf-ci-docs | Modify/Create |
| `scripts/kb/write_utils.py` | task-kb-write-perf-ci-docs | Modify/Create |
| `scripts/kb/persist_query.py` | task-kb-write-perf-ci-docs | Modify/Create |
| `raw/inbox/SPEC.md` | task-kb-write-perf-ci-docs | Modify/Create |
| `docs/architecture.md` | task-kb-write-perf-ci-docs | Modify/Create |
| `.github/workflows/ci-2-analyst-diagnostics.yml` | task-kb-write-perf-ci-docs | Modify/Create |
| `.github/workflows/ci-3-pr-producer.yml` | task-kb-write-perf-ci-docs | Modify/Create |
| `.gitignore` | task-kb-write-perf-ci-docs | Modify/Create |
| `tests/kb/test_ingest.py` | task-kb-write-perf-ci-docs | Modify/Create |
| `tests/kb/test_update_index.py` | task-kb-write-perf-ci-docs | Modify/Create |
| `tests/kb/test_lint_wiki.py` | task-kb-write-perf-ci-docs | Modify/Create |
| `tests/kb/test_write_utils.py` | task-kb-write-perf-ci-docs | Modify/Create |
| `tests/kb/test_persist_query.py` | task-kb-write-perf-ci-docs | Modify/Create |
| `tests/validation/test_workflow_actions.py` | task-kb-write-perf-ci-docs | Modify/Create |


## Unaddressable Issues

| Issue | Reason | Suggested Owner |
|-------|--------|-----------------|
| #19 | Requires explicit baseline metrics discussion and CI capacity planning. | Platform Team |
