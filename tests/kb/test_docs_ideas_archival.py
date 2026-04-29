"""Tests that docs/ideas/ archival stubs are structurally valid.

When a completed docs/ideas/ document is archived to raw/inbox/ for wiki
source intake, a minimal stub is left behind.  This test validates:
  - every stub with an archive pointer has a ``Status: Implemented`` line,
  - the pointed-to file in raw/inbox/ actually exists.

See ``.github/copilot-instructions.md`` → ``docs/ideas/ archival to intake``
for the convention these tests enforce.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
IDEAS_DIR = REPO_ROOT / "docs" / "ideas"
INBOX_DIR = REPO_ROOT / "raw" / "inbox"

# Pattern that matches the archive pointer in a stub.
_ARCHIVE_PTR_RE = re.compile(
    r"Archived to `(raw/inbox/[^`]+)`",
)


class TestDocsIdeasArchival(unittest.TestCase):
    """Validate docs/ideas/ archival stubs."""

    def test_archival_stubs_are_valid(self) -> None:
        """Each stub with an archive pointer must have Status: Implemented and a valid target."""
        if not IDEAS_DIR.is_dir():
            self.skipTest("docs/ideas/ directory does not exist")

        stubs_found = 0
        for md_file in sorted(IDEAS_DIR.glob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            match = _ARCHIVE_PTR_RE.search(text)
            if match is None:
                continue

            stubs_found += 1
            rel_target = match.group(1)

            with self.subTest(stub=md_file.name):
                # Must contain Status: Implemented
                self.assertRegex(
                    text,
                    r"\*\*Status:\*\*\s+Implemented",
                    f"{md_file.name}: archival stub missing 'Status: Implemented' line",
                )

                # Target file must exist
                target = REPO_ROOT / rel_target
                self.assertTrue(
                    target.exists(),
                    f"{md_file.name}: archive target does not exist: {rel_target}",
                )

                # Target must be inside raw/inbox/ (path traversal guard)
                self.assertTrue(
                    target.resolve().is_relative_to(INBOX_DIR.resolve()),
                    f"{md_file.name}: archive target escapes raw/inbox/: {rel_target}",
                )

    def test_at_least_one_stub_exists(self) -> None:
        """Sanity check: at least one archival stub exists (guards against silent regex drift)."""
        if not IDEAS_DIR.is_dir():
            self.skipTest("docs/ideas/ directory does not exist")

        for md_file in IDEAS_DIR.glob("*.md"):
            text = md_file.read_text(encoding="utf-8")
            if _ARCHIVE_PTR_RE.search(text):
                return
        self.fail(
            "No archival stubs found in docs/ideas/ — if all stubs were removed, "
            "this test should also be removed."
        )
