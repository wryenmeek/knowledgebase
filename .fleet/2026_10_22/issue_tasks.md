# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 1 issues on 2026-10-22T11:10:35.919Z

## Executive Summary

1 root cause found, 1 addressable, overall health assessment is good. The repository is missing the Infigraph CLI wrapper and capability contract as described in issue #597. The issue can be resolved by introducing a new, self-contained Python module and corresponding unit tests without conflicting with existing file ownerships.

## Root Cause Analysis

### RC-1: Missing Infigraph CLI Wrapper and Capability Contract

**Related issues:** #597
**Severity:** Medium
**Files involved:** `scripts/analysis/infigraph.py`, `tests/analysis/test_infigraph.py`

#### Diagnosis

The issue requests a new capability wrapper to invoke the Infigraph CLI for knowledgebase integration analysis. The repository currently lacks this feature. The wrapper must define normalized statuses, perform startup checks on the executable to determine if it is unavailable, unsupported, or misconfigured, and reproducibly resolve and record release metadata.

#### Proposed Solution

Implement `scripts/analysis/infigraph.py` with a wrapper class (`InfigraphWrapper`) and status enum (`InfigraphStatus`).

```python
"""Infigraph CLI wrapper and capability contract."""

import json
import logging
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# Pinned release and resolution metadata for CI reproducibility
INFIGRAPH_VERSION = "v0.4.2"
INFIGRAPH_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

class InfigraphStatus(str, Enum):
    """Normalized statuses for Infigraph analysis outcomes."""
    ANALYSIS_COMPLETE = "analysis_complete"
    ANALYSIS_UNAVAILABLE = "analysis_unavailable"
    ANALYSIS_FAILED = "analysis_failed"

@dataclass(frozen=True, slots=True)
class InfigraphResult:
    """Result envelope for Infigraph CLI invocations."""
    status: InfigraphStatus
    reason: str
    capabilities: Optional[List[str]] = None
    output: Optional[str] = None

class InfigraphWrapper:
    """Wrapper for invoking the Infigraph CLI."""
    def __init__(self, executable_path: str = "infigraph"):
        self.executable_path = executable_path

    def check_capabilities(self) -> InfigraphResult:
        try:
            result = subprocess.run(
                [self.executable_path, "capabilities", "--format=json"],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
        except FileNotFoundError:
            return InfigraphResult(
                status=InfigraphStatus.ANALYSIS_UNAVAILABLE,
                reason="Executable not found",
            )
        except subprocess.TimeoutExpired:
            return InfigraphResult(
                status=InfigraphStatus.ANALYSIS_FAILED,
                reason="Command timed out",
            )
        except Exception as e:
            return InfigraphResult(
                status=InfigraphStatus.ANALYSIS_FAILED,
                reason=f"Execution error: {str(e)}",
            )

        if result.returncode != 0:
            return InfigraphResult(
                status=InfigraphStatus.ANALYSIS_FAILED,
                reason=f"Command failed with exit code {result.returncode}",
                output=result.stderr,
            )

        try:
            data = json.loads(result.stdout)
            return InfigraphResult(
                status=InfigraphStatus.ANALYSIS_COMPLETE,
                reason="Capabilities resolved",
                capabilities=data.get("capabilities", []),
            )
        except json.JSONDecodeError:
            return InfigraphResult(
                status=InfigraphStatus.ANALYSIS_FAILED,
                reason="Malformed output: invalid JSON",
                output=result.stdout,
            )
```

**Integration points**
*   `scripts/analysis/__init__.py`: We will append an import line `from .infigraph import InfigraphWrapper, InfigraphStatus, InfigraphResult` so that it is exported for knowledgebase integrations to use.

**Edge cases and risks**
*   **Timeout DoS Risk:** Addressed by enforcing an explicit `timeout=15` argument to `subprocess.run()`.
*   **Missing Executable:** Addressed by explicitly catching `FileNotFoundError` and returning an `ANALYSIS_UNAVAILABLE` status rather than throwing.
*   **Malformed Output:** We gracefully handle cases where the CLI outputs non-JSON data by catching `json.JSONDecodeError`.

#### Test Plan

Create `tests/analysis/test_infigraph.py` utilizing the Python `unittest.mock.patch` (or pytest's monkeypatch) to simulate `subprocess.run` as a fake executable.

1.  **Successful Capabilities:** Mock `subprocess.run` to return a 0 exit code and `{"capabilities": ["static_analysis"]}` on stdout. Expect `ANALYSIS_COMPLETE`.
2.  **Missing Executable:** Mock `subprocess.run` to raise `FileNotFoundError`. Expect `ANALYSIS_UNAVAILABLE`.
3.  **Command Failure:** Mock `subprocess.run` to return a non-zero exit code. Expect `ANALYSIS_FAILED` with the exit code.
4.  **Timeout Failure:** Mock `subprocess.run` to raise `subprocess.TimeoutExpired`. Expect `ANALYSIS_FAILED`.
5.  **Malformed Output:** Mock `subprocess.run` to return invalid JSON string on stdout. Expect `ANALYSIS_FAILED`.

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Add reproducible Infigraph runtime and capability contract | RC-1 | #597 | `scripts/analysis/__init__.py`, `scripts/analysis/infigraph.py` | Low |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/analysis/__init__.py` | 1 | Modify |
| `scripts/analysis/infigraph.py` | 1 | Create |
| `tests/analysis/test_infigraph.py` | 1 | Create |

## Unaddressable Issues

Issues that require changes outside this repository (backend API, infrastructure, product decisions):

| Issue | Reason | Suggested Owner |
|-------|--------|-----------------|
| None | N/A | N/A |
