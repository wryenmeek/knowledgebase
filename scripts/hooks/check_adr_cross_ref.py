#!/usr/bin/env python3
"""Pre-commit hook: when an ADR's ## Status line changes to include 'amended' or
'extended', require docs/decisions/README.md to also be staged.

This enforces the documentation cascade rule: every ADR status update that adds
an amendment or extension note must be accompanied by a README index update in
the same commit.

Only triggers when the status LINE ITSELF CHANGED — editing other parts of an
already-amended ADR does not require re-staging the README.
"""

from __future__ import annotations

import re
import subprocess
import sys


_STATUS_HEADING_RE = re.compile(r"^## Status\s*$", re.MULTILINE)


def _run_git(*args: str) -> tuple[int, str]:
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    return result.returncode, result.stdout


def _get_staged_content(path: str) -> str | None:
    """Read the staged (index) version of a file."""
    rc, out = _run_git("show", f":{path}")
    return out if rc == 0 else None


def _get_head_content(path: str) -> str | None:
    """Read the HEAD version of a file, or None if the file is new."""
    rc, out = _run_git("show", f"HEAD:{path}")
    return out if rc == 0 else None


def _extract_status_line(content: str) -> str | None:
    """Return first non-empty line after '## Status' heading."""
    match = _STATUS_HEADING_RE.search(content)
    if match is None:
        return None
    for line in content[match.end() :].splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _get_staged_paths() -> set[str]:
    """Return the set of paths that are staged (added, copied, or modified)."""
    rc, out = _run_git("diff", "--cached", "--name-only", "--diff-filter=ACM")
    return set(out.splitlines()) if rc == 0 else set()


def main(argv: list[str]) -> int:
    # pre-commit passes staged file paths as argv[1:]
    adr_files = [f for f in argv[1:] if re.match(r"docs/decisions/ADR-\d+-.*\.md$", f)]
    if not adr_files:
        return 0

    staged_paths = _get_staged_paths()
    readme_staged = "docs/decisions/README.md" in staged_paths

    failures: list[str] = []

    for adr_path in adr_files:
        staged_content = _get_staged_content(adr_path)
        if staged_content is None:
            continue

        new_status = _extract_status_line(staged_content)
        if new_status is None:
            continue

        # Compare to HEAD — only act when the status line itself changed.
        head_content = _get_head_content(adr_path)
        if head_content is not None:
            old_status = _extract_status_line(head_content)
            if old_status == new_status:
                continue  # Status line is unchanged; no cascade needed.

        # Status line changed (or file is new). Check if it signals amendment/extension.
        # Match all inflections: amended/amends/amending, extended/extends/extending,
        # plus the canonical past-participle forms ("extended by", "amended in-place").
        # The earlier formulation only checked "amended"/"extended" literals, which
        # silently bypassed cascade enforcement when an ADR used the active-voice
        # "extends ADR-NNN" wording (v-docs audit, 2026-06-20).
        new_status_lower = new_status.lower()
        if re.search(r"\b(amend|extend)(s|ed|ing)?\b", new_status_lower):
            if not readme_staged:
                failures.append(
                    f"  {adr_path}\n"
                    f"    status changed to: '{new_status}'\n"
                    f"    → stage docs/decisions/README.md with the updated status cell."
                )

    if failures:
        print(
            "ERROR: ADR status cascade — docs/decisions/README.md must be staged",
            file=sys.stderr,
        )
        for msg in failures:
            print(msg, file=sys.stderr)
        print(
            "\nWhen an ADR status changes to 'amended' or 'extended', update the README "
            "index row in the same commit.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
