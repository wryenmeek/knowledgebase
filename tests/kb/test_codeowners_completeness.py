"""Drift contract: .github/CODEOWNERS paths must match CONTEXT.md 'sensitive paths' term.

Parses the 'sensitive paths' row from CONTEXT.md ## Terms and asserts the set
of paths equals the set of paths declared in .github/CODEOWNERS (modulo
CODEOWNERS' leading '/' anchor). Fails on either side being a strict subset of
the other.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTEXT_MD = REPO_ROOT / "CONTEXT.md"
CODEOWNERS = REPO_ROOT / ".github" / "CODEOWNERS"

# Sentinel that marks the end of the path enumeration in the 'sensitive paths'
# definition cell. Everything from this text onwards is discarded before
# extracting backtick-quoted paths to avoid picking up .github/CODEOWNERS itself
# or unrelated test-file paths mentioned later in the prose.
_DEFINITION_LIST_END_SENTINEL = ". Referenced by"

# Marker that introduces the path list inside the definition cell. Splitting on
# this text lets us skip any prose or backtick-quoted non-path text that
# precedes the enumeration.
_DEFINITION_LIST_START_SENTINEL = "notification:"


def _parse_sensitive_paths_from_context() -> set[str]:
    """Extract the 'sensitive paths' list from CONTEXT.md ## Terms table."""
    text = CONTEXT_MD.read_text(encoding="utf-8")

    terms_match = re.search(r"^## Terms\s*$", text, re.MULTILINE)
    if not terms_match:
        raise AssertionError("Could not find '## Terms' section in CONTEXT.md")

    terms_section = text[terms_match.end():]

    row_match = re.search(
        r"^\|\s*sensitive paths\s*\|([^|]+)\|",
        terms_section,
        re.MULTILINE,
    )
    if not row_match:
        raise AssertionError(
            "Could not find 'sensitive paths' row in CONTEXT.md ## Terms"
        )

    definition = row_match.group(1)

    # Isolate just the path enumeration: content after the introductory colon
    # and before the "Referenced by" prose.  Both sentinels are module-level
    # constants so a single place needs updating if the wording ever changes.
    if _DEFINITION_LIST_START_SENTINEL in definition:
        definition = definition.split(_DEFINITION_LIST_START_SENTINEL, 1)[1]
    relevant_part = definition.split(_DEFINITION_LIST_END_SENTINEL)[0]

    return set(re.findall(r"`([^`]+)`", relevant_part))


def _parse_codeowners_paths() -> set[str]:
    """Parse .github/CODEOWNERS and return paths with the leading '/' stripped."""
    text = CODEOWNERS.read_text(encoding="utf-8")
    paths: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if not parts:
            continue
        paths.add(parts[0].lstrip("/"))
    return paths


def test_codeowners_file_exists() -> None:
    """CODEOWNERS file must exist at .github/CODEOWNERS."""
    assert CODEOWNERS.is_file(), ".github/CODEOWNERS does not exist"


def test_codeowners_paths_match_sensitive_paths_in_context_md() -> None:
    """CODEOWNERS paths must exactly match the 'sensitive paths' set in CONTEXT.md.

    Neither set may be a strict subset of the other — drift in either direction
    fails the test.
    """
    context_paths = _parse_sensitive_paths_from_context()
    codeowners_paths = _parse_codeowners_paths()

    missing_from_codeowners = context_paths - codeowners_paths
    extra_in_codeowners = codeowners_paths - context_paths

    assert not missing_from_codeowners, (
        "Paths listed in CONTEXT.md 'sensitive paths' but absent from "
        f".github/CODEOWNERS: {sorted(missing_from_codeowners)}"
    )
    assert not extra_in_codeowners, (
        "Paths in .github/CODEOWNERS but not listed in CONTEXT.md "
        f"'sensitive paths': {sorted(extra_in_codeowners)}"
    )
