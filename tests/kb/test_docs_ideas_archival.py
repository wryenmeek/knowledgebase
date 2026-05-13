"""Tests that docs/ideas/ archival stubs are structurally valid.

When a completed docs/ideas/ document is archived to raw/inbox/ for wiki
source intake, a minimal stub is left behind.  This test validates:
  - every stub with an archive pointer has a ``Status: Implemented`` line,
  - the pointed-to file exists in raw/inbox/ (awaiting ingest) OR has already
    been ingested to wiki/sources/ (post-ingest state).

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
WIKI_SOURCES_DIR = REPO_ROOT / "wiki" / "sources"

# Pattern that matches the archive pointer in a stub.
_ARCHIVE_PTR_RE = re.compile(
    r"Archived to `(raw/inbox/[^`]+)`",
)

# Matches terminal "Implemented" but NOT "Implemented (Phase N)".
_IMPLEMENTED_RE = re.compile(
    r"\*\*Status:\*\*\s+Implemented(?!\s*\()",
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

                # Target file must exist — either still in raw/inbox/ (pre-ingest)
                # or already moved to wiki/sources/ (post-ingest).
                target_inbox = REPO_ROOT / rel_target
                # Derive the wiki/sources counterpart (same filename).
                ingested = WIKI_SOURCES_DIR / Path(rel_target).name
                self.assertTrue(
                    target_inbox.exists() or ingested.exists(),
                    f"{md_file.name}: archive target not found at {rel_target} "
                    f"or post-ingest at wiki/sources/{Path(rel_target).name}",
                )

                # If still in inbox, verify it stays inside raw/inbox/.
                if target_inbox.exists():
                    self.assertTrue(
                        target_inbox.resolve().is_relative_to(INBOX_DIR.resolve()),
                        f"{md_file.name}: archive target escapes raw/inbox/: {rel_target}",
                    )

    def test_implemented_docs_must_be_stubs(self) -> None:
        """A doc with terminal 'Status: Implemented' must have an archive pointer (i.e. be a stub)."""
        if not IDEAS_DIR.is_dir():
            self.skipTest("docs/ideas/ directory does not exist")

        for md_file in sorted(IDEAS_DIR.glob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            if not _IMPLEMENTED_RE.search(text):
                continue

            with self.subTest(doc=md_file.name):
                self.assertIsNotNone(
                    _ARCHIVE_PTR_RE.search(text),
                    f"{md_file.name} has 'Status: Implemented' but no archive "
                    f"pointer — archive to raw/inbox/ and leave a stub "
                    f"(see copilot-instructions.md § docs/ideas/ archival)",
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


class TestDocsIdeasStatusField(unittest.TestCase):
    """Every docs/ideas/*.md must declare a **Status:** field.

    The docs/ideas/ lifecycle requires every document to carry an explicit
    status so agents and reviewers can determine what work is in progress,
    complete, or deferred without reading the full document body.

    Allowed values: Proposed, In Progress, Implemented, Implemented (Phase N).
    See copilot-instructions.md § docs/ideas/ status lifecycle.
    """

    _STATUS_RE = re.compile(r"\*\*Status:\*\*")
    _ALLOWED_STATUSES_RE = re.compile(
        r"\*\*Status:\*\*\s+"
        r"(Proposed|In Progress|Implemented(?:\s+\(Phase \d+\))?(?:\s+—[^*\n]+)?)"
    )

    def test_every_ideas_doc_has_status_field(self) -> None:
        if not IDEAS_DIR.is_dir():
            self.skipTest("docs/ideas/ directory does not exist")

        for md_file in sorted(IDEAS_DIR.glob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            with self.subTest(doc=md_file.name):
                self.assertRegex(
                    text,
                    self._STATUS_RE,
                    f"{md_file.name}: missing '**Status:**' field. "
                    f"Add a status line near the top of the document. "
                    f"Allowed values: Proposed, In Progress, Implemented, "
                    f"Implemented (Phase N). "
                    f"See copilot-instructions.md § docs/ideas/ status lifecycle.",
                )

    def test_status_field_uses_allowed_values(self) -> None:
        if not IDEAS_DIR.is_dir():
            self.skipTest("docs/ideas/ directory does not exist")

        for md_file in sorted(IDEAS_DIR.glob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            if not self._STATUS_RE.search(text):
                continue  # Missing status handled by test above

            with self.subTest(doc=md_file.name):
                self.assertRegex(
                    text,
                    self._ALLOWED_STATUSES_RE,
                    f"{md_file.name}: **Status:** field uses an unrecognized value. "
                    f"Allowed values: Proposed, In Progress, Implemented, "
                    f"Implemented (Phase N) (optionally followed by ' — <detail>'). "
                    f"See copilot-instructions.md § docs/ideas/ status lifecycle.",
                )
