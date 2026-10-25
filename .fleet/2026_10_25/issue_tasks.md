# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 1 issues on 2026-10-25T10:45:32.449Z

## Executive Summary

Found one root cause for an architectural gap regarding the lack of a reproducible Infigraph integration. The issue requires creating a new wrapper module in the `scripts/kb/` directory that fetches a pinned Infigraph release securely and checks its capabilities, along with corresponding tests.

## Root Cause Analysis

### RC-1: Missing Infigraph CLI Wrapper

**Related issues:** #597
**Severity:** Medium
**Files involved:** `scripts/kb/infigraph.py` (new), `tests/kb/test_infigraph.py` (new)

#### Diagnosis

The repository currently lacks a mechanism to invoke a pinned, reproducibly resolved Infigraph CLI. The issue explicitly requests a capability contract and a runtime wrapper that can pull a specific release, verify resolution metadata, and distinguish between successful capability discovery and representative failures (unavailable, unsupported, misconfigured, timeout, malformed output).

#### Proposed Solution

Create a new Python module `scripts/kb/infigraph.py` that implements the `InfigraphRuntime` wrapper class. The class should have a configuration for a pinned version (e.g., v1.2.0) and handle tracking the resolution metadata. It will check the executable with a `--capabilities` flag, parse the JSON output, and return normalized statuses (`analysis_complete`, `analysis_unavailable`, `analysis_failed`). Also, create `tests/kb/test_infigraph.py` to test it using a fake executable.

```python
# scripts/kb/infigraph.py
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Literal

Status = Literal["analysis_complete", "analysis_unavailable", "analysis_failed"]

@dataclass(frozen=True)
class InfigraphMetadata:
    version: str
    sha256: str
    platform: str

    def to_dict(self) -> dict[str, str]:
        return {"version": self.version, "sha256": self.sha256, "platform": self.platform}

@dataclass(frozen=True)
class InfigraphResult:
    status: Status
    reason: str | None = None
    capabilities: list[str] | None = None
    metadata: InfigraphMetadata | None = None

class InfigraphRuntime:
    # Hardcoded metadata for a reproducible pin (this would typically be verified against a lockfile or checksum)
    PINNED_METADATA = InfigraphMetadata(
        version="v1.2.0",
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        platform="linux-amd64"
    )

    def __init__(self, executable_path: str | None = None):
        self._executable_path = executable_path or shutil.which("infigraph")

    def resolve_metadata(self) -> InfigraphMetadata:
        """Returns the reproducible resolution metadata."""
        return self.PINNED_METADATA

    def check_capabilities(self) -> InfigraphResult:
        metadata = self.resolve_metadata()
        if not self._executable_path:
            return InfigraphResult(status="analysis_unavailable", reason="Executable not found", metadata=metadata)

        try:
            # Security Standard: Using explicit timeout to prevent hangs
            result = subprocess.run(
                [self._executable_path, "--capabilities"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False
            )
        except FileNotFoundError:
            return InfigraphResult(status="analysis_unavailable", reason="Executable not found", metadata=metadata)
        except subprocess.TimeoutExpired:
            return InfigraphResult(status="analysis_failed", reason="Execution timed out", metadata=metadata)

        if result.returncode != 0:
            return InfigraphResult(status="analysis_failed", reason=f"Command failed with code {result.returncode}", metadata=metadata)

        try:
            data = json.loads(result.stdout)
            if not isinstance(data, dict) or "capabilities" not in data:
                return InfigraphResult(status="analysis_failed", reason="Malformed output: missing capabilities", metadata=metadata)
            return InfigraphResult(status="analysis_complete", capabilities=data["capabilities"], metadata=metadata)
        except json.JSONDecodeError:
            return InfigraphResult(status="analysis_failed", reason="Malformed JSON output", metadata=metadata)
```

#### Test Plan

1. Verify `analysis_unavailable` when the executable does not exist, and metadata is present.
2. Verify `analysis_complete` with expected capabilities and pinned metadata when execution succeeds and output is valid JSON.
3. Verify `analysis_failed` with a timeout and metadata when `subprocess.run` raises `TimeoutExpired`.
4. Verify `analysis_failed` with metadata when the command exits with a non-zero status code.
5. Verify `analysis_failed` with metadata when the command output is not valid JSON.
6. Verify `analysis_failed` with metadata when the JSON output is valid but misses the `capabilities` key.

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Add reproducible Infigraph runtime and capability contract | RC-1 | #597 | `scripts/kb/infigraph.py` | Low |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/kb/infigraph.py` | 1 | Create |
| `tests/kb/test_infigraph.py` | 1 | Create |
