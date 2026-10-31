# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 1 issues on 2026-10-31T11:42:25.922Z

## Executive Summary

Found 1 addressable root cause. The issue asks for adding an `Infigraph` runtime wrapper that can check for analysis capabilities, returning normalized statuses, recording the resolved version reproducibly, and covering tests. This aligns with adding a new script to `scripts/analysis/` and its tests.

## Root Cause Analysis

### RC-1: Missing Infigraph Runtime Wrapper

**Related issues:** #597
**Severity:** Medium
**Files involved:** `scripts/analysis/infigraph.py` (new), `tests/analysis/test_infigraph.py` (new)

#### Diagnosis

The knowledgebase currently has no integration to invoke the Infigraph CLI. As requested by issue #597, we need a wrapper capable of invoking a pinned Infigraph executable and determining if its required capabilities are present.

#### Proposed Solution

**Files modified:** `scripts/analysis/infigraph.py` (new), `tests/analysis/test_infigraph.py` (new)

**Implementation:**

```python
# NEW: scripts/analysis/infigraph.py

import json
import subprocess
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class InfigraphMetadata:
    version: str
    resolved_path: str
    checksum: str

@dataclass(frozen=True)
class CapabilityReport:
    status: Literal["analysis_complete", "analysis_unavailable", "analysis_failed"]
    reason: str
    metadata: InfigraphMetadata | None = None

class InfigraphRuntime:
    def __init__(self, executable_path: str = "infigraph"):
        self.executable_path = executable_path

    def check_capabilities(self, timeout: float = 5.0) -> CapabilityReport:
        try:
            result = subprocess.run(
                [self.executable_path, "capabilities", "--format=json"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True
            )
            data = json.loads(result.stdout)

            metadata = InfigraphMetadata(
                version=data.get("version", "unknown"),
                resolved_path=self.executable_path,
                checksum=data.get("checksum", "unknown")
            )

            if data.get("ready_for_analysis") is True:
                return CapabilityReport(
                    status="analysis_complete",
                    reason="Capabilities are fully supported and ready.",
                    metadata=metadata
                )
            else:
                return CapabilityReport(
                    status="analysis_unavailable",
                    reason="Executable found but required capabilities are missing.",
                    metadata=metadata
                )

        except FileNotFoundError:
            return CapabilityReport(
                status="analysis_unavailable",
                reason=f"Executable '{self.executable_path}' not found."
            )
        except subprocess.TimeoutExpired:
            return CapabilityReport(
                status="analysis_failed",
                reason="Command timed out while checking capabilities."
            )
        except subprocess.CalledProcessError as e:
            return CapabilityReport(
                status="analysis_failed",
                reason=f"Command failed with exit code {e.returncode}: {e.stderr.strip()}"
            )
        except json.JSONDecodeError:
            return CapabilityReport(
                status="analysis_failed",
                reason="Malformed JSON output from executable."
            )
        except Exception as e:
            return CapabilityReport(
                status="analysis_failed",
                reason=f"Unexpected error: {str(e)}"
            )
```

**Integration points:**
This creates a new isolated module in `scripts/analysis/infigraph.py` that can be imported by other analysis workflows.

**Edge cases and risks:**
- **Executable not found**: Handled by catching `FileNotFoundError`.
- **Command hangs**: Handled by passing a `timeout` to `subprocess.run`.
- **Malformed output**: Handled by catching `json.JSONDecodeError`.
- **Permissions/Execution failure**: Handled by catching `subprocess.CalledProcessError`.

#### Test Plan

1. **Successful discovery**: Mock subprocess to return valid JSON indicating readiness. Verify `analysis_complete` status and metadata parsing.
2. **Missing capabilities**: Mock subprocess to return valid JSON with `ready_for_analysis: false`. Verify `analysis_unavailable`.
3. **Executable unavailable**: Mock subprocess to raise `FileNotFoundError`. Verify `analysis_unavailable`.
4. **Command timeout**: Mock subprocess to raise `subprocess.TimeoutExpired`. Verify `analysis_failed`.
5. **Command failure**: Mock subprocess to raise `subprocess.CalledProcessError`. Verify `analysis_failed`.
6. **Malformed output**: Mock subprocess to return invalid JSON. Verify `analysis_failed`.

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Add reproducible Infigraph runtime and capability contract | RC-1 | #597 | `scripts/analysis/infigraph.py`, `tests/analysis/test_infigraph.py` | Low |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/analysis/infigraph.py` | task-infigraph-runtime | Create |
| `tests/analysis/test_infigraph.py` | task-infigraph-runtime | Create |

## Unaddressable Issues

None
