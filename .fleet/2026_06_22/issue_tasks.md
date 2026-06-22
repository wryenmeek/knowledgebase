# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 18 issues on 2026-06-22T11:51:20.081Z

## Executive Summary

Found 5 root causes across the codebase. 5 addressable tasks have been generated. The remaining issues are either tracking issues, require human operator actions, or involve manual QA validation and spikes.

## Root Cause Analysis

### rc-tests-check-approval-flag: Missing prophylactic test coverage for check_approval_flag.py

**Related issues:** #367, #305
**Severity:** Low
**Files involved:** `scripts/hooks/check_approval_flag.py`

#### Diagnosis

Deferred test-coverage gaps from PR #363 cross-functional review and #305 post-merge review for check_approval_flag.py.

Code Path: `scripts/hooks/check_approval_flag.py` lines 102, 121-124 (Rename R-status detection)

Mechanism: The hook uses `git diff --cached --find-renames --find-copies` and parses 3-column R-status output. No test exercises `status="R"` or `status_code="C"`. The real failure mode that bug #300 fixed was a commit touching an exempt file AND a non-exempt file together, which is never asserted.

#### Proposed Solution

Add new test functions in test_approval_migration_ratchet.py for the missing coverage areas and rename the sibling test in test_test_framework_ratchet.py.

```python
def test_hook_returns_zero_when_no_scripts_staged(mock_staged_script_paths):
    mock_staged_script_paths.return_value = ([], None)
    assert main() == 0
```

#### Test Plan

1. Run pytest tests/kb/test_approval_migration_ratchet.py.
2. Ensure the new test functions for empty staged diff, rename status, and mixed files pass.

---

### rc-fleet-label-driven-dispatch: Adopt label-driven dispatch and fix auto-merge layer

**Related issues:** #350, #310
**Severity:** Medium
**Files involved:** `scripts/fleet/github/issues.ts`, `scripts/fleet/github/markdown.ts`, `scripts/fleet/fleet-plan.ts`, `scripts/fleet/fleet-dispatch.ts`, `scripts/fleet/fleet-merge.ts`, `scripts/fleet/archive-stale-sessions.ts`, `.github/workflows/fleet-dispatch-after-merge.yml`

#### Diagnosis

