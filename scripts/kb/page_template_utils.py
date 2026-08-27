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
_FRONTMATTER_BLOCK_RE = re.compile(
    r"^[ \t]*---[ \t]*\r?\n(.*?(?:\r?\n|(?<=\n)))^[ \t]*---[ \t]*(?:\r?\n|$)",
    re.MULTILINE | re.DOTALL,
)

TOPICAL_NAMESPACES: frozenset[str] = frozenset(
    {"sources", "entities", "concepts", "analyses"}
)

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
REQUIRED_PERSONA_FIELDS: tuple[str, ...] = (
    "name",
    "description",
    "updated_at",
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
    template_section_requirements: dict[
        str, tuple[str, ...]
    ] = TEMPLATE_SECTION_REQUIREMENTS,
) -> tuple[str, tuple[tuple[str, str], ...]]:
    normalized_page = normalize_page_path(page)
    violations: list[tuple[str, str]] = []
    if not normalized_page.startswith("wiki/") or not normalized_page.endswith(".md"):
        violations.append(
            (
                "invalid-page-path",
                "page must be a repo-relative markdown path under wiki/**",
            )
        )
        return normalized_page, tuple(violations)

    page_path = Path(repo_root) / normalized_page
    if not page_path.is_file():
        violations.append(("missing-page", "page does not exist"))
        return normalized_page, tuple(violations)

    text = page_path.read_text(encoding="utf-8")
    frontmatter, body = extract_frontmatter(text)
    if frontmatter is None:
        violations.append(
            ("missing-frontmatter", "page must start with a YAML frontmatter block")
        )
        return normalized_page, tuple(violations)

    metadata = parse_frontmatter(frontmatter)
    for key in required_frontmatter_keys:
        if key not in metadata:
            violations.append(
                ("missing-frontmatter-key", f"required key '{key}' is missing")
            )

    title = strip_quotes(metadata.get("title", ""))
    headings = extract_headings(body)
    if not title:
        violations.append(
            ("missing-frontmatter-key", "required key 'title' is missing")
        )
    else:
        expected_heading = f"# {title}"
        if expected_heading not in headings:
            violations.append(
                (
                    "title-heading-mismatch",
                    "H1 heading must match frontmatter title exactly",
                )
            )

    page_type = strip_quotes(metadata.get("type", ""))
    for required_section in template_section_requirements.get(page_type, ()):
        if required_section not in headings:
            violations.append(
                (
                    "missing-body-section",
                    f"required section '{required_section}' is missing",
                )
            )

    return normalized_page, tuple(violations)


def extract_frontmatter(text: str) -> tuple[str | None, str]:
    """Extract a YAML frontmatter block and body from a markdown document.

    Returns ``(frontmatter_str | None, body_str)``. When a frontmatter block
    matches, ``body_str`` is exactly ``text[match.end():]`` after the optional
    leading UTF-8 BOM strip described below, so the body characters are
    preserved verbatim. Body CRLF sequences are not normalized to LF, and a
    trailing body newline is preserved rather than dropped. This differs from
    the pre-PR-#298 ``splitlines()`` implementation, which normalized CRLF and
    dropped exactly one trailing body newline.

    If no frontmatter block is found, returns ``(None, text)`` unchanged for
    non-BOM inputs.

    UTF-8 BOM (`\\ufeff`) at the start of the text is stripped before parsing
    so files saved by Windows editors with the BOM still resolve their
    frontmatter (Issue #321). The stripped BOM is not echoed back to the
    body — callers that need to preserve byte identity should call this on
    text they've already normalised.
    """
    # Strip leading UTF-8 BOM so Windows-saved files don't silently miss
    # their frontmatter (the bare `lstrip(" \t")` below would not catch it).
    if text.startswith("\ufeff"):
        text = text[1:]

    # OPTIMIZATION: Isolate the first line using .find() before calling .lstrip()
    # to avoid allocating a massive new string copy if `text` is large.
    newline_pos = text.find("\n")
    first_line = text if newline_pos == -1 else text[:newline_pos]
    if not first_line.lstrip(" \t\r").startswith("---"):
        return None, text

    match = _FRONTMATTER_BLOCK_RE.match(text)
    if match:
        fm = match.group(1)
        # Strip exact matched trailing newline from frontmatter block
        if fm.endswith("\r\n"):
            fm = fm[:-2]
        elif fm.endswith("\n"):
            fm = fm[:-1]

        body = text[match.end() :]
        return fm, body
    return None, text


