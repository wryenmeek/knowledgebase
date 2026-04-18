# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 15 issues on 2026-04-18T07:15:39.376Z

## Executive Summary

Found 15 addressable issues spanning CI performance, script scaling bottlenecks, security vulnerabilities, and testing gaps. Issues were synthesized into 3 non-overlapping Root Causes based on source-file coupling to ensure sub-agents can work without merge conflicts.

## Root Cause Analysis

### RC-1: Python Scripts Performance, Contracts, & Security Parity
**Related issues:** #2, #3, #4, #5, #7, #8, #17, #18
**Severity:** High
**Files involved:** `scripts/kb/ingest.py`, `scripts/kb/persist_query.py`, `scripts/kb/update_index.py`, `scripts/kb/lint_wiki.py`, `scripts/kb/write_utils.py`, `tests/kb/test_ingest.py`, `tests/kb/test_persist_query.py`, `tests/kb/test_update_index.py`, `tests/kb/test_lint_wiki.py`, `tests/kb/test_write_utils.py`, `raw/processed/SPEC.md`, `docs/architecture.md`

#### Diagnosis

1. **#2 Symlink escapes**: `_write_text_atomically` and `_restore_previous_content` currently use `_ensure_not_symlink` which traverses upwards to `current.parent == current`, but does not bound it to `repo_root`.
2. **#3 Update index lock**: `update_index.py:246` calls `with exclusive_write_lock(wiki_root.parent):`. This acquires the lock on the parent directory, but the requirement is to ensure the local write lock uses the explicit repo root `.` for consistent locking semantics.
3. **#4 Synthetic SHAs**: `ingest.py:108` hardcodes `_PROVISIONAL_GIT_SHA = "0000000000000000000000000000000000000000"`.
4. **#5 Spec drift**: `docs/architecture.md` claims entity/concept generation, which is unimplemented.
5. **#7 & #8 persist_query flags**: `persist_query.py:141` exposes `--result-json` as a no-op, and `--has-unresolved-contradiction` is confusingly implemented without an explicit disable form.
6. **#17 persist_query index rebuild**: `persist_query.py:404` unconditionally calls `index_updated = _update_index_if_changed(request.wiki_root)`.
7. **#18 Repeated Parse Passes**: `update_index.py:81` (`_extract_frontmatter`) uses `lines = markdown_text.splitlines()`, which allocates the entire file into a list of strings just to extract a small frontmatter block.

#### Proposed Solution

**1. Symlink escape fix (`write_utils.py` and `ingest.py`)**

```python
# scripts/kb/write_utils.py
def ensure_safe_write_path(path: Path, repo_root: Path) -> None:
    current = path.resolve()
    if not current.is_relative_to(repo_root.resolve()):
        raise OSError(f"path escapes repo root: {path}")

    current_check = path
    while current_check != current_check.parent:
        if current_check.is_symlink():
            raise OSError(f"symlinked path component is not allowed: {current_check}")
        if current_check.resolve() == repo_root.resolve():
            break
        current_check = current_check.parent
```

Replace `_ensure_not_symlink` in `ingest.py` with this shared utility, passing `repo_root`.

**2. Update index lock (`update_index.py`)**

```diff
-        with exclusive_write_lock(wiki_root.parent):
+        with exclusive_write_lock("."):
```

**3. Synthetic SHAs (`ingest.py`)**

```python
# scripts/kb/ingest.py
def _resolve_provenance_sha() -> str:
    if "GITHUB_SHA" in os.environ:
        return os.environ["GITHUB_SHA"]
    try:
        import subprocess
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        if len(sha) == 40:
            return sha
    except Exception:
        pass
    raise IngestError(contracts.ReasonCode.INVALID_INPUT.value, "Could not resolve git SHA provenance")

# Replace _PROVISIONAL_GIT_SHA usages with _resolve_provenance_sha()
```

**4. Spec Drift (`docs/architecture.md`, `raw/processed/SPEC.md`)**

Remove references to `wiki/entities/**` and `wiki/concepts/**` generation from the specs. Keep only `wiki/sources/**`.

**5. persist_query flags (`persist_query.py`)**

Remove the `--result-json` block from argparse.
Make contradiction explicitly configurable:
```python
    parser.add_argument(
        "--unresolved-contradiction",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Explicitly mark if result has unresolved contradictions.",
    )
```

