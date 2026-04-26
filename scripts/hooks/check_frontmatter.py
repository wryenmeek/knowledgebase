"""Pre-commit hook: validate wiki page and SKILL.md frontmatter.

Pre-commit passes filenames as positional arguments. For each file:
- ``**/SKILL.md`` → checked for REQUIRED_SKILL_FIELDS (takes precedence).
- ``wiki/**/*.md`` → checked for REQUIRED_WIKI_FIELDS.
- All other markdown files → skipped.

Exits non-zero if any file fails frontmatter validation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.kb.page_template_utils import (
    REQUIRED_PERSONA_FIELDS,
    REQUIRED_SKILL_FIELDS,
    REQUIRED_WIKI_FIELDS,
    parse_frontmatter,
)


def _check_file(path_str: str) -> list[str]:
    """Return a list of error messages for *path_str*, or empty list on success."""
    # Normalize separators.
    norm = path_str.replace("\\", "/")
    # Extract path components to detect file type without relying on fnmatch
    # against absolute paths (which would fail in test environments).
    basename = norm.rsplit("/", 1)[-1]

    # SKILL.md takes precedence over wiki/**/*.md for dual-match files.
    is_skill = basename == "SKILL.md"
    # Agent persona: any .md file under a .github/agents/ path component.
    is_persona = not is_skill and ("/agents/" in norm or norm.startswith("agents/"))
    # Wiki page: any .md file that has "/wiki/" as a path component.
    is_wiki = not is_skill and not is_persona and ("/wiki/" in norm or norm.startswith("wiki/"))

    if not is_skill and not is_persona and not is_wiki:
        return []

    if is_persona:
        required_fields = REQUIRED_PERSONA_FIELDS
    elif is_skill:
        required_fields = REQUIRED_SKILL_FIELDS
    else:
        required_fields = REQUIRED_WIKI_FIELDS

    try:
        text = Path(path_str).read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path_str}: cannot read file: {exc}"]

    if not text.strip():
        return [f"{path_str}: missing frontmatter (empty file)"]

    try:
        frontmatter = parse_frontmatter(text)
    except Exception:
        frontmatter = {}

    if frontmatter is None:
        frontmatter = {}

    errors: list[str] = []

    if not text.startswith("---"):
        errors.append(f"{path_str}: missing frontmatter block")
        return errors

    for field in required_fields:
        if field not in frontmatter:
            errors.append(f"{path_str}: missing required field '{field}'")
        elif not frontmatter[field] and frontmatter[field] != 0:
            errors.append(f"{path_str}: field '{field}' is present but empty")

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
