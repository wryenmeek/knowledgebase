"""Pre-commit hook: validate SourceRef citation format in wiki markdown files.

Validates that every ``repo://`` citation in a staged wiki markdown file matches
the canonical SourceRef format.  Skips content inside:

- YAML frontmatter blocks (between leading ``---`` delimiters).
- Fenced code blocks (``` or ~~~).

Scoped to ``wiki/**`` files only via pre-commit ``files:`` filter.  Documentation
files (docs/, schema/, AGENTS.md, etc.) contain template examples that are not
real SourceRefs and are intentionally excluded.

Reports all malformed citations (not just the first) so authors can fix them
in a single pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.kb.sourceref import SOURCEREF_RE

_REPO_PREFIX = "repo://"


def _check_file(path_str: str) -> list[str]:
    errors: list[str] = []
    try:
        text = Path(path_str).read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path_str}: cannot read file: {exc}"]

    lines = text.splitlines()
    in_frontmatter = False
    frontmatter_done = False
    in_fence = False
    fence_char: str = ""

    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()

        # YAML frontmatter detection (leading --- block).
        if not frontmatter_done:
            if lineno == 1 and stripped == "---":
                in_frontmatter = True
                continue
            if in_frontmatter:
                if stripped == "---" or stripped == "...":
                    in_frontmatter = False
                    frontmatter_done = True
                continue

        # Fenced code block detection.
        if stripped.startswith("```") or stripped.startswith("~~~"):
            if in_fence:
                if stripped.startswith(fence_char):
                    in_fence = False
                    fence_char = ""
            else:
                in_fence = True
                fence_char = stripped[:3]
            continue

        if in_fence:
            continue

        # Scan line for repo:// citations.
        if _REPO_PREFIX not in line:
            continue

        # Find all raw repo:// occurrences and validate each.
        pos = 0
        while True:
            idx = line.find(_REPO_PREFIX, pos)
            if idx == -1:
                break
            # SOURCEREF_RE extracts what it considers the SourceRef token.
            # Strip trailing markdown structural chars from both sides before
            # comparing: backticks appear in code spans (``repo://...``);
            # SOURCEREF_RE's exclusion set stops at ), ], , but not `.
            token_match = SOURCEREF_RE.match(line, idx)
            raw_end = idx
            while raw_end < len(line) and not line[raw_end].isspace():
                raw_end += 1
            raw_token = line[idx:raw_end].rstrip(".,;:!?`")
            match_clean = token_match.group().rstrip(".,;:!?`") if token_match else ""

            if match_clean != raw_token:
                errors.append(
                    f"{path_str}:{lineno}: malformed SourceRef citation: {raw_token!r}"
                )
            pos = raw_end

    return errors


def main(argv: list[str] | None = None) -> int:
    files = argv if argv is not None else sys.argv[1:]
    all_errors: list[str] = []
    for f in files:
        # Only process markdown files.
        if not f.endswith(".md"):
            continue
        all_errors.extend(_check_file(f))
    for err in all_errors:
        print(f"ERROR: {err}", file=sys.stderr)
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