**6. persist_query index rebuild (`persist_query.py`)**

```diff
-                index_updated = _update_index_if_changed(request.wiki_root)
-                state_changed = analysis_changed or index_updated
+                index_updated = False
+                if analysis_changed:
+                    index_updated = _update_index_if_changed(request.wiki_root)
+                state_changed = analysis_changed
```

**7. Repeated Parse Passes (`update_index.py`, `lint_wiki.py`)**

```python
import re
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL | re.MULTILINE)

def _extract_frontmatter(markdown_text: str, page_path: Path) -> str:
    match = _FRONTMATTER_RE.search(markdown_text)
    if not match:
        raise IndexGenerationError(f"{page_path}: missing YAML frontmatter delimiters")
    return match.group(1)
```

#### Test Plan
- Run `test_ingest.py`, `test_persist_query.py`, `test_update_index.py`, `test_lint_wiki.py`, `test_write_utils.py`.
- Add test in `test_persist_query.py` verifying index is skipped if `analysis_changed` is False.
- Add test in `test_ingest.py` for correct Git SHA fallback.

---

### RC-2: CI-3 Optimizations and Security Gaps
**Related issues:** #9, #11, #14, #15
**Severity:** High
**Files involved:** `.github/workflows/ci-3-pr-producer.yml`, `tests/kb/test_ci3_workflow.py`

#### Diagnosis

**#14 & #15 CI-3 Batching and GITHUB_OUTPUT**:
```yaml
# .github/workflows/ci-3-pr-producer.yml
          echo "has_sources=true" >> "${GITHUB_OUTPUT}"
          {
            echo "sources<<EOF"
            printf '%s\n' "${source_paths[@]}"
            echo "EOF"
          } >> "${GITHUB_OUTPUT}"
...
          while IFS= read -r source_path; do
            ...
            ingest_json="$(python3 -m scripts.kb.ingest \
              --source "${source_path}" \
```
This hits multiline GITHUB_OUTPUT limits and invokes python loop per-file.

**#9 Lock Deletion**:
```yaml
          rm -f wiki/.kb_write.lock
```

**#11 Authoritative Approval**:
Manual dispatch checks environment but needs an actor validation script block to strictly enforce role limits for manual pushes.

#### Proposed Solution

**Batching & Handoff**:
```diff
-          {
-            echo "sources<<EOF"
-            printf '%s\n' "${source_paths[@]}"
-            echo "EOF"
-          } >> "${GITHUB_OUTPUT}"
+          printf '%s\n' "${source_paths[@]}" > ci3_sources.manifest
...
-          while IFS= read -r source_path; do
-            ...
-          done <<< "${SOURCE_LIST}"
+          echo "[CI-3] ingest batch"
+          set +e
+          ingest_json="$(python3 -m scripts.kb.ingest \
+            --sources-manifest ci3_sources.manifest \
+            --batch-policy continue_and_report_per_source \
+            --wiki-root wiki \
+            --schema AGENTS.md \
+            --report-json)"
+          ingest_exit=$?
```

**Lock Deletion**:
Remove `rm -f wiki/.kb_write.lock`.

**Authoritative Approval**:
In `ci3-manual-approval` job, add an explicit check to verify the triggering actor belongs to the authorized maintainers team or hardcode an explicit failure if authorization fails.
```yaml
      - name: Confirm protected-environment approval
        run: |
          set -euo pipefail
          if [[ "${{ github.actor }}" != "wryenmeek" ]]; then
            echo "::error::Unauthorized actor for manual dispatch."
            false
          fi
          echo "CI-3 manual dispatch approved via protected environment reviewers."
```

#### Test Plan
- `tests/kb/test_ci3_workflow.py` updated to expect `--sources-manifest` and lack of `rm -f`. Test actor string validation.

---

### RC-3: CI-2 Coverage & Global Repo Hygiene
**Related issues:** #6, #12, #13, #16
**Severity:** Medium
**Files involved:** `.github/workflows/ci-2-analyst-diagnostics.yml`, `tests/kb/test_workflow_yaml_syntax.py`, `tests/kb/test_integration_verification_matrix.py`, `tests/kb/test_unit_verification_matrix.py`, `.gitignore`

#### Diagnosis

