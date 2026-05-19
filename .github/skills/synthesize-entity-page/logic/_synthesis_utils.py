"""
Shared utilities for synthesis-curator page-writing logic.

Used by synthesize_entity_page.py and synthesize_concept_page.py.
Not a CLI entry point — import only.

Public API
----------
- ``_sanitize_llm_str(value, max_len)`` — strip newlines/nulls from LLM output; apply before
  passing any field to ``render_draft_page`` or ``append_to_existing_page``.
- ``title_to_slug(title)`` — kebab-case slug, max 200 chars.
- ``find_duplicate(candidates, title, aliases)`` — case-insensitive dedup scan.
  **Callers must fail-closed when > 1 match is returned** (skip, not error).
- ``scan_existing_pages(wiki_root, namespace)`` — lists ``{title, aliases, path}`` dicts;
  logs parse errors and continues (partial results are better than crashing).
- ``render_draft_page(...)`` — renders a full wiki page markdown string.
- ``validate_draft_frontmatter(content)`` — returns list of missing required keys.
- ``validate_draft_structure(draft)`` — returns list of structural violations.
- ``append_to_existing_page(page_path, new_source_ref, new_open_questions)`` — appends new
  SourceRef and/or open_questions to an existing page.  Returns ``True`` if the page was
  modified, ``False`` if there was nothing new to add (not an error).
- ``_replace_yaml_list_block(frontmatter_str, key, new_items)`` — frontmatter surgery helper.
"""

from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# LLM output sanitisation
# ---------------------------------------------------------------------------


def _sanitize_llm_str(value: object, *, max_len: int = 500) -> str:
    """Strip newlines, carriage returns, and null bytes from LLM-returned strings.

    These characters can terminate YAML string literals prematurely and inject
    arbitrary YAML keys into frontmatter.  Apply to every field read from the
    extraction bundle before passing to ``render_draft_page`` or
    ``append_to_existing_page``.
    """
    if not isinstance(value, str):
        return ""
    value = re.sub(r"[\r\n\x00]", " ", value)
    return value[:max_len].strip()

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # repo root

from scripts.kb.page_template_utils import (
    extract_frontmatter,
    extract_sources_from_frontmatter,
    extract_yaml_list,
    parse_frontmatter,
)
from scripts.kb.write_utils import write_text_capturing_previous_safe


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------


