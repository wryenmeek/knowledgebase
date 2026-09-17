# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 1 issues on 2026-09-17T10:59:26.843Z

## Executive Summary

Identified 1 missing feature requiring a new wrapper for the Infigraph CLI. All issues are addressable within the repository.

## Root Cause Analysis

### RC-1: Missing Infigraph CLI wrapper and capability contract

**Related issues:** #597
**Severity:** Medium
**Files involved:** `scripts/kb/infigraph.py` (new), `tests/kb/test_infigraph.py` (new)

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

# Reproducible resolution metadata
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

1. Missing executable: Call check_capabilities() with a non-existent executable path. Expect `ANALYSIS_UNAVAILABLE` with "Executable unavailable" reason.
2. Capability timeout: Mock subprocess to raise TimeoutExpired. Expect `ANALYSIS_FAILED` with timeout reason.
3. Malformed JSON output: Mock subprocess to output non-JSON strings. Expect `ANALYSIS_UNAVAILABLE` (for capabilities) or `ANALYSIS_FAILED` (for analysis).
4. Missing required capabilities: Mock subprocess to output JSON with missing capability. Expect `ANALYSIS_UNAVAILABLE` with missing capability reason.
5. Successful execution: Mock subprocess to output correct version, capabilities, and analysis JSON. Expect `ANALYSIS_COMPLETE` with parsed data.

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

Issues that require changes outside this repository (backend API, infrastructure, product decisions):

| Issue | Reason | Suggested Owner |
|-------|--------|-----------------|