**#16 Duplicate YAML Parsing**:
CI-2 yaml:
```yaml
      - name: Validate workflow YAML syntax
        run: |
          set -euo pipefail
          ruby -e '...'
```
This is a duplicate of `tests/kb/test_workflow_yaml_syntax.py`.

**#6 Verification Matrix Gaps & Coverage Target**:
Tests are missing in `test_integration_verification_matrix.py` and `test_unit_verification_matrix.py`. No enforcement of 90% coverage in CI-2.

**#12 `.gitignore`**:
Missing `.env.local` and `.claude/`.

#### Proposed Solution

**CI-2 Coverage**:
Remove `Validate workflow YAML syntax` step from `ci-2-analyst-diagnostics.yml`.
Modify the test step:
```diff
-          echo "[CI-2] unittest discover" | tee -a diagnostics/diagnostics.log
-          python3 -m unittest discover -s tests -p 'test_*.py' 2>&1 | tee -a diagnostics/diagnostics.log
+          echo "[CI-2] unittest discover and coverage" | tee -a diagnostics/diagnostics.log
+          pip install coverage
+          python3 -m coverage run -m unittest discover -s tests -p 'test_*.py' 2>&1 | tee -a diagnostics/diagnostics.log
+          python3 -m coverage report -m --fail-under=90 2>&1 | tee -a diagnostics/diagnostics.log
```

**Gitignore**:
```diff
+ .env.local
+ .env.*.local
+ .claude/
```

**Matrix Gaps (#6, #13)**:
Add explicit test blocks into the integration matrices covering mermaid parsing logic, `persist_query` regression guards, and symlink destination tests.

#### Test Plan
- Matrix tests pass locally. CI-2 coverage executes properly and passes.

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Python Tooling Enhancements | RC-1 | #2, #3, #4, #5, #7, #8, #17, #18 | `scripts/kb/ingest.py`, `scripts/kb/persist_query.py`, `scripts/kb/update_index.py`, `scripts/kb/lint_wiki.py`, `scripts/kb/write_utils.py`, `tests/kb/test_ingest.py`, `tests/kb/test_persist_query.py`, `tests/kb/test_update_index.py`, `tests/kb/test_lint_wiki.py`, `tests/kb/test_write_utils.py`, `raw/processed/SPEC.md`, `docs/architecture.md` | High |
| 2 | CI-3 Automation Improvements | RC-2 | #9, #11, #14, #15 | `.github/workflows/ci-3-pr-producer.yml`, `tests/kb/test_ci3_workflow.py` | Low |
| 3 | CI-2 Coverage & Repo Hygiene | RC-3 | #6, #12, #13, #16 | `.github/workflows/ci-2-analyst-diagnostics.yml`, `tests/kb/test_workflow_yaml_syntax.py`, `tests/kb/test_integration_verification_matrix.py`, `tests/kb/test_unit_verification_matrix.py`, `.gitignore` | Medium |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/kb/ingest.py` | 1 | Modify |
| `scripts/kb/persist_query.py` | 1 | Modify |
| `scripts/kb/update_index.py` | 1 | Modify |
| `scripts/kb/lint_wiki.py` | 1 | Modify |
| `scripts/kb/write_utils.py` | 1 | Modify |
| `tests/kb/test_ingest.py` | 1 | Modify |
| `tests/kb/test_persist_query.py` | 1 | Modify |
| `tests/kb/test_update_index.py` | 1 | Modify |
| `tests/kb/test_lint_wiki.py` | 1 | Modify |
| `tests/kb/test_write_utils.py` | 1 | Modify |
| `raw/processed/SPEC.md` | 1 | Modify |
| `docs/architecture.md` | 1 | Modify |
| `.github/workflows/ci-3-pr-producer.yml` | 2 | Modify |
| `tests/kb/test_ci3_workflow.py` | 2 | Modify |
| `.github/workflows/ci-2-analyst-diagnostics.yml` | 3 | Modify |
| `tests/kb/test_workflow_yaml_syntax.py` | 3 | Modify |
| `tests/kb/test_integration_verification_matrix.py` | 3 | Modify |
| `tests/kb/test_unit_verification_matrix.py` | 3 | Modify |
| `.gitignore` | 3 | Modify |

## Unaddressable Issues

| Issue | Reason | Suggested Owner |
|-------|--------|-----------------|
| #19 | CI timing telemetry should be implemented as an explicit external analytics job or dashboard rather than hacking GHA steps | Ops / Infra team |
