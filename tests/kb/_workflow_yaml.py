"""Shared helpers for parsing small slices of workflow YAML text.

Workflow contract tests prefer a dependency-free indent-aware parser over
adding a YAML dependency to the hot path. These helpers centralize recurring
mapping and step extraction logic used by workflow contract suites.
"""

from __future__ import annotations

from pathlib import Path


def leading_spaces(line: str) -> int:
    """Return the count of leading space characters on ``line``."""
    return len(line) - len(line.lstrip(" "))


def _parse_mapping_block(
    lines: list[str],
    block_start: int,
    *,
    indent: int,
    context: str,
    workflow_path: Path,
) -> dict[str, str]:
    """Parse a one-level mapping block and fail on malformed or duplicate keys."""
    mapping: dict[str, str] = {}
    duplicate_keys: set[str] = set()
    expected_prefix = " " * indent
    nested_prefix = expected_prefix + "  "

    for candidate in lines[block_start + 1 :]:
        stripped = candidate.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if not candidate.startswith(expected_prefix) or candidate.startswith(nested_prefix):
            break
        if ":" not in stripped:
            raise AssertionError(f"{workflow_path} has malformed entry in {context}: {candidate}")
        map_key, map_value = stripped.split(":", 1)
        normalized_key = map_key.strip()
        if normalized_key in mapping:
            duplicate_keys.add(normalized_key)
        mapping[normalized_key] = map_value.strip()

    if duplicate_keys:
        duplicates = ", ".join(sorted(duplicate_keys))
        raise AssertionError(f"{workflow_path} has duplicate keys in {context}: {duplicates}")

    return mapping


def parse_top_level_mapping_block(
    text: str,
    key: str,
    *,
    workflow_path: Path,
) -> dict[str, str]:
    """Parse a single top-level ``key:`` mapping block into ``{str: str}``."""
    lines = text.splitlines()
    target = f"{key}:"

    for index, line in enumerate(lines):
        if line.strip() != target or line.startswith(" "):
            continue
        return _parse_mapping_block(
            lines,
            index,
            indent=2,
            context=f"top-level '{key}' block",
            workflow_path=workflow_path,
        )

    raise AssertionError(f"Top-level '{key}' block is missing from {workflow_path}")


def parse_job_mapping_block(
    text: str,
    job_name: str,
    key: str,
    workflow_path: Path,
) -> dict[str, str]:
    """Parse a ``key:`` mapping block inside a named job into ``{str: str}``."""
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

    return _parse_mapping_block(
        lines,
        key_indices[0],
        indent=6,
        context=f"job '{job_name}' '{key}' block",
        workflow_path=workflow_path,
    )


def extract_named_step_block(text: str, step_name: str, *, workflow_path: Path) -> str:
    """Extract one workflow step block by exact ``- name:`` match."""
    lines = text.splitlines()
    target = f"- name: {step_name}"
    matches = [index for index, line in enumerate(lines) if line.strip() == target]
    if not matches:
        raise AssertionError(f"{workflow_path} is missing step '{step_name}'")
    if len(matches) > 1:
        raise AssertionError(f"{workflow_path} has duplicate steps named '{step_name}'")

    start = matches[0]
    step_indent = leading_spaces(lines[start])
    end = len(lines)

    for index in range(start + 1, len(lines)):
        candidate = lines[index]
        stripped = candidate.strip()
        if stripped.startswith("- name:") and leading_spaces(candidate) == step_indent:
            end = index
            break
        if stripped and leading_spaces(candidate) < step_indent:
            end = index
            break

    return "\n".join(lines[start:end])
