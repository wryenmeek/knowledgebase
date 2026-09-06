# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 1 issues on 2026-09-06T10:17:07.168Z

## Executive Summary

Identified 1 root cause corresponding to a missing feature for Infigraph integration. The issue is addressable and requires introducing a new runtime wrapper module to manage the Infigraph executable safely, along with its test suite.

## Root Cause Analysis

### RC-1: Missing Infigraph runtime and capability contract

**Related issues:** #597
**Severity:** Medium
**Files involved:** `scripts/analysis/infigraph.py`

#### Diagnosis

The knowledgebase currently lacks a wrapper to invoke the Infigraph CLI. There is no code path in `scripts/analysis` (or elsewhere) that handles Infigraph metadata resolution, startup checks, or capability analysis. As a result, the integration cannot determine if the required analysis capabilities are available or execute them reproducibly.

#### Proposed Solution

Introduce a new module `scripts/analysis/infigraph.py` that provides:
1. `InfigraphRelease`: A dataclass for reproducible metadata (version, checksum, resolution date).
2. `InfigraphStatus`: An Enum defining `analysis_complete`, `analysis_unavailable`, and `analysis_failed`.
3. `InfigraphRuntime`: A class that:
   - Verifies the executable exists.
   - Runs capability checks to distinguish between an executable that is unavailable, unsupported, or ready to analyze.
   - Executes analysis commands with timeout handling.
   - Returns normalized statuses including actionable failure reasons.

```python
# scripts/analysis/infigraph.py
import subprocess
import json
import enum
from dataclasses import dataclass
from typing import Optional, Dict, Any

class InfigraphStatus(enum.Enum):
    ANALYSIS_COMPLETE = "analysis_complete"
    ANALYSIS_UNAVAILABLE = "analysis_unavailable"
    ANALYSIS_FAILED = "analysis_failed"

@dataclass
class InfigraphRelease:
    version: str
    checksum: str
    resolved_at: str

class InfigraphRuntime:
    def __init__(self, executable_path: str, release: InfigraphRelease):
        self.executable_path = executable_path
        self.release = release

    def check_capabilities(self) -> InfigraphStatus:
        try:
            result = subprocess.run(
                [self.executable_path, "--capabilities"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                return InfigraphStatus.ANALYSIS_UNAVAILABLE
            return InfigraphStatus.ANALYSIS_COMPLETE
        except FileNotFoundError:
            return InfigraphStatus.ANALYSIS_UNAVAILABLE
        except subprocess.TimeoutExpired:
            return InfigraphStatus.ANALYSIS_FAILED
        except Exception:
            return InfigraphStatus.ANALYSIS_FAILED

    def analyze(self, target_path: str) -> Dict[str, Any]:
        try:
            result = subprocess.run(
                [self.executable_path, "analyze", target_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                return {"status": InfigraphStatus.ANALYSIS_FAILED.value, "reason": "Command failed"}
            return {"status": InfigraphStatus.ANALYSIS_COMPLETE.value, "data": json.loads(result.stdout)}
        except FileNotFoundError:
            return {"status": InfigraphStatus.ANALYSIS_UNAVAILABLE.value, "reason": "Executable not found"}
        except subprocess.TimeoutExpired:
            return {"status": InfigraphStatus.ANALYSIS_FAILED.value, "reason": "Timeout"}
        except json.JSONDecodeError:
            return {"status": InfigraphStatus.ANALYSIS_FAILED.value, "reason": "Malformed output"}
```

#### Test Plan

Create `tests/analysis/test_infigraph.py` using a fake executable (e.g., via a temporary script) to cover:
1. Successful capability discovery (`analysis_complete`).
2. Representative installation failure (executable not found).
3. Capability failure (executable unsupported).
4. Command failure (executable returns non-zero code).
5. Command timeout (`analysis_failed`).
6. Malformed JSON output (`analysis_failed`).

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Add reproducible Infigraph runtime | RC-1 | #597 | `scripts/analysis/infigraph.py` | Low |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/analysis/infigraph.py` | 1 | Create |
| `tests/analysis/test_infigraph.py` | 1 | Create |

## Unaddressable Issues

None
