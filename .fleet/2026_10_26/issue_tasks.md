# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 1 issues on 2026-10-26T12:16:57.954Z

## Executive Summary

Found 1 actionable root cause addressing a missing runtime capability contract for the Infigraph CLI. The issue requires a new reproducible integration wrapper, which does not exist in the codebase yet.

## Root Cause Analysis

### RC-1: Missing Infigraph Runtime Wrapper

**Related issues:** #597
**Severity:** Medium
**Files involved:** `scripts/kb/infigraph_runtime.py`, `scripts/kb/infigraph_metadata.json`, `tests/kb/test_infigraph_runtime.py`

#### Diagnosis

The knowledgebase currently lacks a reproducible and verifiable integration with the Infigraph CLI. There is no code path or wrapper that can resolve the pinned CLI, verify its execution, and define standard capability/status contracts. This prevents features requiring graph analysis from running securely and reliably in CI or local environments.

#### Proposed Solution

Implement a new `infigraph_runtime.py` wrapper that performs reproducible execution using pinned metadata from `infigraph_metadata.json`, and handles capability discovery, exposing normalized statuses as requested by the acceptance criteria.

```python
# scripts/kb/infigraph_runtime.py
import subprocess
import shutil
import json
from pathlib import Path
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any

class InfigraphStatus(Enum):
    ANALYSIS_COMPLETE = "analysis_complete"
    ANALYSIS_UNAVAILABLE = "analysis_unavailable"
    ANALYSIS_FAILED = "analysis_failed"

@dataclass
class InfigraphResult:
    status: InfigraphStatus
    reason: Optional[str] = None
    output: Optional[str] = None

class InfigraphRuntime:
    def __init__(self, executable_path: str = "infigraph", metadata_path: str = "scripts/kb/infigraph_metadata.json"):
        self.executable_path = executable_path
        self.metadata_path = Path(metadata_path)

    def load_metadata(self) -> Dict[str, Any]:
        if not self.metadata_path.exists():
            return {}
        try:
            with open(self.metadata_path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def check_availability(self) -> InfigraphResult:
        metadata = self.load_metadata()
        if not metadata.get("version") or not metadata.get("sha256"):
            return InfigraphResult(
                status=InfigraphStatus.ANALYSIS_UNAVAILABLE,
                reason="Resolution metadata is missing or invalid. Infigraph release must be pinned."
            )

        if not shutil.which(self.executable_path):
            return InfigraphResult(
                status=InfigraphStatus.ANALYSIS_UNAVAILABLE,
                reason="Executable not found in PATH"
            )

        try:
            # Capability discovery contract check
            result = subprocess.run(
                [self.executable_path, "--capabilities"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                return InfigraphResult(
                    status=InfigraphStatus.ANALYSIS_UNAVAILABLE,
                    reason=f"Capability check failed: {result.stderr.strip() or 'Unknown error'}"
                )

            return InfigraphResult(
                status=InfigraphStatus.ANALYSIS_COMPLETE,
                output=result.stdout.strip()
            )
        except subprocess.TimeoutExpired:
            return InfigraphResult(
                status=InfigraphStatus.ANALYSIS_FAILED,
                reason="Capability check timed out"
            )
        except Exception as e:
            return InfigraphResult(
                status=InfigraphStatus.ANALYSIS_FAILED,
                reason=f"Execution error: {str(e)}"
            )
```

##### Integration points
The new `InfigraphRuntime` will be self-contained within `scripts/kb/infigraph_runtime.py` and its resolution metadata in `scripts/kb/infigraph_metadata.json`. Future graph analysis components will instantiate this class to verify capabilities before initiating graph storage or analysis tasks. Before/after diffs showing the integration should be produced if you end up wiring this into an existing module, but currently, it will just be provided as a standalone utility.

##### Edge cases and risks
1. **Missing or Malformed Metadata:** The metadata file might be missing, unreadable, or missing required fields (`version`, `sha256`). The runtime must gracefully return `ANALYSIS_UNAVAILABLE`.
2. **Executable Not in PATH:** `shutil.which` might fail to find the executable, returning `ANALYSIS_UNAVAILABLE`.
3. **Execution Timeout or Failure:** The CLI might hang or return a non-zero code. The use of `timeout=5` prevents hangs, returning `ANALYSIS_FAILED`.

#### Test Plan

Create `tests/kb/test_infigraph_runtime.py` using `unittest.mock.patch` to simulate `shutil.which`, `subprocess.run`, and file reads. Cover scenarios:
1. Executable not found (returns ANALYSIS_UNAVAILABLE)
2. Metadata missing or malformed (returns ANALYSIS_UNAVAILABLE)
3. Successful capability discovery (returns ANALYSIS_COMPLETE)
4. Capability check timeout (returns ANALYSIS_FAILED)
5. Capability check non-zero return code (returns ANALYSIS_UNAVAILABLE)
6. Malformed CLI output during capability check (returns ANALYSIS_FAILED)
7. Representative installation or command failures handled gracefully.

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Add reproducible Infigraph runtime and capability contract | RC-1 | #597 | `scripts/kb/infigraph_runtime.py`, `scripts/kb/infigraph_metadata.json` | Low |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/kb/infigraph_runtime.py` | 1 | Create |
| `scripts/kb/infigraph_metadata.json` | 1 | Create |
| `tests/kb/test_infigraph_runtime.py` | 1 | Create |

## Unaddressable Issues

None
