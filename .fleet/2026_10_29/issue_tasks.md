# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 1 issues on 2026-10-29T12:18:52.378Z

## Executive Summary

Found one root cause for the requested enhancement: the need for a wrapper module to interact with a reproducible Infigraph executable and report capability statuses. This is a greenfield integration, easily isolated into a new module in `scripts/analysis/infigraph.py` with corresponding tests.

## Root Cause Analysis

### RC-1: Missing Infigraph Runtime Integration

**Related issues:** #597
**Severity:** High
**Files involved:** `scripts/analysis/infigraph.py` (new), `tests/analysis/test_infigraph.py` (new)

#### Diagnosis

The knowledgebase integration currently lacks a way to invoke the Infigraph CLI. Issue #597 requests a capability contract and reproducible runtime for Infigraph to verify that required analysis capabilities are available. Since this is a new feature, no existing code path causes a failure. Rather, the absence of an Infigraph wrapper prevents the knowledgebase from successfully determining analysis readiness.

#### Proposed Solution

Create a new module, `scripts/analysis/infigraph.py`, to wrap the Infigraph CLI.

**Implementation Details:**
- A pinning mechanism for the Infigraph release (e.g., a constant `INFIGRAPH_VERSION` or a JSON file) to ensure reproducibility.
- A function `check_infigraph_status()` that:
  - Invokes the Infigraph executable (e.g., `infigraph --version` or `infigraph capabilities`).
  - Distinguishes between unavailable (executable not found), unsupported (wrong version), misconfigured, or ready.
- A normalized status return object (e.g., `InfigraphStatus` dataclass or enum) with states like `analysis_complete`, `analysis_unavailable`, `analysis_failed`, and actionable failure reasons.

**Files modified:** `scripts/analysis/infigraph.py` (new), `tests/analysis/test_infigraph.py` (new)

```python
# NEW: scripts/analysis/infigraph.py
import subprocess
import shutil
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any

class AnalysisState(Enum):
    COMPLETE = "analysis_complete"
    UNAVAILABLE = "analysis_unavailable"
    FAILED = "analysis_failed"

@dataclass
class InfigraphStatus:
    state: AnalysisState
    reason: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None

INFIGRAPH_VERSION = "1.2.0" # Example pinned version

def check_infigraph_status(executable_path: str = "infigraph") -> InfigraphStatus:
    if not shutil.which(executable_path):
        return InfigraphStatus(state=AnalysisState.UNAVAILABLE, reason="Executable not found.")

    try:
        # Run capability discovery with timeout
        result = subprocess.run(
            [executable_path, "capabilities"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
             return InfigraphStatus(state=AnalysisState.FAILED, reason=f"Command failed: {result.stderr}")

        # Parse capabilities (assuming JSON output)
        import json
        try:
             capabilities = json.loads(result.stdout)
             return InfigraphStatus(state=AnalysisState.COMPLETE, capabilities=capabilities)
        except json.JSONDecodeError:
             return InfigraphStatus(state=AnalysisState.FAILED, reason="Malformed output from executable.")

    except subprocess.TimeoutExpired:
        return InfigraphStatus(state=AnalysisState.FAILED, reason="Command timed out.")
    except Exception as e:
        return InfigraphStatus(state=AnalysisState.FAILED, reason=str(e))
```

#### Integration points
Since this is a new module, there are no immediate integrations into existing logic described in the issue. It acts as an isolated wrapper ready to be imported.

#### Edge cases and risks
- The Infigraph executable might hang indefinitely if not called with a timeout.
- The output from Infigraph might change format or be malformed, causing parsing errors.
- The path to the executable might not be in the system PATH.

#### Test Plan

1. **Successful Capability Discovery:** Fake executable returns valid JSON capabilities -> Status is `analysis_complete`.
2. **Missing Executable:** Executable not found in PATH -> Status is `analysis_unavailable`.
3. **Command Failure:** Executable returns non-zero exit code -> Status is `analysis_failed`.
4. **Timeout Failure:** Executable hangs and hits timeout -> Status is `analysis_failed`.
5. **Malformed Output:** Executable returns invalid JSON -> Status is `analysis_failed`.

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Add reproducible Infigraph runtime and capability contract | RC-1 | #597 | `scripts/analysis/infigraph.py` (new) | Low |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/analysis/infigraph.py` | 1 | Create |
| `tests/analysis/test_infigraph.py` | 1 | Create |

## Unaddressable Issues

Issues that require changes outside this repository (backend API, infrastructure, product decisions):

| Issue | Reason | Suggested Owner |
|-------|--------|-----------------|
| None | N/A | N/A |
