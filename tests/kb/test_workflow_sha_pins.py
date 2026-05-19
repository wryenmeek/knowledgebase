"""Comprehensive SHA-pin regression test for all GitHub Actions workflow files.

Asserts that no workflow file contains floating action references (@vN, @main,
@latest) so that supply-chain pinning introduced in commit 0402d6c cannot
silently regress when contributors add new workflow steps.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest


WORKFLOWS_DIR = Path(".github/workflows")

# Patterns that indicate a floating (unpinned) action reference.
# A safe ref is a full 40-character hex SHA, e.g. actions/checkout@93cb6efe...
_FLOATING_REF_PATTERN = re.compile(
    r"^\s+uses:\s+\S+@(?:main|master|latest|v\d[\w.]*)$",
    re.MULTILINE,
)

# Local/reusable workflow refs start with './' and don't need SHA pinning.
_LOCAL_REF_PATTERN = re.compile(r"^\s+uses:\s+\./")

# A pinned ref uses a 40-hex-char SHA (optionally followed by a space and comment).
_PINNED_REF_PATTERN = re.compile(
    r"^\s+uses:\s+\S+@[0-9a-f]{40}",
    re.MULTILINE,
)

# SHA-pinned refs should carry a version comment for human readability.
_PINNED_WITH_COMMENT_PATTERN = re.compile(
    r"^\s+uses:\s+\S+@[0-9a-f]{40}\s+#",
    re.MULTILINE,
)


class WorkflowShaPinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow_files = sorted(WORKFLOWS_DIR.glob("*.yml"))
        assert cls.workflow_files, f"No workflow files found in {WORKFLOWS_DIR}"

    def test_no_floating_action_refs(self) -> None:
        """No workflow file may use a floating action ref (@vN, @main, @latest).

        Supply-chain attacks exploit floating refs to inject malicious code via
        a tag move. All third-party action refs must be pinned to a full SHA.
        """
        for wf_path in self.workflow_files:
            with self.subTest(workflow=wf_path.name):
                text = wf_path.read_text(encoding="utf-8")
                lines = text.splitlines()
                for lineno, line in enumerate(lines, start=1):
                    # Skip local/reusable workflow refs — they don't need SHA pinning.
                    if _LOCAL_REF_PATTERN.match(line):
                        continue
                    if _FLOATING_REF_PATTERN.match(line):
                        self.fail(
                            f"{wf_path.name}:{lineno} — floating action ref detected: "
                            f"{line.strip()!r}\n"
                            f"Pin to a full 40-char SHA: "
                            f"  uses: owner/action@<40-hex-sha>  # vX"
                        )

    def test_pinned_refs_have_version_comments(self) -> None:
        """SHA-pinned refs should carry a # vX comment for human readability.

        This is a soft check (warning-level) — fails only when a pinned ref
        has no comment at all, since uncommented SHAs are opaque to reviewers.
        """
        for wf_path in self.workflow_files:
            with self.subTest(workflow=wf_path.name):
                text = wf_path.read_text(encoding="utf-8")
                for lineno, line in enumerate(text.splitlines(), start=1):
                    if not _PINNED_REF_PATTERN.match(line):
                        continue
                    if _LOCAL_REF_PATTERN.match(line):
                        continue
                    self.assertRegex(
                        line,
                        r"@[0-9a-f]{40}\s+#",
                        f"{wf_path.name}:{lineno} — SHA-pinned ref missing version comment: "
                        f"{line.strip()!r}",
                    )


if __name__ == "__main__":
    unittest.main()
