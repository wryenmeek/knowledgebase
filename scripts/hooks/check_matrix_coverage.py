"""Pre-commit hook: write-surface matrix lint.

Checks that every *newly added* Python file under ``scripts/**`` or
``.github/skills/**/logic/**`` has a corresponding row in the AGENTS.md
write-surface matrix.

Design notes
------------
- Only newly added files are checked. Modifying an existing file that isn't
  covered is grandfathered — the matrix is a forward-looking contract.
- Path sanitization via ``normalize_repo_relative_path()`` guards against colon
  characters before git subprocess calls (git mis-parses colons in refspecs).
- A ``git rev-parse --verify HEAD`` guard prevents crashes on initial commits
  or orphan branches where HEAD does not exist.
- Surface patterns are parsed from ``AGENTS.md`` using ``agents_matrix_utils``.
  This avoids a separate parser and stays in sync automatically.
"""

from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import Path

# Repo root is 3 levels up: scripts/hooks/check_matrix_coverage.py
_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENTS_MD = _REPO_ROOT / "AGENTS.md"

# Patterns of files that must be covered by the write-surface matrix.
_COVERED_PATTERNS = [
    "scripts/**/*.py",
    ".github/skills/**/logic/**",
]


def _is_covered(repo_rel: str, matrix_surfaces: set[str]) -> bool:
    """Return True if *repo_rel* matches any declared surface pattern."""
    for surface in matrix_surfaces:
        if fnmatch.fnmatch(repo_rel, surface):
            return True
    return False


def _has_head() -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        capture_output=True,
        cwd=_REPO_ROOT,
    )
    return result.returncode == 0


def _is_new_file(repo_rel: str) -> bool:
    """Return True if *repo_rel* does not exist in HEAD (i.e., newly added)."""
    result = subprocess.run(
        ["git", "cat-file", "-e", f"HEAD:{repo_rel}"],
        capture_output=True,
        cwd=_REPO_ROOT,
    )
    return result.returncode != 0


def _normalize(path_str: str) -> str | None:
    """Normalize path to repo-relative POSIX form; return None if unsafe."""
    # Reject colons — git mis-parses colons in refspecs.
    if ":" in path_str:
        return None
    try:
        from scripts.kb import path_utils
        return path_utils.normalize_repo_relative_path(path_str)
    except Exception:
        # Fallback: use raw posix path relative to repo root.
        try:
            p = Path(path_str).resolve()
            return str(p.relative_to(_REPO_ROOT)).replace("\\", "/")
        except ValueError:
            return None


def main(argv: list[str] | None = None) -> int:
    files = argv if argv is not None else sys.argv[1:]

    if not files:
        return 0

    # Load matrix surfaces from AGENTS.md.
    try:
        from scripts.kb.agents_matrix_utils import parse_matrix_surfaces
        matrix_surfaces = parse_matrix_surfaces(_AGENTS_MD)
    except Exception as exc:
        print(f"ERROR: could not parse AGENTS.md matrix: {exc}", file=sys.stderr)
        return 1

    has_head = _has_head()
    errors: list[str] = []

    for f in files:
        repo_rel = _normalize(f)
        if repo_rel is None:
            print(f"WARNING: skipping unsafe path: {f!r}", file=sys.stderr)
            continue

        # Check if file matches a pattern that requires coverage.
        needs_coverage = any(fnmatch.fnmatch(repo_rel, pat) for pat in _COVERED_PATTERNS)
        if not needs_coverage:
            continue

        # Check if file is newly added.
        if has_head and not _is_new_file(repo_rel):
            continue

        # File is new and requires coverage — check matrix.
        if not _is_covered(repo_rel, matrix_surfaces):
            errors.append(
                f"{repo_rel}: newly added file has no write-surface matrix row in AGENTS.md. "
                f"Add a row for this surface before merging."
            )

    for err in errors:
        print(f"ERROR: {err}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
