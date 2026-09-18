# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 1 issues on 2026-09-18T10:36:10.574Z

## Executive Summary

Identified 1 missing feature requiring a new wrapper for the Infigraph CLI. The issue is fully addressable within the repository and requires adding a new python wrapper script and its corresponding tests.

## Root Cause Analysis

### RC-1: Missing Infigraph CLI wrapper and capability contract

**Related issues:** #597
**Severity:** Medium
**Files involved:** `scripts/kb/infigraph.py`, `tests/kb/test_infigraph.py`

#### Diagnosis

The project lacks an integration layer to reproducibly invoke the Infigraph CLI. As a result, there is no way to perform analysis using Infigraph while guaranteeing that the environment has the correct, pinned version and the required capabilities. There are no existing code paths handling Infigraph execution. This is a missing feature and architectural gap.

#### Proposed Solution

Create a new wrapper module `scripts/kb/infigraph.py` to handle the reproducible Infigraph runtime.

```python
# NEW: scripts/kb/infigraph.py
import enum
import json
import subprocess
from dataclasses import dataclass
from typing import Optional, Dict, Any

INFIGRAPH_VERSION_PIN = "1.0.0"
INFIGRAPH_EXPECTED_CAPABILITIES = {"graph_analysis", "syntax_tree"}

class InfigraphStatus(enum.Enum):
    ANALYSIS_COMPLETE = "analysis_complete"
    ANALYSIS_UNAVAILABLE = "analysis_unavailable"
    ANALYSIS_FAILED = "analysis_failed"

@dataclass
class InfigraphResult:
    status: InfigraphStatus
    reason: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

class InfigraphWrapper:
    def __init__(self, executable_path: str = "infigraph", timeout: int = 30):
        self.executable_path = executable_path
        self.timeout = timeout

    def check_capabilities(self) -> InfigraphResult:
        try:
            result = subprocess.run(
                [self.executable_path, "--capabilities"],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            if result.returncode != 0:
                return InfigraphResult(
                    status=InfigraphStatus.ANALYSIS_UNAVAILABLE,
                    reason=f"Executable misconfigured or unsupported. Return code {result.returncode}"
                )

            try:
                capabilities = json.loads(result.stdout)
            except json.JSONDecodeError:
                return InfigraphResult(
                    status=InfigraphStatus.ANALYSIS_UNAVAILABLE,
                    reason="Malformed output from capabilities check"
                )

            provided = set(capabilities.get("capabilities", []))
            if not INFIGRAPH_EXPECTED_CAPABILITIES.issubset(provided):
                missing = INFIGRAPH_EXPECTED_CAPABILITIES - provided
                return InfigraphResult(
                    status=InfigraphStatus.ANALYSIS_UNAVAILABLE,
                    reason=f"Missing required capabilities: {missing}"
                )

            version = capabilities.get("version")
            if version != INFIGRAPH_VERSION_PIN:
                return InfigraphResult(
                    status=InfigraphStatus.ANALYSIS_UNAVAILABLE,
                    reason=f"Version mismatch. Expected {INFIGRAPH_VERSION_PIN}, got {version}"
                )

            return InfigraphResult(status=InfigraphStatus.ANALYSIS_COMPLETE)

        except FileNotFoundError:
            return InfigraphResult(
                status=InfigraphStatus.ANALYSIS_UNAVAILABLE,
                reason="Executable unavailable"
            )
        except subprocess.TimeoutExpired:
            return InfigraphResult(
                status=InfigraphStatus.ANALYSIS_FAILED,
                reason="Capabilities check timed out"
            )

    def run_analysis(self, target_path: str) -> InfigraphResult:
        capabilities_check = self.check_capabilities()
        if capabilities_check.status != InfigraphStatus.ANALYSIS_COMPLETE:
            return capabilities_check

        try:
            result = subprocess.run(
                [self.executable_path, "analyze", target_path],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            if result.returncode != 0:
                return InfigraphResult(
                    status=InfigraphStatus.ANALYSIS_FAILED,
                    reason=f"Analysis command failed. Return code {result.returncode}: {result.stderr.strip()}"
                )

            try:
                data = json.loads(result.stdout)
                return InfigraphResult(status=InfigraphStatus.ANALYSIS_COMPLETE, data=data)
            except json.JSONDecodeError:
                return InfigraphResult(
                    status=InfigraphStatus.ANALYSIS_FAILED,
                    reason="Malformed output from analysis command"
                )

        except subprocess.TimeoutExpired:
            return InfigraphResult(
                status=InfigraphStatus.ANALYSIS_FAILED,
                reason="Analysis command timed out"
            )
```

#### Test Plan

Create `tests/kb/test_infigraph.py` that utilizes a fake executable or mocks `subprocess.run` to cover:
1. Successful capability discovery (returns proper JSON with matching version and capabilities).
2. Missing required capabilities (returns missing fields).
3. Version mismatch.
4. Executable missing (raises `FileNotFoundError`).
5. Execution timeout (raises `subprocess.TimeoutExpired`).
6. Malformed JSON output.
7. Successful analysis command.
8. Failed analysis command (non-zero return code).

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Add reproducible Infigraph runtime and capability contract | RC-1 | #597 | `scripts/kb/infigraph.py`, `tests/kb/test_infigraph.py` | Low |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/kb/infigraph.py` | 1 | Create |
| `tests/kb/test_infigraph.py` | 1 | Create |

## Unaddressable Issues

None
