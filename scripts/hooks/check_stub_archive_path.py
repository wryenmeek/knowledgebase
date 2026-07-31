#!/usr/bin/env python3
"""Pre-commit hook: validate that docs/ideas/ stubs with archive pointers reference
files that actually exist.

A stub is a docs/ideas/ document that has been archived to intake. It must contain
a line like: Archived to `raw/inbox/<filename>`

The referenced file must exist at:
- raw/inbox/<filename>  (pre-ingest state), OR
- wiki/sources/<filename>  (post-ingest state)

If neither exists, the stub's archive pointer is stale and must be corrected.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INBOX_DIR = REPO_ROOT / "raw" / "inbox"
WIKI_SOURCES_DIR = REPO_ROOT / "wiki" / "sources"

_ARCHIVE_PTR_RE = re.compile(r"Archived to `((raw/inbox|wiki/sources)/[^`]+)`")


def _get_staged_content(path: str) -> str | None:
    """Read the staged (index) version of a file."""
    result = subprocess.run(["git", "show", f":{path}"], capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


def main(argv: list[str]) -> int:
    stub_files = [
        f for f in argv[1:] if f.startswith("docs/ideas/") and f.endswith(".md")
    ]
    if not stub_files:
        return 0

    failures: list[str] = []

    for stub_path in stub_files:
        content = _get_staged_content(stub_path)
        if content is None:
            continue

        match = _ARCHIVE_PTR_RE.search(content)
        if match is None:
            continue  # Not a stub with an archive pointer.

        rel_target = match.group(1)
        filename = Path(rel_target).name

        target_inbox = REPO_ROOT / rel_target
        target_sources = WIKI_SOURCES_DIR / filename

        if not target_inbox.exists() and not target_sources.exists():
            failures.append(
                f"  {stub_path}: claims 'Archived to `{rel_target}`'\n"
                f"    but the file was not found at either:\n"
                f"    - {rel_target}  (raw/inbox/ pre-ingest)\n"
                f"    - wiki/sources/{filename}  (post-ingest)\n"
            )

    if failures:
        print(
            "ERROR: Stub archive pointer targets missing file:",
            file=sys.stderr,
        )
        for msg in failures:
            print(msg, file=sys.stderr)
        print(
            "\nFix: update the stub's archive pointer to match the actual file location "
            "(raw/inbox/<file> or wiki/sources/<file>), or archive the file first.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
