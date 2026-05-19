"""Comprehensive SHA-pin regression test for all GitHub Actions workflow files.

Asserts that no workflow file contains floating action references (@vN, @main,
@latest) so that supply-chain pinning introduced in commit 0402d6c cannot
silently regress when contributors add new workflow steps.

Two complementary approaches are used:
  1. Denylist: flag known floating patterns (fast, human-readable error message).
  2. Allowlist: require every external uses: line to be a 40-hex-char SHA
     (catches unknown aliases like @HEAD, @release-x, or partial SHAs).
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest
import yaml


WORKFLOWS_DIR = Path(".github/workflows")

# Local/reusable workflow refs start with './' and don't need SHA pinning.
_LOCAL_REF_PATTERN = re.compile(r"^\s+uses:\s+\./")

# Matches any external uses: line that has an @ ref.
_EXTERNAL_USES_PATTERN = re.compile(r"^\s+uses:\s+\S+@")

# A pinned ref uses a 40-hex-char SHA (optionally followed by a space and comment).
_PINNED_REF_PATTERN = re.compile(
    r"^\s+uses:\s+\S+@[0-9a-f]{40}",
    re.MULTILINE,
)

# Known floating patterns — word-boundary anchor (\b) so trailing comments
# like `@v4  # update later` do NOT escape detection.
_FLOATING_REF_PATTERN = re.compile(
    r"^\s+uses:\s+\S+@(?:main|master|latest|v\d[\w.]*)\b",
    re.MULTILINE,
)


class WorkflowShaPinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow_files = sorted(WORKFLOWS_DIR.glob("*.yml"))
        assert cls.workflow_files, f"No workflow files found in {WORKFLOWS_DIR}"

    def test_no_floating_action_refs(self) -> None:
        """No workflow file may use a known floating action ref (@vN, @main, @latest).

        Supply-chain attacks exploit floating refs to inject malicious code via
        a tag move. All third-party action refs must be pinned to a full SHA.

        The \\b word boundary ensures refs like `@v4  # TODO: pin` are still caught
        even when a trailing comment follows the version token.
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

    def test_all_external_uses_are_sha_pinned(self) -> None:
        """Every external uses: line must reference a full 40-hex-character SHA.

        This allowlist approach catches aliases not covered by the denylist:
        @HEAD, @release-2026, partial SHAs (abc1234), custom tags, etc.
        Any uses: line with an @ ref that is NOT a 40-char SHA fails.
        """
        for wf_path in self.workflow_files:
            with self.subTest(workflow=wf_path.name):
                text = wf_path.read_text(encoding="utf-8")
                for lineno, line in enumerate(text.splitlines(), start=1):
                    if not _EXTERNAL_USES_PATTERN.match(line):
                        continue
                    if _LOCAL_REF_PATTERN.match(line):
                        continue
                    if not _PINNED_REF_PATTERN.match(line):
                        self.fail(
                            f"{wf_path.name}:{lineno} — action ref is not SHA-pinned: "
                            f"{line.strip()!r}\n"
                            f"Pin to a full 40-char SHA: "
                            f"  uses: owner/action@<40-hex-sha>  # vX"
                        )

    def test_pinned_refs_have_version_comments(self) -> None:
        """SHA-pinned refs should carry a # vX comment for human readability.

        This is a soft check — fails only when a pinned ref has no comment at
        all, since uncommented SHAs are opaque to reviewers.
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

    def test_pages_deploy_token_not_inlined_in_run_blocks(self) -> None:
        """pages.yml must not inline ${{ secrets.* }} in run: shell blocks.

        Passing a token inline in a shell command exposes it in argv
        (visible in /proc/<pid>/cmdline) and git diagnostics. The fix routes
        it via DEPLOY_TOKEN env var, expanded by the shell as ${DEPLOY_TOKEN}.

        Uses YAML parse to accurately scope the check to run: values only
        (avoids false-matches on env: blocks or step metadata).
        """
        text = Path(".github/workflows/pages.yml").read_text(encoding="utf-8")
        workflow = yaml.safe_load(text)
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                run_val = step.get("run", "")
                if run_val:
                    self.assertNotIn(
                        "${{ secrets.GITHUB_TOKEN }}",
                        str(run_val),
                        "pages.yml must not inline ${{ secrets.GITHUB_TOKEN }} in a run: block — use DEPLOY_TOKEN env var",
                    )
        # Positive assertions: the safe pattern must be present.
        self.assertIn(
            "DEPLOY_TOKEN: ${{ secrets.GITHUB_TOKEN }}",
            text,
            "pages.yml must declare DEPLOY_TOKEN in an env: block",
        )
        self.assertIn(
            "${DEPLOY_TOKEN}",
            text,
            "pages.yml must reference DEPLOY_TOKEN as a shell variable (not an expression)",
        )


if __name__ == "__main__":
    unittest.main()