The fleet pipeline currently does not support label-driven dispatch (#350) and Phase 2a auto-merge fails to trigger Phase 2b because it uses GITHUB_TOKEN instead of a GitHub App token (#310).

Code Path: `scripts/fleet/github/issues.ts::getIssues`

Mechanism: `getIssues` accepts only `state`/`perPage` but does NOT filter by label. GitHub Actions documents that events triggered by GITHUB_TOKEN do not create new workflow runs, which breaks the queue auto-merge.

#### Proposed Solution

Adopt HSI ADR-030 label-driven dispatch with a 3-strikes abort condition. Update the workflow fleet-dispatch-after-merge.yml to use a GitHub App token for the queue auto-merge step and add a concurrency group.

```typescript
<<<<<<< SEARCH
export async function getIssues(
  options?: { perPage?: number; state?: "open" | "closed" | "all" }
) {
=======
export async function getIssues(
  options?: { perPage?: number; state?: "open" | "closed" | "all"; labels?: string[] }
) {
>>>>>>> REPLACE
```

#### Test Plan

1. Run bun test scripts/fleet/github/issues.test.ts.
2. Ensure that labels are properly concatenated when passed to getIssues.

---

### rc-minor-improvements-p2: Minor code improvements from post-merge review

**Related issues:** #305
**Severity:** Low
**Files involved:** `scripts/kb/write_utils.py`, `scripts/_optional_surface_common.py`, `.github/workflows/jules-archive-stale.yml`, `scripts/fleet/github/mutation-diagnostics.ts`

#### Diagnosis

Various minor P2 improvements from a post-merge retrospective review.

Code Path: `scripts/kb/write_utils.py:300-306`

Mechanism: `_read_lock_holder_details` doesn't catch `UnicodeDecodeError` (subclass of `ValueError`, not `OSError`). A corrupted lock file with non-UTF-8 bytes would crash inside `LockUnavailableError.__init__`.

#### Proposed Solution

Fix Exception handling in write_utils.py, remove dead code in normalize_apply_alias, add concurrency block to workflow, and update mutation diagnostics.

```python
<<<<<<< SEARCH
    except (OSError, UnicodeDecodeError):
=======
    except (OSError, UnicodeDecodeError, ValueError):
>>>>>>> REPLACE
```

#### Test Plan

1. Run pytest tests/kb/test_write_utils.py.
2. Ensure corrupted lock files raise ValueError gracefully.

---

### rc-trim-context-md: Cosmetic: trim CONTEXT.md silent-revert PR defense-mechanism detail

**Related issues:** #354
**Severity:** Low
**Files involved:** `CONTEXT.md`

#### Diagnosis

The CONTEXT.md file contains defense-mechanism detail for the 'silent-revert PR' term which is not strict glossary format.

Code Path: `CONTEXT.md` row for `silent-revert PR`.

Mechanism: The final sentence describes the defense mechanism, not the term definition.

#### Proposed Solution

Trim the term to Option A (minimal) as proposed in issue #354 and bump the last_updated frontmatter.

```markdown
<<<<<<< SEARCH
| silent-revert PR | A PR whose title/scope suggests a small or unrelated change but whose diff silently removes substantial content from sensitive paths. The canonical example is Scribe's `bolt: ...` PR (sha `82d56196`) that deleted 2474 lines of docs/strategies under a `bolt` scope label. Tier 0 defensive layer (issue #342) gates against this pattern via the commit-scope check (gates B + C) and the stale bot-branch sweeper. |
=======
| silent-revert PR | A PR whose title/scope suggests a small or unrelated change but whose diff silently removes substantial content from sensitive paths. The canonical example is Scribe's `bolt: ...` PR (sha `82d56196`) that deleted 2474 lines of docs/strategies under a `bolt` scope label. Defended by Tier 0 layer (see issue #342). |
>>>>>>> REPLACE
```

#### Test Plan

1. Run pytest tests/kb/test_context_md_freshness.py.
2. Ensure it passes without syntax errors.

---

### rc-checkpoint-registry-bootstrap: Wire CI-3 + execute checkpoint-registry bootstrap runbook

**Related issues:** #188
**Severity:** High
**Files involved:** `.github/workflows/ci-3-pr-producer.yml`, `docs/mvp-runbook.md`, `docs/architecture.md`

#### Diagnosis

CI-3 needs to be wired to invoke the runtime from #187 and the bootstrap runbook needs to be executed to seed the initial registry.

Code Path: `.github/workflows/ci-3-pr-producer.yml`

Mechanism: CI wiring is mechanical but cannot land alone because `--mutate` would fail against a non-existent registry.

#### Proposed Solution

Modify ci-3-pr-producer.yml to invoke checkpoint_registry.py --mutate per batch. Execute the bootstrap runbook and commit the resulting json.

```yaml
<<<<<<< SEARCH
      - name: Run CI-3 processing (dry run)
        run: python3 scripts/kb/checkpoint_registry.py
=======
      - name: Run CI-3 processing
        run: |
          python3 scripts/kb/checkpoint_registry.py --mutate
          python3 scripts/kb/checkpoint_registry.py --verify --warn-only >> $GITHUB_STEP_SUMMARY
>>>>>>> REPLACE
```

#### Test Plan

1. Verify .github/workflows/ci-3-pr-producer.yml has valid syntax using actionlint.
2. Verify the new wiki-processing-checkpoint-registry.json.

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Add test coverage for check_approval_flag.py | rc-tests-check-approval-flag | #367, #305 | `scripts/hooks/check_approval_flag.py` | Low |
| 2 | Adopt label-driven dispatch and GitHub App token for fleet | rc-fleet-label-driven-dispatch | #350, #310 | `scripts/fleet/github/issues.ts`, `scripts/fleet/github/markdown.ts`, `scripts/fleet/fleet-plan.ts`, `scripts/fleet/fleet-dispatch.ts`, `scripts/fleet/fleet-merge.ts`, `scripts/fleet/archive-stale-sessions.ts`, `.github/workflows/fleet-dispatch-after-merge.yml`, `docs/decisions/ADR-032-fleet-quota-saturation-soft-warn.md`, `docs/decisions/README.md`, `AGENTS.md`, `tests/kb/test_framework_write_surface_matrix.py` | Medium |
| 3 | Minor codebase improvements from P2 bundle | rc-minor-improvements-p2 | #305 | `scripts/kb/write_utils.py`, `scripts/_optional_surface_common.py`, `.github/workflows/jules-archive-stale.yml`, `scripts/fleet/github/mutation-diagnostics.ts` | Low |
| 4 | Trim CONTEXT.md silent-revert PR detail | rc-trim-context-md | #354 | `CONTEXT.md` | Low |
| 5 | Wire CI-3 and execute checkpoint-registry bootstrap | rc-checkpoint-registry-bootstrap | #188 | `.github/workflows/ci-3-pr-producer.yml`, `docs/mvp-runbook.md`, `docs/architecture.md` | High |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/hooks/check_approval_flag.py` | task-tests-check-approval-flag | Modify |
| `tests/kb/test_approval_migration_ratchet.py` | task-tests-check-approval-flag | Modify |
| `tests/kb/test_test_framework_ratchet.py` | task-tests-check-approval-flag | Modify |
| `scripts/fleet/github/issues.ts` | task-fleet-label-driven-dispatch | Modify |
| `scripts/fleet/github/markdown.ts` | task-fleet-label-driven-dispatch | Modify |
| `scripts/fleet/fleet-plan.ts` | task-fleet-label-driven-dispatch | Modify |
| `scripts/fleet/fleet-dispatch.ts` | task-fleet-label-driven-dispatch | Modify |
| `scripts/fleet/fleet-merge.ts` | task-fleet-label-driven-dispatch | Modify |
| `scripts/fleet/archive-stale-sessions.ts` | task-fleet-label-driven-dispatch | Modify |
| `.github/workflows/fleet-dispatch-after-merge.yml` | task-fleet-label-driven-dispatch | Modify |
| `docs/decisions/ADR-032-fleet-quota-saturation-soft-warn.md` | task-fleet-label-driven-dispatch | Modify |
| `docs/decisions/README.md` | task-fleet-label-driven-dispatch | Modify |
| `AGENTS.md` | task-fleet-label-driven-dispatch | Modify |
| `tests/kb/test_framework_write_surface_matrix.py` | task-fleet-label-driven-dispatch | Modify |
| `docs/decisions/ADR-033-fleet-label-driven-dispatch-adoption.md` | task-fleet-label-driven-dispatch | Modify |
| `docs/decisions/ADR-034-fleet-no-notification-on-quota-saturation.md` | task-fleet-label-driven-dispatch | Modify |
| `scripts/fleet/fleet-plan.test.ts` | task-fleet-label-driven-dispatch | Modify |
| `scripts/fleet/fleet-dispatch.test.ts` | task-fleet-label-driven-dispatch | Modify |
| `scripts/fleet/fleet-merge.test.ts` | task-fleet-label-driven-dispatch | Modify |
| `scripts/fleet/archive-stale-sessions.test.ts` | task-fleet-label-driven-dispatch | Modify |
| `tests/kb/test_fleet_dispatch_after_merge_workflow.py` | task-fleet-label-driven-dispatch | Modify |
| `tests/kb/test_doc_cascade_completeness.py` | task-fleet-label-driven-dispatch | Modify |
| `tests/kb/test_adr_readme_status_sync.py` | task-fleet-label-driven-dispatch | Modify |
| `scripts/kb/write_utils.py` | task-minor-improvements-p2 | Modify |
| `scripts/_optional_surface_common.py` | task-minor-improvements-p2 | Modify |
| `.github/workflows/jules-archive-stale.yml` | task-minor-improvements-p2 | Modify |
| `scripts/fleet/github/mutation-diagnostics.ts` | task-minor-improvements-p2 | Modify |
| `tests/kb/test_write_utils.py` | task-minor-improvements-p2 | Modify |
| `tests/kb/test_optional_surface_common.py` | task-minor-improvements-p2 | Modify |
| `scripts/fleet/github/mutation-diagnostics.test.ts` | task-minor-improvements-p2 | Modify |
| `scripts/fleet/fleet-entrypoint-fatal.test.ts` | task-minor-improvements-p2 | Modify |
| `tests/kb/test_jules_archive_stale_workflow.py` | task-minor-improvements-p2 | Modify |
| `CONTEXT.md` | task-trim-context-md | Modify |
| `tests/kb/test_context_md_freshness.py` | task-trim-context-md | Modify |
| `tests/kb/test_context_import_helpers.py` | task-trim-context-md | Modify |
| `.github/workflows/ci-3-pr-producer.yml` | task-checkpoint-registry-bootstrap | Modify |
| `docs/mvp-runbook.md` | task-checkpoint-registry-bootstrap | Modify |
| `docs/architecture.md` | task-checkpoint-registry-bootstrap | Modify |
| `raw/wiki-processing/wiki-processing-checkpoint-registry.json` | task-checkpoint-registry-bootstrap | Modify |
| `tests/kb/test_ci3_workflow.py` | task-checkpoint-registry-bootstrap | Modify |
| `tests/kb/test_checkpoint_registry.py` | task-checkpoint-registry-bootstrap | Modify |

## Unaddressable Issues

Issues that require changes outside this repository (backend API, infrastructure, product decisions):

| Issue | Reason | Suggested Owner |
|-------|--------|-----------------|
| #368 | Tracking issue - do not close; do not edit body. | Human / wryenmeek |
| #366 | Requires manual operator action via gh cli and UI to create label and tracking issue. | Human / wryenmeek |
| #365 | Requires manual audit of PRs over a 90-day window to calculate false positive rate. | Human / wryenmeek |
| #364 | Requires human decision on whether to promote CODEOWNERS after 30-day evaluation. | Human / wryenmeek |
| #353 | Requires human decision on Tier 3 multi-provider fallback based on public surface maturity. | Human / wryenmeek |
| #351 | Requires 14 days of clean observation data before flipping to dry_run: false. | Human / wryenmeek |
| #341 | Phase 1 is superseded by #350 (no notification on quota saturation). Phase 2/3 require Copilot SWE agent activation which is an admin/human task. | Human / wryenmeek |
| #156 | Human-owned decision lane for semantic query API hosting/deployment. | Human / wryenmeek |
| #194 | Requires manual smoke test in CLI 1.0.60 session to validate Mechanism B. | QA / Human |
| #196 | Phase 1.5 spike requires manual measurement of compliance rate via CLI and VS Code Chat. | QA / Human |
| #198 | Requires adversarial review by humans (@code-reviewer, @security-auditor, etc.) and manual fixture testing. | QA / Security Auditor |
| #207 | Requires manual review of every finding for hallucination, citation grounding, and adversarial inputs. | QA / Human |
| #212 | Requires manual execution of CLI and VS Code Chat sessions to compute set-equivalence. | QA / Human |
