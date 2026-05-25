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


def parse_job_mapping_block(
    text: str,
    job_name: str,
    key: str,
    workflow_path: Path,
) -> dict[str, str]:
    """Parse a ``key:`` mapping block inside a named job into ``{str: str}``.

    Jobs are expected at 2-space indentation (``  job_name:``) and their keys
    at 4-space indentation (``    key:``).  Values are at 6-space indentation.

    Raises AssertionError when the job or the key block is missing; callers
    use this to drive pytest failures directly.
    """
    lines = text.splitlines()
    job_target = f"{job_name}:"
    key_target = f"{key}:"

    job_indices = [
        index
        for index, line in enumerate(lines)
        if line.strip() == job_target and line.startswith("  ") and not line.startswith("    ")
    ]
    if not job_indices:
        raise AssertionError(f"{workflow_path} is missing job '{job_name}'")
    if len(job_indices) > 1:
        raise AssertionError(f"{workflow_path} has duplicate job blocks for '{job_name}'")

    key_indices: list[int] = []
    for index in range(job_indices[0] + 1, len(lines)):
        candidate = lines[index]
        stripped = candidate.strip()
        if not stripped:
            continue
        if not candidate.startswith("    "):
            break
        if stripped == key_target and candidate.startswith("    ") and not candidate.startswith("      "):
            key_indices.append(index)

    if not key_indices:
        raise AssertionError(f"{workflow_path} is missing '{key}' block in job '{job_name}'")
    if len(key_indices) > 1:
        raise AssertionError(f"{workflow_path} has duplicate '{key}' blocks in job '{job_name}'")

    key_index = key_indices[0]
    mapping: dict[str, str] = {}
    for candidate in lines[key_index + 1 :]:
        stripped = candidate.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if not candidate.startswith("      ") or candidate.startswith("        "):
            break
        if ":" not in stripped:
            raise AssertionError(
                f"{workflow_path} has malformed entry in job '{job_name}' '{key}' block: {candidate}"
            )
        map_key, map_value = stripped.split(":", 1)
        mapping[map_key.strip()] = map_value.strip()

    return mapping
