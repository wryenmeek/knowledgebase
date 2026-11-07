# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 1 issues on 2026-11-07T12:29:28.472Z

## Executive Summary

1 root cause found, 1 is addressable. The knowledgebase currently lacks a reproducible integration for the Infigraph CLI. The proposed solution introduces a dedicated wrapper to resolve, execute, and evaluate the availability of Infigraph capabilities without introducing cross-repo dependencies.

## Root Cause Analysis

### RC-1: Missing reproducible Infigraph runtime and capability contract

**Related issues:** #597
**Severity:** Medium
**Files involved:** `scripts/kb/infigraph.py`, `tests/kb/test_infigraph.py`

#### Diagnosis

The project requires integration with an Infigraph CLI to perform analysis, but there is no mechanism to reproducibly specify the required release, verify the installation, or invoke the tool to discover available capabilities. A structured wrapper is required to bridge the local CLI invocation with actionable normalized statuses.

#### Proposed Solution

Create a self-contained Python wrapper `scripts/kb/infigraph.py` that records resolution metadata, discovers the executable, and runs capability checks with strict timeout and JSON parsing.

**Implementation:**

```python
# NEW: scripts/kb/infigraph.py
import json
import subprocess
import shutil
from dataclasses import dataclass
from enum import Enum

class InfigraphStatus(Enum):
    ANALYSIS_COMPLETE = "analysis_complete"
    ANALYSIS_UNAVAILABLE = "analysis_unavailable"
    ANALYSIS_FAILED = "analysis_failed"

@dataclass
class InfigraphResolution:
    version: str
    sha256: str
    platform: str

# Reproducibly recorded resolution metadata
CURRENT_RESOLUTION = InfigraphResolution(
    version="1.0.0",
    sha256="placeholder-hash",
    platform="linux-amd64"
)

@dataclass
class InfigraphResult:
    status: InfigraphStatus
    reason: str | None = None
    capabilities: list[str] | None = None

def get_infigraph_executable(custom_path: str | None = None) -> str | None:
    return custom_path or shutil.which("infigraph")

def check_capabilities(executable_path: str | None) -> InfigraphResult:
    if not executable_path:
        return InfigraphResult(status=InfigraphStatus.ANALYSIS_UNAVAILABLE, reason="Executable not found")

    try:
        result = subprocess.run(
            [executable_path, "capabilities"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )

        if result.returncode != 0:
            return InfigraphResult(
                status=InfigraphStatus.ANALYSIS_FAILED,
                reason=f"Command failed with code {result.returncode}: {result.stderr.strip() if result.stderr else ''}"
            )

        try:
            data = json.loads(result.stdout)
            if not isinstance(data, dict) or "capabilities" not in data:
                return InfigraphResult(status=InfigraphStatus.ANALYSIS_FAILED, reason="Malformed capability response")

            return InfigraphResult(
                status=InfigraphStatus.ANALYSIS_COMPLETE,
                capabilities=data["capabilities"]
            )
        except json.JSONDecodeError:
            # 🛡️ Sentinel: Do not leak sensitive command output by propagating exception context.
            return InfigraphResult(status=InfigraphStatus.ANALYSIS_FAILED, reason="Malformed JSON output")

    except FileNotFoundError:
        return InfigraphResult(status=InfigraphStatus.ANALYSIS_UNAVAILABLE, reason="Executable not found")
    except subprocess.TimeoutExpired:
        # 🛡️ Sentinel: Do not leak sensitive arguments by propagating exception context.
        return InfigraphResult(status=InfigraphStatus.ANALYSIS_FAILED, reason="Command timed out")
```

#### Test Plan

1. Verify successful capability discovery by mocking a fake executable that returns `{"capabilities": ["graph"]}`.
2. Verify timeout failures result in `ANALYSIS_FAILED` using a fake executable that sleeps.
3. Verify malformed output returns `ANALYSIS_FAILED` without throwing exceptions.
4. Verify non-existent executable returns `ANALYSIS_UNAVAILABLE`.
5. Verify command failures (non-zero exit code) return `ANALYSIS_FAILED`.

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Implement Infigraph CLI wrapper and capability checks | missing-infigraph-runtime | #597 | `scripts/kb/infigraph.py` | Low |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/kb/infigraph.py` | implement-infigraph-wrapper | Create |
| `tests/kb/test_infigraph.py` | implement-infigraph-wrapper | Create |

## Unaddressable Issues

Issues that require changes outside this repository (backend API, infrastructure, product decisions):

| Issue | Reason | Suggested Owner |
|-------|--------|-----------------|
