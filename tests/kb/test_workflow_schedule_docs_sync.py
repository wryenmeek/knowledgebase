"""Test that every cron schedule in .github/workflows/*.yml is documented verbatim
in docs/mvp-runbook.md.

This prevents runbook schedule descriptions from drifting out of sync with the
actual cron strings in workflow YAML files. The raw cron string (e.g. '0 6 * * *')
must appear somewhere in the runbook — typically in the Trigger column of the
workflow table.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
RUNBOOK_PATH = REPO_ROOT / "docs" / "mvp-runbook.md"

# Matches a cron value in either single or double quotes (as used in workflow YAML).
_CRON_VALUE_RE = re.compile(r"""cron:\s+['"]([^'"]+)['"]""")


def _extract_cron_schedules(workflow_path: Path) -> list[str]:
    """Return all cron schedule strings from a workflow YAML file."""
    try:
        with open(workflow_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError:
        return []

    if not isinstance(data, dict):
        return []

    # YAML parses the 'on' key as the boolean True in some versions.
    on_section = data.get("on") or data.get(True) or {}
    if not isinstance(on_section, dict):
        return []

    schedule = on_section.get("schedule") or []
    crons: list[str] = []
    for item in schedule:
        if isinstance(item, dict) and "cron" in item:
            crons.append(str(item["cron"]))
    return crons


class TestWorkflowScheduleRunbookSync(unittest.TestCase):
    """Every cron schedule in workflows must appear verbatim in the runbook."""

    def test_cron_schedules_documented_in_runbook(self) -> None:
        if not WORKFLOWS_DIR.is_dir():
            self.skipTest(".github/workflows/ directory does not exist")
        if not RUNBOOK_PATH.exists():
            self.skipTest("docs/mvp-runbook.md does not exist")

        runbook_text = RUNBOOK_PATH.read_text(encoding="utf-8")

        for workflow_path in sorted(WORKFLOWS_DIR.glob("*.yml")):
            crons = _extract_cron_schedules(workflow_path)
            for cron in crons:
                with self.subTest(workflow=workflow_path.name, cron=cron):
                    self.assertIn(
                        cron,
                        runbook_text,
                        f"{workflow_path.name} has cron schedule '{cron}' that does not "
                        f"appear verbatim in docs/mvp-runbook.md. Update the runbook's "
                        f"Trigger column for this workflow to include the raw cron string.",
                    )


if __name__ == "__main__":
    unittest.main()
