"""Shared page-template parsing and validation helpers."""

from __future__ import annotations

from os import PathLike
from pathlib import Path
import re

from . import path_utils


TEMPLATE_SECTION_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "entity": ("## Summary", "## Evidence", "## Open Questions"),
    "concept": ("## Summary", "## Evidence", "## Open Questions"),
    "source": ("## Summary", "## Evidence", "## Open Questions"),
    "analysis": ("## Summary", "## Evidence", "## Open Questions"),
}
_FRONTMATTER_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

TOPICAL_NAMESPACES: frozenset[str] = frozenset({"sources", "entities", "concepts", "analyses"})

REQUIRED_FRONTMATTER_KEYS: tuple[str, ...] = (
    "type",
    "title",
    "status",
    "sources",
    "open_questions",
    "confidence",
    "sensitivity",
    "updated_at",
    "tags",
)

# Pre-commit fast-path subsets — keep in sync with REQUIRED_FRONTMATTER_KEYS.
# These are the minimum fields checked by the frontmatter validation hook for
# each file type. They are strict subsets: every field here must also appear
# in REQUIRED_FRONTMATTER_KEYS (for wiki pages) or match the canonical SKILL.md
# schema (for skills).
REQUIRED_WIKI_FIELDS: tuple[str, ...] = (
    "type",
    "title",
    "status",
    "updated_at",
)
REQUIRED_SKILL_FIELDS: tuple[str, ...] = (
    "name",
    "description",
)


def is_nested_topical_page(path: Path, wiki_root: Path) -> bool:
    parts = path.relative_to(wiki_root).parts
    return len(parts) > 2 and parts[0] in TOPICAL_NAMESPACES


def normalize_page_path(value: str | PathLike[str]) -> str:
    try:
        return path_utils.normalize_repo_relative_path(value)
    except path_utils.RepoRelativePathError:
        raw_value = value.as_posix() if isinstance(value, Path) else str(value)
        if raw_value.startswith("/") or "\\" in raw_value:
            return raw_value
        return ""


def validate_page_template_path(
    page: str | PathLike[str],
    *,
    repo_root: str | Path,
    required_frontmatter_keys: tuple[str, ...],
    template_section_requirements: dict[str, tuple[str, ...]] = TEMPLATE_SECTION_REQUIREMENTS,
) -> tuple[str, tuple[tuple[str, str], ...]]:
    normalized_page = normalize_page_path(page)
    violations: list[tuple[str, str]] = []
    if not normalized_page.startswith("wiki/") or not normalized_page.endswith(".md"):
        violations.append(
            ("invalid-page-path", "page must be a repo-relative markdown path under wiki/**")
        )
        return normalized_page, tuple(violations)

    page_path = Path(repo_root) / normalized_page
    if not page_path.is_file():
        violations.append(("missing-page", "page does not exist"))
        return normalized_page, tuple(violations)

    text = page_path.read_text(encoding="utf-8")
    frontmatter, body = extract_frontmatter(text)
    if frontmatter is None:
        violations.append(("missing-frontmatter", "page must start with a YAML frontmatter block"))
        return normalized_page, tuple(violations)

    metadata = parse_frontmatter(frontmatter)
    for key in required_frontmatter_keys:
        if key not in metadata:
            violations.append(("missing-frontmatter-key", f"required key '{key}' is missing"))

    title = strip_quotes(metadata.get("title", ""))
    headings = extract_headings(body)
    if not title:
        violations.append(("missing-frontmatter-key", "required key 'title' is missing"))
    else:
        expected_heading = f"# {title}"
        if expected_heading not in headings:
            violations.append(("title-heading-mismatch", "H1 heading must match frontmatter title exactly"))

    page_type = strip_quotes(metadata.get("type", ""))
    for required_section in template_section_requirements.get(page_type, ()):
        if required_section not in headings:
            violations.append(
                ("missing-body-section", f"required section '{required_section}' is missing")
            )

    return normalized_page, tuple(violations)


def extract_frontmatter(text: str) -> tuple[str | None, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1 :])
    return None, text


def parse_frontmatter(frontmatter: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in frontmatter.splitlines():
        match = _FRONTMATTER_KEY_RE.match(line)
        if match:
            parsed[match.group(1)] = match.group(2).strip()
    return parsed


def parse_page_frontmatter(text: str) -> dict[str, str]:
    """Extract and parse frontmatter from a full page text, returning key→value pairs.

    Returns an empty dict when the text has no frontmatter block.
    Convenience wrapper over :func:`extract_frontmatter` + :func:`parse_frontmatter`.
    """
    frontmatter, _ = extract_frontmatter(text)
    if frontmatter is None:
        return {}
    return parse_frontmatter(frontmatter)


def strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def extract_sources_from_frontmatter(frontmatter: str) -> list[str]:
    """Return the list of source values from a YAML frontmatter block.

    Handles three forms of the ``sources:`` key:

    - Inline empty list:  ``sources: []`` → ``[]``
    - Inline single value: ``sources: repo://...`` → ``["repo://..."]``
    - Multi-line YAML list::

        sources:
          - repo://first
          - repo://second

    Returns an empty list when the ``sources:`` key is absent.
    Quotes are stripped from each value using :func:`strip_quotes`.
    """
    lines = frontmatter.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("sources:"):
            continue
        inline_value = stripped[len("sources:"):].strip()
        if inline_value == "[]":
            return []
        if inline_value:
            return [strip_quotes(inline_value)]
        sources: list[str] = []
        for raw_line in lines[index + 1:]:
            if not raw_line.startswith("  "):
                break
            item = raw_line.strip()
            if item.startswith("- "):
                sources.append(strip_quotes(item[2:].strip()))
        return sources
    return []


def extract_frontmatter_keys(frontmatter: str) -> set[str]:
    """Return the set of top-level key names present in a YAML frontmatter block."""
    keys: set[str] = set()
    for line in frontmatter.splitlines():
        match = _FRONTMATTER_KEY_RE.match(line)
        if match:
            keys.add(match.group(1))
    return keys


def extract_headings(body: str) -> set[str]:
    headings: set[str] = set()
    in_fenced_block = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fenced_block = not in_fenced_block
            continue
        if in_fenced_block:
            continue
        match = _HEADING_RE.match(stripped)
        if match:
            headings.add(f"{match.group(1)} {match.group(2)}")
    return headings


__all__ = [
    "REQUIRED_FRONTMATTER_KEYS",
    "REQUIRED_SKILL_FIELDS",
    "REQUIRED_WIKI_FIELDS",
    "TEMPLATE_SECTION_REQUIREMENTS",
    "TOPICAL_NAMESPACES",
    "extract_frontmatter",
    "extract_frontmatter_keys",
    "extract_headings",
    "extract_sources_from_frontmatter",
    "is_nested_topical_page",
    "normalize_page_path",
    "parse_frontmatter",
    "parse_page_frontmatter",
    "strip_quotes",
    "validate_page_template_path",
]
