# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 1 issues on 2026-10-15T10:52:53.576Z

## Executive Summary

Identified 1 root cause corresponding to a missing feature for Infigraph integration. The issue is addressable and requires introducing a new runtime wrapper module to safely manage the Infigraph executable and run capability checks, along with its test suite. Overall health is good as this is a modular, self-contained feature.

## Root Cause Analysis

### RC-1: Missing Infigraph runtime and capability contract

**Related issues:** #597
**Severity:** Medium
**Files involved:** `scripts/analysis/infigraph.py`, `tests/analysis/test_infigraph.py`

#### Diagnosis

The knowledgebase currently lacks an integration wrapper to invoke the Infigraph CLI. There is no code path in `scripts/analysis` (or elsewhere) that handles Infigraph metadata resolution, startup checks, or capability analysis. As a result, the integration cannot determine if the required analysis capabilities are available, ensure reproducible environment setups, or execute analysis commands reliably.

#### Proposed Solution

Introduce a new module `scripts/analysis/infigraph.py` providing the `InfigraphRuntime` wrapper.

**Implementation:**
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
        except Exception as e:
            return {"status": InfigraphStatus.ANALYSIS_FAILED.value, "reason": str(e)}
```

##### Integration points

This introduces a new, independent module `scripts/analysis/infigraph.py`. There are no modifications to existing `scripts/analysis` files since this is a new sub-system. Other components will integrate by instantiating `InfigraphRuntime` with the resolved executable path and release metadata.

##### Edge cases and risks

1. **Malformed JSON outputs from the CLI:** Handled by wrapping `json.loads` in a `try-except` block and mapping it to `ANALYSIS_FAILED`.
2. **Command hangs:** Handled by introducing explicit `timeout=5` and `timeout=30` arguments in `subprocess.run` to prevent unbounded hangs.
3. **Path traversal or injection in `target_path`:** Assumes `target_path` is sanitized before being passed to `analyze()`.

#### Test Plan

Create `tests/analysis/test_infigraph.py` using a fake executable (e.g., via a temporary Python script created using the `tmp_path` fixture) to cover:
1. Successful capability discovery (`analysis_complete`).
2. Representative installation failure (executable not found).
3. Capability failure (executable unsupported / returns non-zero code).
4. Command failure (executable returns non-zero code).
5. Command timeout (`analysis_failed`).
6. Malformed JSON output (`analysis_failed`).

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Add reproducible Infigraph runtime | RC-1 | #597 | `scripts/analysis/infigraph.py`, `tests/analysis/test_infigraph.py` | Low |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/analysis/infigraph.py` | 1 | Create |
| `tests/analysis/test_infigraph.py` | 1 | Create |

## Unaddressable Issues

Issues that require changes outside this repository (backend API, infrastructure, product decisions):

| Issue | Reason | Suggested Owner |
|-------|--------|-----------------|
