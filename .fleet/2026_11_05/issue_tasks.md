# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 1 issues on 2026-11-05T13:59:51.061Z

## Executive Summary

One root cause was identified, requiring a wrapper module for the external Infigraph CLI to ensure reproducible execution and reliable capability reporting. The solution introduces a new Python module with well-defined contracts and isolated testing.

## Root Cause Analysis

### RC-1: Missing Infigraph Wrapper

**Related issues:** #597
**Severity:** High
**Files involved:** `scripts/kb/infigraph.py`, `scripts/kb/__init__.py`, `scripts/kb/contracts.py`

#### Diagnosis

The knowledgebase currently lacks an integration point for invoking the Infigraph CLI. As per the issue brief, there is no code path or standardized wrapper that resolves a pinned executable, discovers its capabilities, or reports deterministic statuses (`analysis_complete`, `analysis_unavailable`, `analysis_failed`).

#### Proposed Solution

Introduce `scripts/kb/infigraph.py` which provides an `InfigraphRuntime` wrapper.

**Implementation:**
```python
# NEW: scripts/kb/infigraph.py
import json
import subprocess
from dataclasses import dataclass
from typing import Any
from .contracts import InfigraphReasonCode

@dataclass(frozen=True)
class CapabilityReport:
    status: InfigraphReasonCode
    reason: str
    capabilities: dict[str, Any]

class InfigraphRuntime:
    def __init__(self, executable_path: str, version_pin: str):
        self.executable_path = executable_path
        self.version_pin = version_pin

    def check_capabilities(self) -> CapabilityReport:
        try:
            result = subprocess.run(
                [self.executable_path, "--capabilities"],
                capture_output=True,
                text=True,
                timeout=5.0
            )
        except FileNotFoundError:
            return CapabilityReport(InfigraphReasonCode.ANALYSIS_UNAVAILABLE, "Executable not found", {})
        except subprocess.TimeoutExpired:
            return CapabilityReport(InfigraphReasonCode.ANALYSIS_FAILED, "Timeout executing Infigraph", {})

        if result.returncode != 0:
            return CapabilityReport(
                InfigraphReasonCode.ANALYSIS_FAILED,
                f"Command failed (exit {result.returncode}): {result.stderr.strip()}",
                {}
            )

        try:
            caps = json.loads(result.stdout)
            return CapabilityReport(InfigraphReasonCode.ANALYSIS_COMPLETE, "ok", caps)
        except json.JSONDecodeError as exc:
            return CapabilityReport(InfigraphReasonCode.ANALYSIS_FAILED, "Malformed capabilities output", {})
```

**Integration points:**
Modify `scripts/kb/__init__.py`:
```python
# scripts/kb/__init__.py
- from . import contracts, qmd_preflight
- __all__ = ["contracts", "qmd_preflight"]
+ from . import contracts, qmd_preflight, infigraph
+ __all__ = ["contracts", "qmd_preflight", "infigraph"]
```

Modify `scripts/kb/contracts.py` to add ReasonCodes:
```python
# scripts/kb/contracts.py
+ class InfigraphReasonCode(StrEnum):
+     ANALYSIS_COMPLETE = "analysis_complete"
+     ANALYSIS_UNAVAILABLE = "analysis_unavailable"
+     ANALYSIS_FAILED = "analysis_failed"
```

**Edge cases and risks:**
- External command unavailability (path resolution failure)
- Missing capabilities in older versions
- Execution timeouts or malformed JSON output from capabilities check
- Incomplete backward compatibility in status enums when returning to older clients

#### Test Plan

Introduce `tests/kb/test_infigraph.py` that uses a mock `subprocess.run` (a fake executable approach) to cover:
1. Capability discovery success: Mock returns 0 with valid JSON.
2. CLI installation/resolution failures: Mock raises `FileNotFoundError`.
3. Timeout failures: Mock raises `subprocess.TimeoutExpired`.
4. Command failures: Mock returns non-zero code.
5. Malformed output failures: Mock returns 0 with invalid JSON.

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Add reproducible Infigraph runtime and capability contract | RC-1 | #597 | `scripts/kb/infigraph.py`, `scripts/kb/__init__.py`, `scripts/kb/contracts.py` | Low |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/kb/__init__.py` | 1 | Modify |
| `scripts/kb/contracts.py` | 1 | Modify |
| `scripts/kb/infigraph.py` | 1 | Create |
| `tests/kb/test_infigraph.py` | 1 | Create |

## Unaddressable Issues

None
