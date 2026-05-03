"""Tests that cross-document index tables stay complete.

T1 — ADR README completeness: every ``docs/decisions/ADR-*.md`` file must
have a corresponding row in ``docs/decisions/README.md``.

T2 — Runbook workflow completeness: every ``.github/workflows/*.yml`` file
must be mentioned in ``docs/mvp-runbook.md``.

These enforce the "Documentation cascades" contract documented in
``.github/copilot-instructions.md``.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestADRIndexCompleteness(unittest.TestCase):
    """Every ADR file must have a row in the ADR README index."""

    def test_all_adr_files_listed_in_readme(self) -> None:
        decisions_dir = REPO_ROOT / "docs" / "decisions"
        readme = decisions_dir / "README.md"
        if not readme.is_file():
            self.skipTest("docs/decisions/README.md does not exist")

        adr_files = sorted(decisions_dir.glob("ADR-*.md"))
        if not adr_files:
            self.skipTest("No ADR files found")

        readme_text = readme.read_text(encoding="utf-8")

        for adr_file in adr_files:
            with self.subTest(adr=adr_file.name):
                self.assertIn(
                    adr_file.name,
                    readme_text,
                    f"{adr_file.name} is not referenced in docs/decisions/README.md",
                )


class TestRunbookWorkflowCompleteness(unittest.TestCase):
    """Every workflow YAML must be mentioned in the runbook."""

    def test_all_workflows_listed_in_runbook(self) -> None:
        workflows_dir = REPO_ROOT / ".github" / "workflows"
        runbook = REPO_ROOT / "docs" / "mvp-runbook.md"
        if not runbook.is_file():
            self.skipTest("docs/mvp-runbook.md does not exist")

        workflow_files = sorted(workflows_dir.glob("*.yml"))
        if not workflow_files:
            self.skipTest("No workflow files found")

        runbook_text = runbook.read_text(encoding="utf-8")

        for wf_file in workflow_files:
            with self.subTest(workflow=wf_file.name):
                self.assertIn(
                    wf_file.name,
                    runbook_text,
                    f"{wf_file.name} is not documented in docs/mvp-runbook.md",
                )