def title_to_slug(title: str) -> str:
    """Convert a canonical title to a URL-safe kebab-case slug (max 200 chars)."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug.strip())
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug.strip("-") or "untitled")[:200]


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


def find_duplicate(
    candidates: list[dict[str, Any]],
    title: str,
    aliases: list[str],
) -> list[dict[str, Any]]:
    """Return all existing pages whose title or alias matches the proposed title/aliases.

    Comparison is case-insensitive. Callers must fail-closed when > 1 match is found.
    """
    target_names = {v.lower() for v in [title, *aliases] if v}
    return [
        p
        for p in candidates
        if p["title"].lower() in target_names
        or any(a.lower() in target_names for a in (p.get("aliases") or []))
    ]


# ---------------------------------------------------------------------------
# YAML frontmatter list surgery
# ---------------------------------------------------------------------------


def _extract_yaml_list_from_str(frontmatter_str: str, key: str) -> list[str]:
    """Backward-compatible wrapper around scripts.kb.page_template_utils.extract_yaml_list."""
    return extract_yaml_list(frontmatter_str, key)


# ---------------------------------------------------------------------------
# Existing-page scanning
# ---------------------------------------------------------------------------


def scan_existing_pages(wiki_root: Path, namespace: str) -> list[dict]:
    """Return a list of ``{title, aliases, path}`` for all pages in a namespace."""
    ns_dir = wiki_root / namespace
    if not ns_dir.is_dir():
        return []
    results: list[dict] = []
    for page_path in sorted(ns_dir.glob("*.md")):
        try:
            content = page_path.read_text(encoding="utf-8")
            fm_str, _ = extract_frontmatter(content)
            if fm_str is None:
                continue
            fm = parse_frontmatter(fm_str)
            title = fm.get("title", "").strip().strip('"').strip("'")
            aliases = _extract_yaml_list_from_str(fm_str, "aliases") if fm_str else []
            results.append({"title": title, "aliases": aliases, "path": str(page_path)})
        except Exception as exc:
            print(
                f"warning: scan_existing_pages: failed to parse {page_path}: {exc}",
                file=sys.stderr,
            )
    return results


# ---------------------------------------------------------------------------
# Replace YAML list block
# ---------------------------------------------------------------------------


def _replace_yaml_list_block(
    frontmatter_str: str, key: str, new_items: list[str]
) -> str:
    """Replace the YAML list block for `key` in frontmatter with `new_items`.

    Handles both inline ``key: []`` and multi-line form.
    Appends a new key block if the key is not found.
    """
    if new_items:
        replacement_lines = [f"{key}:"] + [f'  - "{item}"' for item in new_items]
    else:
        replacement_lines = [f"{key}: []"]

    lines = frontmatter_str.splitlines()
    key_prefix = f"{key}:"
    start: int | None = None
    end: int | None = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith(key_prefix):
            continue
        start = i
        inline = stripped[len(key_prefix) :].strip()
        if inline:
            # Inline form (e.g., "key: []" or "key: value")
            end = i + 1
        else:
            # Multi-line form: scan list items
            end = i + 1
            while end < len(lines) and lines[end].startswith("  "):
                end += 1
        break

    if start is None:
        # Key not found: append
        return frontmatter_str + "\n" + "\n".join(replacement_lines)

    new_lines = lines[:start] + replacement_lines + lines[end:]
    return "\n".join(new_lines)


# ---------------------------------------------------------------------------
# Page content rendering
# ---------------------------------------------------------------------------

_REQUIRED_FRONTMATTER_KEYS = (
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


def _yaml_dq_escape(s: str) -> str:
    """Escape a string for use inside a YAML double-quoted scalar."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def render_draft_page(
    *,
    page_type: str,
    title: str,
    aliases: list[str],
    source_ref: str,
    summary: str,
    evidence: str,
    tags: list[str],
    open_questions: list[str],
    confidence: int = 2,
    sensitivity: str = "internal",
) -> str:
    """Render a full wiki page draft as a markdown string."""
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    escaped_title = _yaml_dq_escape(title)
    sources_block = f'  - "{source_ref}"' if source_ref else "  []"
    tag_lines = (
        "\n".join(f'  - "{_yaml_dq_escape(t)}"' for t in tags) if tags else '  - "draft"'
    )
    oq_multiline = (
        "\n" + "\n".join(f'  - "{_yaml_dq_escape(q)}"' for q in open_questions)
        if open_questions
        else ""
    )
    oq_yaml = f"open_questions:{oq_multiline if open_questions else ' []'}"
    body_oq = "\n".join(f"- {q}" for q in open_questions) if open_questions else "*(none)*"
    evidence_clean = evidence.strip() or "*(see source page)*"
    aliases_fm = (
        "\naliases:\n" + "\n".join(f'  - "{_yaml_dq_escape(a)}"' for a in aliases)
        if aliases
        else ""
    )

    page = (
        f"---\n"
        f"type: {page_type}\n"
        f'title: "{escaped_title}"\n'
        f"status: active\n"
        f"sources:\n"
        f"{sources_block}\n"
        f"{oq_yaml}\n"
        f"confidence: {confidence}\n"
        f"sensitivity: {sensitivity}\n"
        f'updated_at: "{now}"\n'
        f"tags:\n"
        f"{tag_lines}\n"
        f"{aliases_fm}".rstrip()
        + "\n---\n"
        f"\n# {title}\n"
        f"\n## Summary\n{summary.strip()}\n"
        f"\n## Evidence\n- {evidence_clean}\n"
        f"\n## Open Questions\n{body_oq}\n"
    )
    return page


def validate_draft_frontmatter(content: str) -> list[str]:
    """Return a list of missing required frontmatter keys (empty = valid)."""
    fm_str, _ = extract_frontmatter(content)
    if fm_str is None:
        return ["no frontmatter block found"]
    fm = parse_frontmatter(fm_str)
    missing = [k for k in _REQUIRED_FRONTMATTER_KEYS if k not in fm]
    return missing


def validate_draft_structure(draft: str) -> list[str]:
    """Return a list of structural draft violations (empty = valid)."""
    fm_str, _ = extract_frontmatter(draft)
    if fm_str is None:
        return ["frontmatter missing or undetected"]

    parts = draft.split("\n---\n", 1)
    if len(parts) != 2:
        return ["frontmatter closing delimiter missing or malformed"]

    body = parts[1]
    violations: list[str] = []
    if body.startswith("---"):
        violations.append("body starts with an unexpected frontmatter delimiter")
    return violations


# ---------------------------------------------------------------------------
# Existing-page update (append-only)
# ---------------------------------------------------------------------------


def append_to_existing_page(
    page_path: Path,
    new_source_ref: str,
    new_open_questions: list[str],
) -> bool:
    """Append a SourceRef and open_questions to an existing page.

    Does NOT overwrite any existing prose. Returns True if the page was modified.
    """
    content = page_path.read_text(encoding="utf-8")
    fm_str, body = extract_frontmatter(content)
    if fm_str is None:
        return False

    current_sources = extract_sources_from_frontmatter(fm_str)
    changed = False
    if new_source_ref and new_source_ref not in current_sources:
        current_sources.append(new_source_ref)
        changed = True

    current_oqs = _extract_yaml_list_from_str(fm_str, "open_questions")
    for oq in new_open_questions:
        if oq and oq not in current_oqs:
            current_oqs.append(oq)
            changed = True

    if not changed:
        return False

    new_fm = _replace_yaml_list_block(fm_str, "sources", current_sources)
    new_fm = _replace_yaml_list_block(new_fm, "open_questions", current_oqs)
    new_content = f"---\n{new_fm}\n---\n{body}"
    write_text_capturing_previous_safe(page_path, new_content)
    return True
