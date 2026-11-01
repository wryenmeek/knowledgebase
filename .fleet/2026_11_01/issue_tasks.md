# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 1 issues on 2026-11-01T12:41:48.912Z

## Executive Summary

Found 1 root cause corresponding to an architectural gap for the requested Infigraph integration. The issue is addressable and involves creating a new wrapper module with normalized statuses, capability checks, and pinned metadata, alongside corresponding tests.

## Root Cause Analysis

### RC-1: Missing Infigraph runtime wrapper and capability discovery

**Related issues:** #597
**Severity:** Medium
**Files involved:** `scripts/kb/infigraph.py` (new), `tests/kb/test_infigraph.py` (new)

#### Diagnosis

The codebase currently lacks any integration with the Infigraph CLI. The knowledgebase integration requires a way to invoke a pinned version of Infigraph, verify its capabilities at startup, and handle execution failures gracefully with normalized statuses (`analysis_complete`, `analysis_unavailable`, `analysis_failed`).

#### Proposed Solution

**Integration points**
Create a new module `scripts/kb/infigraph.py` that defines the integration contract and pinned metadata. No existing files need to be modified, this is a clean addition.

**Implementation:**

```python
# scripts/kb/infigraph.py
import dataclasses
import json
import logging
import subprocess
from typing import Literal, Optional

logger = logging.getLogger(__name__)

# Pinned metadata for CI verification
INFIGRAPH_MANIFEST = {
    "version": "1.0.0",
    "sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
    "url": "https://example.com/infigraph/v1.0.0/infigraph-linux-amd64"
}

@dataclasses.dataclass
class InfigraphResult:
    status: Literal["analysis_complete", "analysis_unavailable", "analysis_failed"]
    reason: Optional[str] = None
    capabilities: list[str] = dataclasses.field(default_factory=list)

def check_capabilities(executable_path: str) -> InfigraphResult:
    try:
        # Use an explicit timeout to prevent unbounded hangs
        result = subprocess.run(
            [executable_path, "capabilities", "--format=json"],
            capture_output=True,
            text=True,
            timeout=5
        )
    except FileNotFoundError:
        return InfigraphResult(status="analysis_unavailable", reason="Executable not found")
    except subprocess.TimeoutExpired:
        return InfigraphResult(status="analysis_failed", reason="Command timed out")
    except Exception as e:
        return InfigraphResult(status="analysis_failed", reason=str(e))

    if result.returncode != 0:
        return InfigraphResult(
            status="analysis_unavailable",
            reason=f"Executable failed (code {result.returncode}): {result.stderr.strip() or 'Unknown error'}"
        )

    try:
        data = json.loads(result.stdout)
        return InfigraphResult(
            status="analysis_complete",
            capabilities=data.get("capabilities", [])
        )
    except json.JSONDecodeError:
        return InfigraphResult(status="analysis_failed", reason="Malformed JSON output")

```

**Edge cases and risks**
- `subprocess.run` hangs: mitigated by explicit `timeout=5`.
- `result.stderr` might be `None` or empty: mitigated by safe fallback `result.stderr.strip() or 'Unknown error'` and ensuring we don't crash on `None`.
- Executable missing: Handled by catching `FileNotFoundError`.
- JSON output malformed: Handled by catching `json.JSONDecodeError`.

#### Test Plan

Create `tests/kb/test_infigraph.py` to cover:
1. `test_successful_capability_discovery`: Fake executable returns 0 and valid JSON. Returns `analysis_complete` with capabilities.
2. `test_executable_not_found`: Path does not exist. Returns `analysis_unavailable` with "Executable not found".
3. `test_command_timeout`: Mock `subprocess.run` to raise `subprocess.TimeoutExpired`. Returns `analysis_failed`.
4. `test_malformed_output`: Fake executable returns 0 but invalid JSON. Returns `analysis_failed`.
5. `test_execution_failure`: Fake executable returns non-zero. Returns `analysis_unavailable`.

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Add reproducible Infigraph runtime wrapper | RC-1 | #597 | `scripts/kb/infigraph.py` | Low |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/kb/infigraph.py` | 1 | Create |
| `tests/kb/test_infigraph.py` | 1 | Create |

## Unaddressable Issues

Issues that require changes outside this repository (backend API, infrastructure, product decisions):

| Issue | Reason | Suggested Owner |
|-------|--------|-----------------|
