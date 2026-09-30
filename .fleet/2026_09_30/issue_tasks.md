# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 1 issues on 2026-09-30T11:56:39.654Z

## Executive Summary

1 root cause found, 1 addressable. The knowledgebase currently lacks a way to run the Infigraph CLI. The goal is to add a wrapper that resolves the CLI path (checking environment variables or common locations) and executes it, handling missing/unsupported/misconfigured states.

## Root Cause Analysis

### RC-1: Missing Infigraph CLI wrapper

**Related issues:** #597
**Severity:** Medium
**Files involved:** `scripts/analysis/infigraph.py`, `tests/analysis/test_infigraph.py`

#### Diagnosis

The project does not currently have integration with the Infigraph CLI. The issue asks for a reproducible wrapper to run `infigraph` and report whether analysis capabilities are available. Since this is an "add" task, the diagnosis is a missing feature.

#### Proposed Solution

**Files to create:** `scripts/analysis/infigraph.py`, `tests/analysis/test_infigraph.py`

Create a wrapper script that resolves the `infigraph` CLI executable and executes it.

```python
# scripts/analysis/infigraph.py
import json
import os
import subprocess
from dataclasses import dataclass
from typing import Literal

# The pinned version metadata
INFIGRAPH_PINNED_VERSION = "1.2.0"

Status = Literal["analysis_complete", "analysis_unavailable", "analysis_failed"]

@dataclass
class InfigraphStatus:
    status: Status
    reason: str | None = None
    capabilities: list[str] | None = None

def _resolve_executable() -> str | None:
    # Check INFIGRAPH_BIN environment variable first
    env_bin = os.environ.get("INFIGRAPH_BIN")
    if env_bin and os.path.isfile(env_bin) and os.access(env_bin, os.X_OK):
        return env_bin

    # Check path
    import shutil
    return shutil.which("infigraph")

def check_capabilities() -> InfigraphStatus:
    executable = _resolve_executable()
    if not executable:
        return InfigraphStatus("analysis_unavailable", "Infigraph CLI executable not found.")

    try:
        # Run infigraph --capabilities to get JSON output
        result = subprocess.run(
            [executable, "--capabilities"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True
        )
    except subprocess.TimeoutExpired:
        return InfigraphStatus("analysis_failed", "Infigraph CLI execution timed out.")
    except subprocess.CalledProcessError as e:
        return InfigraphStatus("analysis_failed", f"Infigraph CLI execution failed: {e.stderr.strip()}")
    except Exception as e:
         return InfigraphStatus("analysis_failed", f"Unexpected error running Infigraph CLI: {e}")

    try:
        data = json.loads(result.stdout)
        capabilities = data.get("capabilities", [])
        return InfigraphStatus("analysis_complete", capabilities=capabilities)
    except json.JSONDecodeError:
        return InfigraphStatus("analysis_failed", "Malformed output from Infigraph CLI (invalid JSON).")
```

#### Test Plan

1. Missing executable: Mock `_resolve_executable` to return None, ensure status is `analysis_unavailable`.
2. Executable timeout: Mock `subprocess.run` to raise `TimeoutExpired`, ensure status is `analysis_failed`.
3. Executable error: Mock `subprocess.run` to raise `CalledProcessError`, ensure status is `analysis_failed`.
4. Executable malformed output: Mock `subprocess.run` to return invalid JSON, ensure status is `analysis_failed`.
5. Successful execution: Mock `subprocess.run` to return valid JSON with capabilities, ensure status is `analysis_complete` and capabilities match.

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Add Infigraph CLI wrapper | RC-1 | #597 | `scripts/analysis/infigraph.py` | Low |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/analysis/infigraph.py` | 1 | Create |
| `tests/analysis/test_infigraph.py` | 1 | Create |

## Unaddressable Issues

None.
