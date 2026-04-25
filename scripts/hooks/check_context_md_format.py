"""Pre-commit hook: validate CONTEXT.md format.

Checks that any staged ``CONTEXT.md`` file:
- Has frontmatter with ``scope`` and ``last_updated`` fields.
- Contains the required section headings: ``## Terms``, ``## Invariants``,
  ``## File Roles``.
- Is at most 200 lines.
- Headings inside fenced code blocks do not count toward requirements.

Pre-commit configures this hook with ``files: 'CONTEXT\\.md$'``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.kb.page_template_utils import parse_frontmatter

REQUIRED_SECTIONS = ("## Terms", "## Invariants", "## File Roles")
MAX_LINES = 200
REQUIRED_FRONTMATTER = ("scope", "last_updated")


def _check_file(path_str: str) -> list[str]:
    errors: list[str] = []

    try:
        text = Path(path_str).read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path_str}: cannot read file: {exc}"]

    if not text.strip():
        errors.append(f"{path_str}: empty file — CONTEXT.md requires frontmatter and sections")
        return errors

    lines = text.splitlines()

    # Line count check.
    if len(lines) > MAX_LINES:
        errors.append(
            f"{path_str}: file has {len(lines)} lines; maximum is {MAX_LINES}"
        )

    # Frontmatter check.
    try:
        frontmatter = parse_frontmatter(text) or {}
    except Exception:
        frontmatter = {}

    if not text.startswith("---"):
        errors.append(f"{path_str}: missing frontmatter block")
    else:
        for field in REQUIRED_FRONTMATTER:
            if field not in frontmatter:
                errors.append(f"{path_str}: missing required frontmatter field '{field}'")
            elif not frontmatter[field] and frontmatter[field] != 0:
                errors.append(f"{path_str}: frontmatter field '{field}' is empty")

    # Section heading check — skip headings inside fenced code blocks.
    found_sections: set[str] = set()
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
        if in_fence:
            continue
        # Check exact heading match (case-sensitive, strip trailing whitespace).
        for section in REQUIRED_SECTIONS:
            if stripped == section or stripped.startswith(section + " "):
                found_sections.add(section)

    for section in REQUIRED_SECTIONS:
        if section not in found_sections:
            errors.append(f"{path_str}: missing required section '{section}'")

    return errors


def main(argv: list[str] | None = None) -> int:
    files = argv if argv is not None else sys.argv[1:]
    all_errors: list[str] = []
    for f in files:
        all_errors.extend(_check_file(f))
    for err in all_errors:
        print(f"ERROR: {err}", file=sys.stderr)
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
