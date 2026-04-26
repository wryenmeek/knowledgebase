"""Pre-commit hook: validate .github/hooks/hooks.json structure.

Pre-commit passes filenames as positional arguments. For each file:
- Checks valid JSON syntax
- Checks required top-level 'hooks' key
- Checks all four required event keys: SessionStart, PreToolUse, PostToolUse, Stop
- Checks each hook entry has a 'command' field
- Checks all referenced shell script paths resolve to real files

Exits non-zero if any file fails validation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.kb.github_customizations_graph import validate_hooks_json

# Repo root is three levels up from scripts/hooks/check_hooks_json.py
_REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    files = argv if argv is not None else sys.argv[1:]
    all_errors: list[str] = []
    for f in files:
        errors = validate_hooks_json(Path(f), _REPO_ROOT)
        all_errors.extend(errors)
    for err in all_errors:
        print(f"ERROR: {err}", file=sys.stderr)
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
