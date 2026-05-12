"""Shared helpers for parsing small slices of workflow YAML text.

Workflow contract tests prefer a dependency-free indent-aware parser over
adding a YAML dependency to the test suite. These helpers centralize the
common parsing shapes that previously lived duplicated in per-CI test files.
"""

from __future__ import annotations

from pathlib import Path


def leading_spaces(line: str) -> int:
    """Return the count of leading space characters on ``line``."""
    return len(line) - len(line.lstrip(" "))


def parse_top_level_mapping_block(
    text: str,
    key: str,
    *,
    workflow_path: Path,
) -> dict[str, str]:
    """Parse a single top-level ``key:`` mapping block into ``{str: str}``.

    Raises AssertionError when the top-level key is missing; callers use this
    to drive pytest failures directly.
    """
    lines = text.splitlines()
    target = f"{key}:"

    for index, line in enumerate(lines):
        if line.strip() != target or line.startswith(" "):
            continue

        mapping: dict[str, str] = {}
        for candidate in lines[index + 1 :]:
            stripped = candidate.strip()
            if not stripped:
                continue
            if not candidate.startswith("  ") or candidate.startswith("    "):
                break
            if stripped.startswith("#") or ":" not in stripped:
                continue
            map_key, map_value = stripped.split(":", 1)
            mapping[map_key.strip()] = map_value.strip()

        return mapping

    raise AssertionError(f"Top-level '{key}' block is missing from {workflow_path}")
