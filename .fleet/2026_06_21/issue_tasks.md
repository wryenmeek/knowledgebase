# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 14 issues on 2026-06-21T09:48:12.279Z

## Executive Summary

I analyzed 14 open issues and identified 4 concrete root causes requiring code changes. 3 issues were determined to be unaddressable via repo-local code changes (they require environment configuration or external investigation). The remaining 7 issues are epics, QA gates, or tracker issues that don't map to specific bugs in the codebase. Overall health is good, with most issues being minor workflow/ratchet adjustments or deferred items from previous sessions.

## Root Cause Analysis

### RC-1: Missing workflow contract test for GITHUB_PR_HEAD_SHA pre-commit env

**Related issues:** #340
**Severity:** Low
**Files involved:** `tests/kb/test_pre_commit_workflow.py`

#### Diagnosis

Issue #340 notes that a previous PR remediation added `GITHUB_PR_HEAD_SHA: ${{ github.event.pull_request.head.sha }}` to the `.github/workflows/pre-commit.yml` workflow file under the "Run pre-commit on all files" step. However, no static contract test exists to assert this wiring is maintained over time.

There is currently no test for `pre-commit.yml` in `tests/kb/`. We need to add a test file `tests/kb/test_pre_commit_workflow.py` that loads the YAML and asserts the environment variable is present and correctly mapped.

#### Proposed Solution

Create `tests/kb/test_pre_commit_workflow.py`:

```python
"""Contract tests for pre-commit.yml workflow."""

from __future__ import annotations

import unittest
from pathlib import Path
import yaml

class PreCommitWorkflowContractTests(unittest.TestCase):
    def test_github_pr_head_sha_env_is_wired(self) -> None:
        """Assert GITHUB_PR_HEAD_SHA is wired in the 'Run pre-commit on all files' step."""
        workflow_path = Path(".github/workflows/pre-commit.yml")
        self.assertTrue(workflow_path.exists(), "pre-commit.yml missing")

        with open(workflow_path, "r", encoding="utf-8") as f:
            workflow = yaml.safe_load(f)

        jobs = workflow.get("jobs", {})
        pre_commit_job = jobs.get("pre-commit", {})
        steps = pre_commit_job.get("steps", [])

        target_step = None
        for step in steps:
            if step.get("name") == "Run pre-commit on all files":
                target_step = step
                break

        self.assertIsNotNone(target_step, "Could not find 'Run pre-commit on all files' step")

        env = target_step.get("env", {})
        self.assertIn("GITHUB_PR_HEAD_SHA", env, "GITHUB_PR_HEAD_SHA env var not set")
        self.assertEqual(
            env["GITHUB_PR_HEAD_SHA"],
            "${{ github.event.pull_request.head.sha }}",
            "GITHUB_PR_HEAD_SHA does not equal ${{ github.event.pull_request.head.sha }}"
        )

if __name__ == "__main__":
    unittest.main()
```

#### Test Plan

1. Run `pytest tests/kb/test_pre_commit_workflow.py` and confirm the test passes against the existing `.github/workflows/pre-commit.yml`.

---

### RC-2: Pre-commit hook time-bomb logic and ratchet loose inequality

**Related issues:** #300, #332
**Severity:** High
**Files involved:** `scripts/hooks/check_approval_flag.py`, `tests/kb/test_approval_migration_ratchet.py`

#### Diagnosis

Issue #300 describes two related bugs in `scripts/hooks/check_approval_flag.py` and its test `tests/kb/test_approval_migration_ratchet.py`:
1. The rejection for `--approval=` (equals form) occurs before `_EXEMPT_PATHS` is consulted. Since `scripts/_optional_surface_common.py` is in `_EXEMPT_PATHS` but legitimately contains the literal `"--approval="` to detect legacy callers, edits to the file will be incorrectly blocked by the pre-commit hook after the migration deadline (2026-12-31).
2. The approval flag script count ratchet in `tests/kb/test_approval_migration_ratchet.py` uses `==`, but Issue #332 requests an automated tripwire to fail after `2026-12-31` if legacy `--approval approved` compatibility scripts remain.

