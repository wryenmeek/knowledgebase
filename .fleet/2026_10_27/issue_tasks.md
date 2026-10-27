# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 1 issues on 2026-10-27T11:37:26.445Z

## Executive Summary

Found 1 root cause corresponding to the single enhancement request for an Infigraph capability wrapper. The task is fully addressable and requires a new contract file, its corresponding test suite, and a metadata recording utility to satisfy reproducible resolution requirements.

## Root Cause Analysis

### RC-1: Missing Infigraph Runtime Wrapper and Contract

**Related issues:** #597
**Severity:** Medium
**Files involved:** `scripts/kb/infigraph_runtime.py`, `tests/kb/test_infigraph_runtime.py`

#### Diagnosis

The repository currently lacks a wrapper to invoke the Infigraph CLI. The `scripts/kb/` directory contains various deterministic entry points, but none provide the capability contract and reproducible invocation interface required by issue #597 for the Infigraph integration. A new module is required to verify the executable's capabilities deterministically, record its version metadata reproducibly for CI verification, and prevent cross-repository graph storage or MCP integration.

#### Proposed Solution

Create a new `scripts/kb/infigraph_runtime.py` file providing the capability contract, execution wrappers, and a reproducible metadata pinning mechanism.

```python
"""Reproducible Infigraph CLI runtime and capability contract."""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path
from typing import Literal, Optional

# Normalized status strings
STATUS_ANALYSIS_COMPLETE = "analysis_complete"
STATUS_ANALYSIS_UNAVAILABLE = "analysis_unavailable"
STATUS_ANALYSIS_FAILED = "analysis_failed"

@dataclasses.dataclass(frozen=True, slots=True)
class CapabilityReport:
    """Capability report for the pinned Infigraph executable."""
    status: Literal["analysis_complete", "analysis_unavailable", "analysis_failed"]
    version: str | None = None
    capabilities: tuple[str, ...] = ()
    reason: str | None = None

def check_capabilities(executable: str = "infigraph", timeout: int = 15) -> CapabilityReport:
    """Check the availability and capabilities of the Infigraph executable."""
    try:
        result = subprocess.run(
            [executable, "capabilities", "--format=json"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
    except FileNotFoundError:
        return CapabilityReport(status=STATUS_ANALYSIS_UNAVAILABLE, reason="executable not found")
    except subprocess.TimeoutExpired:
        return CapabilityReport(status=STATUS_ANALYSIS_FAILED, reason="command timed out")
    except Exception as e:
        return CapabilityReport(status=STATUS_ANALYSIS_FAILED, reason=f"execution error: {e}")

    if result.returncode != 0:
        return CapabilityReport(
            status=STATUS_ANALYSIS_FAILED,
            reason=f"command failed with code {result.returncode}"
        )

    try:
        data = json.loads(result.stdout)
        version = data.get("version")
        capabilities = tuple(data.get("capabilities", []))
        return CapabilityReport(
            status=STATUS_ANALYSIS_COMPLETE,
            version=version,
            capabilities=capabilities
        )
    except json.JSONDecodeError:
        return CapabilityReport(status=STATUS_ANALYSIS_FAILED, reason="malformed output")

def record_resolution_metadata(executable: str = "infigraph", output_file: str = "infigraph_resolution.json", timeout: int = 15) -> bool:
    """Records the selected Infigraph release and resolution metadata reproducibly for CI."""
    report = check_capabilities(executable=executable, timeout=timeout)

    if report.status != STATUS_ANALYSIS_COMPLETE:
        return False

    metadata = {
        "executable": executable,
        "version": report.version,
        "capabilities": report.capabilities,
        "resolved_at_status": "pinned"
    }

    try:
        with open(output_file, "w") as f:
            json.dump(metadata, f, indent=2)
        return True
    except IOError:
        return False


def invoke_analysis(
    target_path: str,
    executable: str = "infigraph",
    timeout: int = 30
) -> dict[str, str]:
    """Invoke Infigraph analysis on a target path."""
    # Ensure no cross-repository or MCP integration
    if ".." in target_path or target_path.startswith("/") or "mcp" in target_path.lower():
        return {"status": STATUS_ANALYSIS_FAILED, "reason": "invalid target path: no cross-repo or MCP integration allowed"}

    try:
        result = subprocess.run(
            [executable, "analyze", target_path, "--format=json"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
    except FileNotFoundError:
        return {"status": STATUS_ANALYSIS_UNAVAILABLE, "reason": "executable not found"}
    except subprocess.TimeoutExpired:
        return {"status": STATUS_ANALYSIS_FAILED, "reason": "command timed out"}

    if result.returncode != 0:
        return {"status": STATUS_ANALYSIS_FAILED, "reason": f"command failed: {result.stderr.strip()}"}

    return {"status": STATUS_ANALYSIS_COMPLETE, "output": result.stdout.strip()}
```

#### Test Plan

Create `tests/kb/test_infigraph_runtime.py` with the following scenarios using a fake executable (or mocking `subprocess.run`):
1. Executable unavailable (FileNotFoundError).
2. Command timeout (subprocess.TimeoutExpired).
3. Capability check successful (valid JSON returned).
4. Malformed output during capability check (JSONDecodeError).
5. Target path validation in analysis invocation blocks `..`, `/` and `mcp`.
6. Successful metadata recording using `record_resolution_metadata` writes valid JSON.

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Add reproducible Infigraph runtime and capability contract | RC-1 | #597 | `scripts/kb/infigraph_runtime.py`, `tests/kb/test_infigraph_runtime.py` | Low |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/kb/infigraph_runtime.py` | task-add-infigraph-runtime | Create |
| `tests/kb/test_infigraph_runtime.py` | task-add-infigraph-runtime | Create |

## Unaddressable Issues

| Issue | Reason | Suggested Owner |
|-------|--------|-----------------|