def parse_frontmatter(frontmatter: str) -> dict[str, str]:
    parsed: dict[str, str] = {}

    # Normalize line endings: CRLF -> LF, CR -> LF to handle all variants.
    if "\r" in frontmatter:
        frontmatter = frontmatter.replace("\r\n", "\n").replace("\r", "\n")

    start = 0
    end = frontmatter.find("\n")

    while end != -1:
        line = frontmatter[start:end]
        match = _FRONTMATTER_KEY_RE.match(line)
        if match:
            parsed[match.group(1)] = match.group(2).strip()
        start = end + 1
        end = frontmatter.find("\n", start)

    if start < len(frontmatter):
        line = frontmatter[start:]
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


def extract_yaml_list(frontmatter_str: str, key: str) -> list[str]:
    """Extract a YAML list value for *key* from a frontmatter string (no YAML parser).

    Handles inline ``key: []``, inline single value ``key: val``,
    and multi-line list form (``key:\n  - item``).
    """
    key_prefix = f"{key}:"
    # OPTIMIZATION: Fast-path literal check to avoid O(N) splitlines allocation
    if key_prefix not in frontmatter_str:
        return []

    lines = frontmatter_str.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith(key_prefix):
            continue
        inline = stripped[len(key_prefix) :].strip()
        if inline == "[]":
            return []
        if inline:
            return [inline.strip('"').strip("'")]
        items: list[str] = []
        for raw in lines[index + 1 :]:
            if not raw.startswith("  "):
                break
            item = raw.strip()
            if item.startswith("- "):
                items.append(item[2:].strip().strip('"').strip("'"))
        return items
    return []


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
    # OPTIMIZATION: Fast-path literal check to avoid O(N) splitlines allocation
    if "sources:" not in frontmatter:
        return []

    lines = frontmatter.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("sources:"):
            continue
        inline_value = stripped[len("sources:") :].strip()
        if inline_value == "[]":
            return []
        if inline_value:
            return [strip_quotes(inline_value)]
        sources: list[str] = []
        for raw_line in lines[index + 1 :]:
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
    """Extract markdown headings from ``body`` as a set of ``"# text"`` strings.

    Streams through ``body`` using ``find('\\n')`` slicing instead of
    ``splitlines()`` to avoid materializing an O(N) line array. Skips
    headings inside fenced code blocks (``` or ~~~).

    CRLF and bare CR (Classic Mac) line endings are normalized to LF before
    streaming, so all three common line-ending conventions are handled correctly.
    The normalization is guarded by an ``\\r`` membership test so LF-only bodies
    (the common case) pay only a single O(N) scan rather than two replace passes.
    """
    headings: set[str] = set()
    in_fenced_block = False

    # Normalize line endings: CRLF → LF, then bare CR → LF.
    # The streaming find('\n') loop only treats LF as a break;
    # this guards against Classic-Mac CR-only files producing
    # silently empty heading lists.
    if "\r" in body:
        body = body.replace("\r\n", "\n").replace("\r", "\n")

    def _maybe_add(line: str) -> None:
        nonlocal in_fenced_block
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fenced_block = not in_fenced_block
            return
        if in_fenced_block:
            return
        if stripped.startswith("#"):
            match = _HEADING_RE.match(stripped)
            if match:
                headings.add(f"{match.group(1)} {match.group(2)}")

    start = 0
    end = body.find("\n")
    while end != -1:
        _maybe_add(body[start:end])
        start = end + 1
        end = body.find("\n", start)
    if start < len(body):
        _maybe_add(body[start:])

    return headings


__all__ = [
    "REQUIRED_FRONTMATTER_KEYS",
    "REQUIRED_PERSONA_FIELDS",
    "REQUIRED_SKILL_FIELDS",
    "REQUIRED_WIKI_FIELDS",
    "TEMPLATE_SECTION_REQUIREMENTS",
    "TOPICAL_NAMESPACES",
    "extract_frontmatter",
    "extract_frontmatter_keys",
    "extract_headings",
    "extract_sources_from_frontmatter",
    "extract_yaml_list",
    "is_nested_topical_page",
    "normalize_page_path",
    "parse_frontmatter",
    "parse_page_frontmatter",
    "strip_quotes",
    "validate_page_template_path",
]