In `scripts/hooks/check_approval_flag.py:214-230`:
```python
        # Enforce equals-sign rejection before exemptions so transitional
        # compatibility files cannot silently keep the legacy equals syntax.
        if (
            _contains_approval_equals(staged_text)
            and _migration_deadline_passed()
        ):
            failures.append(
                f"{staged_path.path}: {_APPROVAL_EQUALS_TOKEN}<value> is forbidden after "
                f"{APPROVAL_EQUALS_REJECTION_DEADLINE.isoformat()}; use --apply"
            )
            continue
        if staged_path.path in _EXEMPT_PATHS:
            continue
```
This ordering rejects exempt files.

#### Proposed Solution

Fix 1: Move the exemption check above the equals check in `scripts/hooks/check_approval_flag.py`:
```python
        if read_error is not None:
            failures.append(read_error)
            continue

        # Only check exemptions, then check for equals-sign rejection.
        if staged_path.path in _EXEMPT_PATHS:
            continue

        if (
            _contains_approval_equals(staged_text)
            and _migration_deadline_passed()
        ):
            failures.append(
                f"{staged_path.path}: {_APPROVAL_EQUALS_TOKEN}<value> is forbidden after "
                f"{APPROVAL_EQUALS_REJECTION_DEADLINE.isoformat()}; use --apply"
            )
            continue
```

Fix 2: Add an automated tripwire for the deadline in `tests/kb/test_approval_migration_ratchet.py` to address Issue #332:
```python
# tests/kb/test_approval_migration_ratchet.py
from datetime import date
from scripts.kb.contracts import MAX_APPROVAL_FLAG_SCRIPTS

def test_approval_flag_deprecation_deadline_tripwire() -> None:
    """Tripwire to ensure legacy approval flags are fully removed by 2026-12-31 (ADR-030)."""
    if date.today() > date(2026, 12, 31):
        assert MAX_APPROVAL_FLAG_SCRIPTS == 0, (
            "ADR-030 approval-flag deprecation deadline has passed! "
            f"Expected MAX_APPROVAL_FLAG_SCRIPTS to be 0, but is {MAX_APPROVAL_FLAG_SCRIPTS}."
        )
```

#### Test Plan

1. Run `pytest tests/kb/test_approval_migration_ratchet.py` to ensure it passes.

---

### RC-3: Dead duplicate check in normalize_apply_alias

**Related issues:** #305 (P2 bundle)
**Severity:** Low
**Files involved:** `scripts/_optional_surface_common.py`, `tests/kb/test_optional_surface_common.py`

#### Diagnosis

Issue #305 bundles several minor issues:
The dead duplicate check in `scripts/_optional_surface_common.py:447-463`:
```python
def normalize_apply_alias(argv: Sequence[str]) -> list[str]:
    _LEGACY_APPROVAL_EQUALS_PREFIX = "--approval" + "="
    args = list(argv)
    if any(token.startswith(_LEGACY_APPROVAL_EQUALS_PREFIX) for token in args):
        raise ValueError(...)
    if "--apply" not in args:
        return args
    if "--approval" in args or any(token.startswith(_LEGACY_APPROVAL_EQUALS_PREFIX) for token in args):
        raise ValueError("--apply cannot be combined with --approval")
```
The `any(token.startswith(_LEGACY_APPROVAL_EQUALS_PREFIX) for token in args)` inside the second `if` is redundant because it would have raised a `ValueError` in the first check.

#### Proposed Solution

Update `scripts/_optional_surface_common.py`:

```python
<<<<<<< SEARCH
    if "--apply" not in args:
        return args
    if "--approval" in args or any(token.startswith(_LEGACY_APPROVAL_EQUALS_PREFIX) for token in args):
        raise ValueError("--apply cannot be combined with --approval")
=======
    if "--apply" not in args:
        return args
    if "--approval" in args:
        raise ValueError("--apply cannot be combined with --approval")
>>>>>>> REPLACE
```

#### Test Plan

1. Verify the script runs and the behavior is unchanged but without dead code by running `pytest tests/kb/test_optional_surface_common.py`.

---

### RC-4: Mutation diagnostics extractStatusCode gRPC mismatch

