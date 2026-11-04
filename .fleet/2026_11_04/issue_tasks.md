# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 1 issues on 2026-11-04T13:48:04.966Z

## Executive Summary

One root cause was identified for Issue #597 involving the lack of reproducible runtime integration and capability discovery for the Infigraph CLI. The issue is fully addressable within the repository by adding a localized CLI wrapper script and its associated tests.

## Root Cause Analysis

### RC-1: Missing Infigraph Runtime Wrapper

**Related issues:** #597
**Severity:** Medium
**Files involved:** `scripts/analysis/infigraph.py` (new), `tests/analysis/test_infigraph.py` (new)

#### Diagnosis

The knowledgebase currently lacks a wrapper to invoke the Infigraph CLI. There is no code path in `scripts/analysis` (or elsewhere) that handles Infigraph metadata resolution, startup checks, or capability analysis. As a result, the integration cannot determine if the required analysis capabilities are available or execute them reproducibly.

#### Proposed Solution

Introduce a new module `scripts/analysis/infigraph.py` that provides:
1. `InfigraphRelease`: A dataclass for reproducible metadata (version, checksum, resolution date).
2. `InfigraphStatus`: An Enum defining `analysis_complete`, `analysis_unavailable`, and `analysis_failed`.
3. `InfigraphRuntime`: A class that verifies the executable exists, runs capability checks to distinguish between unavailable, unsupported, or ready to analyze, and executes analysis commands with timeout handling and actionable failure reasons.

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

#### Integration points
- No existing files are modified; this is a pure addition of `scripts/analysis/infigraph.py` and `tests/analysis/test_infigraph.py`.

#### Edge cases and risks
- Timeout on CLI execution blocking the system. Addressed by applying explicit `timeout=...` to `subprocess.run` and returning `ANALYSIS_FAILED`.
- Process crashes or malformed output from the executable. Addressed by capturing exceptions and returning `ANALYSIS_FAILED`.
- Path traversal or unsafe executables. Addressed by allowing the executable path to be pinned.
- Sensitive data leaks in exception traces. Addressed by capturing and mapping exceptions.

#### Test Plan

Create `tests/analysis/test_infigraph.py` using a fake executable (e.g., via a temporary python script using pytest tmp_path fixture) to cover:
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
| 1 | Add reproducible Infigraph runtime wrapper | RC-1 | #597 | `scripts/analysis/infigraph.py`, `tests/analysis/test_infigraph.py` | Low |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/analysis/infigraph.py` | task-add-infigraph-wrapper | Create |
| `tests/analysis/test_infigraph.py` | task-add-infigraph-wrapper | Create |

## Unaddressable Issues

None
