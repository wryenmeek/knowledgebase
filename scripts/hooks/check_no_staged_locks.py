"""Pre-commit hook: reject staged governance lock files.

Pre-commit passes filenames as positional arguments. The hook exits non-zero
if any staged file's basename matches a known governance lock file.

Staged deletions (removing a lock) are permitted — pre-commit strips the
status prefix before passing filenames, so a deleted file still appears in
argv. The hook only checks the basename, not whether the file exists.
"""

from __future__ import annotations

import sys

from scripts.kb.contracts import GOVERNANCE_LOCK_FILES


def main(argv: list[str] | None = None) -> int:
    files = argv if argv is not None else sys.argv[1:]
    failures: list[str] = []
    for f in files:
        # Extract basename without importing os — avoids any path-manipulation risk.
        basename = f.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if basename in GOVERNANCE_LOCK_FILES:
            failures.append(f)
    if failures:
        for f in failures:
            print(f"ERROR: Governance lock file must not be staged: {f}", file=sys.stderr)
        print(
            "Hint: lock files should never be committed. Add them to .gitignore.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
