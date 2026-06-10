#!/usr/bin/env python3
"""Pre-commit hook: require ``applyTo:`` on staged instruction files.

# ADR-028 (pending) — required-applyTo invariant

Frontmatter-less ``.github/instructions/*.instructions.md`` files are a hidden
ratchet: Copilot CLI's ``BXo`` splitter puts files without ``applyTo:`` into the
always-loaded bucket, silently promoting them to every-turn context. This hook
checks staged content via ``git show :<path>`` so the index, not the working tree,
is what determines whether a commit may proceed.
"""

from __future__ import annotations

import re
import subprocess
import sys

from scripts.kb.page_template_utils import (
    extract_frontmatter,
    extract_yaml_list,
    parse_frontmatter,
    strip_quotes,
)

INSTRUCTIONS_PATH_RE = re.compile(r"^\.github/instructions/.+\.instructions\.md$")
EMPTY_LIST_RE = re.compile(r"^\[\s*\]$")
YAML_NULL_VALUES = {"null", "Null", "NULL", "~"}


def _normalize_path(path: str) -> str:
    normalized = path
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _has_invalid_path_components(path: str) -> bool:
    parts = path.split("/")
    return path.startswith("/") or "\\" in path or ".." in parts or "" in parts


def _get_instruction_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    instruction_paths: list[str] = []
    failures: list[str] = []

    for path in paths:
        normalized = _normalize_path(path)
        if not INSTRUCTIONS_PATH_RE.fullmatch(normalized):
            continue
        if _has_invalid_path_components(normalized):
            failures.append(f"{path}: invalid .github/instructions path")
            continue
        instruction_paths.append(normalized)

    return instruction_paths, failures


def _get_staged_content(path: str) -> str | None:
    """Read the staged (index) version of a file."""
    result = subprocess.run(
        ["git", "show", f":{path}"], capture_output=True, text=True
    )
    return result.stdout if result.returncode == 0 else None


def _is_quoted_scalar(value: str) -> bool:
    return len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}


def _strip_unquoted_inline_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote == '"':
            escaped = True
            continue
        if char in {'"', "'"}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
        elif char == "#" and quote is None:
            return value[:index].strip()
    return value.strip()


def _is_empty_applyto(raw_value: str) -> bool:
    value = _strip_unquoted_inline_comment(raw_value)
    if not value:
        return True

    if _is_quoted_scalar(value):
        return not strip_quotes(value).strip()

    return (
        not value
        or value in YAML_NULL_VALUES
        or EMPTY_LIST_RE.fullmatch(value) is not None
    )


def _validate_applyto(path: str, content: str) -> str | None:
    frontmatter_text, _ = extract_frontmatter(content)
    if frontmatter_text is None:
        return f"{path}: missing frontmatter block with required non-empty applyTo:"

    frontmatter = parse_frontmatter(frontmatter_text)
    if "applyTo" not in frontmatter:
        return f"{path}: missing required non-empty applyTo: frontmatter field"

    raw_value = frontmatter["applyTo"]

    if not raw_value.strip():
        items = extract_yaml_list(frontmatter_text, "applyTo")
        if any(item.strip() for item in items):
            return None
        return f"{path}: empty applyTo: frontmatter field"

    if _is_empty_applyto(raw_value):
        return f"{path}: empty applyTo: frontmatter field"

    return None


def _is_path_in_index(path: str) -> bool:
    """Return True if ``path`` exists in the git index.

    For staged deletions, ``git show :<path>`` fails because the file is no
    longer in the index. ``git ls-files -- <path>`` returns an empty result
    in that case. Distinguishing a staged deletion from an unreadable file
    lets the hook skip deletions instead of blocking the commit.
    """
    result = subprocess.run(
        ["git", "ls-files", "--", path], capture_output=True, text=True
    )
    return bool(result.stdout.strip())


def main(argv: list[str] | None = None) -> int:
    files = sys.argv[1:] if argv is None else argv
    instruction_files, failures = _get_instruction_paths(files)
    if not instruction_files and not failures:
        return 0

    for path in instruction_files:
        content = _get_staged_content(path)
        if content is None:
            # Staged deletion: file no longer in the index. Skip rather than
            # block the commit.
            if not _is_path_in_index(path):
                continue
            failures.append(f"{path}: cannot read staged content via git show :{path}")
            continue

        failure = _validate_applyto(path, content)
        if failure is not None:
            failures.append(failure)

    if failures:
        print(
            "ERROR: .github/instructions/*.instructions.md files require "
            "non-empty applyTo: frontmatter.",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        print(
            "\nFix: add YAML frontmatter such as:\n"
            "---\n"
            'applyTo: "path/glob/**"\n'
            "---",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