**Related issues:** #305 (P2 bundle)
**Severity:** Low
**Files involved:** `scripts/fleet/github/mutation-diagnostics.ts`, `scripts/fleet/github/mutation-diagnostics.test.ts`

#### Diagnosis

Issue #305 #7: `extractStatusCode` reads `record.code` as a number, so gRPC code 9 (FAILED_PRECONDITION) lands in `statusCode=9` and would silently match a hypothetical future `statusCode === 9` check. We should extract the status code cleanly.

```typescript
// scripts/fleet/github/mutation-diagnostics.ts:280
    // record.code may carry an HTTP status code (e.g. {"code":400,"status":"FAILED_PRECONDITION"})
    toNumberValue(record.code),
    toNumberValue(nestedError?.status),
    toNumberValue(nestedError?.statusCode),
    // nestedError.code may carry gRPC status code (e.g. {"error":{"code":9,"status":"FAILED_PRECONDITION"}})
    toNumberValue(nestedError?.code),
```

#### Proposed Solution

Update `scripts/fleet/github/mutation-diagnostics.ts` to omit `nestedError?.code` parsing.

```typescript
<<<<<<< SEARCH
    // nestedError.code may carry gRPC status code (e.g. {"error":{"code":9,"status":"FAILED_PRECONDITION"}})
    toNumberValue(nestedError?.code),
=======
>>>>>>> REPLACE
```

#### Test Plan

1. Run `cd scripts/fleet && bun test scripts/fleet/github/mutation-diagnostics.test.ts`

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Add workflow contract test for GITHUB_PR_HEAD_SHA pre-commit env | RC-1 | #340 | `tests/kb/test_pre_commit_workflow.py` | Low |
| 2 | Fix pre-commit time-bomb and ratchet loose inequality | RC-2 | #300, #332 | `scripts/hooks/check_approval_flag.py`, `tests/kb/test_approval_migration_ratchet.py` | Medium |
| 3 | Remove dead duplicate check in normalize_apply_alias | RC-3 | #305 | `scripts/_optional_surface_common.py`, `tests/kb/test_optional_surface_common.py` | Low |
| 4 | Remove gRPC code parsing from extractStatusCode | RC-4 | #305 | `scripts/fleet/github/mutation-diagnostics.ts`, `scripts/fleet/github/mutation-diagnostics.test.ts` | Low |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `tests/kb/test_pre_commit_workflow.py` | task-1-workflow-test | Create |
| `scripts/hooks/check_approval_flag.py` | task-2-approval-ratchet | Modify |
| `tests/kb/test_approval_migration_ratchet.py` | task-2-approval-ratchet | Modify |
| `scripts/_optional_surface_common.py` | task-3-dead-code | Modify |
| `tests/kb/test_optional_surface_common.py` | task-3-dead-code | Create |
| `scripts/fleet/github/mutation-diagnostics.ts` | task-4-grpc-code | Modify |
| `scripts/fleet/github/mutation-diagnostics.test.ts` | task-4-grpc-code | Modify |

## Unaddressable Issues

Issues that require changes outside this repository (backend API, infrastructure, product decisions, or manual operational steps):

| Issue | Reason | Suggested Owner |
|-------|--------|-----------------|
| #335 | CI-2 closure evidence checker flags recently closed issues. Requires a human operator to add closure evidence comments to old PRs/issues on GitHub. | Developer / Human Operator |
| #310 | Phase 2a auto-merge should use GitHub App token. The code support is already merged (uses `create-github-app-token`), but the App needs to be provisioned and secrets added to the repo settings. | DevOps / GitHub Admin |
| #156 | Deliver semantic query API + search integration. The scope is explicitly marked as "human-owned decision lane for hosting/deployment". | Architecture Team |
| #82 | Investigate Jules API FAILED_PRECONDITION error. External API issue requiring validation of JULES_API_KEY entitlement and account linkage. | Backend/API Team |
| #188 | PR4 — Wire CI-3 + execute checkpoint-registry bootstrap runbook. This is marked as "HITL operator step" and requires operator execution. | Release Manager |
| #194, #196, #198, #207, #212 | Spikes, validations, and real-use exercises. These are epics/trackers for manual steps and observations, not actionable codebase fixes. | QA / Human Operator |
