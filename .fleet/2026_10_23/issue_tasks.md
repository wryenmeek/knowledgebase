# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 1 issues on 2026-10-23T11:02:14.072Z

## Executive Summary

Found 1 actionable root cause regarding the need for a pinned, reproducibly resolved Infigraph CLI integration. This feature will introduce the initial runtime wrapper and contract to support future analysis capabilities.

## Root Cause Analysis

### RC-1: Missing Infigraph CLI runtime and capability contract

**Related issues:** #597
**Severity:** High
**Files involved:** `scripts/kb/contracts.py`, `scripts/kb/infigraph_runtime.py` (new), `tests/kb/test_infigraph_runtime.py` (new)

#### Diagnosis

The repository lacks integration with the Infigraph CLI for analysis capabilities. Issue #597 requests a reproducible wrapper that can resolve a pinned executable, verify its capabilities during startup, and provide normalized statuses.

#### Proposed Solution

**1. `scripts/kb/contracts.py`**
Define the contract statuses.

```diff
--- a/scripts/kb/contracts.py
+++ b/scripts/kb/contracts.py
@@ -10,6 +10,12 @@
 from typing import Any


+class InfigraphAnalysisStatus(StrEnum):
+    """Normalized statuses for Infigraph CLI capability checks."""
+    ANALYSIS_COMPLETE = "analysis_complete"
+    ANALYSIS_UNAVAILABLE = "analysis_unavailable"
+    ANALYSIS_FAILED = "analysis_failed"
+
 class PolicyId(StrEnum):
     """Canonical policy identifiers from SPEC.md."""
```

**2. `scripts/kb/infigraph_runtime.py`**
Implement the wrapper.

```python
import json
import subprocess
from dataclasses import dataclass
from typing import Any
from pathlib import Path
from scripts.kb.contracts import InfigraphAnalysisStatus

PINNED_INFIGRAPH_VERSION = "1.0.0"

@dataclass
class InfigraphCapabilityReport:
    status: InfigraphAnalysisStatus
    reason: str | None = None
    capabilities: dict[str, Any] | None = None

def check_infigraph_capabilities(executable_path: str, timeout: int = 15) -> InfigraphCapabilityReport:
    """Invokes the Infigraph CLI to report available capabilities."""
    path = Path(executable_path)
    if not path.is_file():
        return InfigraphCapabilityReport(InfigraphAnalysisStatus.ANALYSIS_UNAVAILABLE, "Executable not found")

    try:
        completed = subprocess.run(
            [executable_path, "--capabilities"],
            capture_output=True,
            text=True,
            timeout=timeout
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Command timed out") from None
    except (OSError, subprocess.SubprocessError) as e:
        return InfigraphCapabilityReport(InfigraphAnalysisStatus.ANALYSIS_UNAVAILABLE, "Execution failed")

    if completed.returncode != 0:
        return InfigraphCapabilityReport(InfigraphAnalysisStatus.ANALYSIS_FAILED, f"Command failed: {completed.stderr.strip()}")

    try:
        data = json.loads(completed.stdout)
        return InfigraphCapabilityReport(InfigraphAnalysisStatus.ANALYSIS_COMPLETE, capabilities=data)
    except json.JSONDecodeError:
        return InfigraphCapabilityReport(InfigraphAnalysisStatus.ANALYSIS_FAILED, "Malformed output")
```

**Integration points:**
No existing functions are modified; this is a new module exposed for future agents. No cross-repository graph storage or MCP integration is included.

**Edge cases and risks:**
- Executable missing or non-executable (handled via `is_file()` and `OSError` catch).
- Hangs (handled via explicit `timeout=15` and suppressing sensitive args via `from None`).
- Malformed JSON output (handled via `JSONDecodeError` catch).

#### Test Plan

Create `tests/kb/test_infigraph_runtime.py` using `pytest` and `tmp_path`. Write temporary scripts (e.g., shell or python) acting as the fake executable to simulate:
1. Valid JSON output.
2. Missing file.
3. Command failure (exit 1).
4. Hanging process (sleep 20) to trigger timeout.
5. Invalid JSON string output.

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Implement reproducible Infigraph runtime and capability contract | RC-1 | #597 | `scripts/kb/contracts.py`, `scripts/kb/infigraph_runtime.py` | Medium |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/kb/contracts.py` | 1 | Modify |
| `scripts/kb/infigraph_runtime.py` | 1 | Create |
| `tests/kb/test_infigraph_runtime.py` | 1 | Create |

## Unaddressable Issues

| Issue | Reason | Suggested Owner |
|-------|--------|-----------------|
| (None) | | |
