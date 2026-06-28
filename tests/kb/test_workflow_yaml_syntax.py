"""Parser-level syntax checks for GitHub workflow YAML files.

Also covers composite action manifests under ``.github/actions/<name>/action.yml``,
which carry the same YAML parse risk as workflow files. See
audit-knowledgebase-workspace report 2026-06-27 for the gap that
motivated extending the lint surface.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


WORKFLOWS_DIR = Path(".github/workflows")
ACTIONS_DIR = Path(".github/actions")


def _all_workflow_and_action_files() -> list[str]:
    files: list[Path] = list(WORKFLOWS_DIR.glob("*.yml"))
    if ACTIONS_DIR.is_dir():
        files.extend(ACTIONS_DIR.glob("**/action.yml"))
    return sorted(str(p) for p in files)


@pytest.mark.skipif(
    not shutil.which("ruby"), reason="Ruby is required for YAML syntax validation"
)
def test_all_workflows_are_parseable_yaml() -> None:
    assert WORKFLOWS_DIR.exists(), f"Missing workflows directory: {WORKFLOWS_DIR}"
    workflow_files = _all_workflow_and_action_files()
    assert len(workflow_files) > 0, (
        "Expected at least one workflow or action.yml file"
    )

    ruby_program = """
require "psych"
ARGV.each do |workflow_path|
  Psych.parse_file(workflow_path)
end
"""
    result = subprocess.run(
        ["ruby", "-e", ruby_program, *workflow_files],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "Workflow/action YAML parse failed.\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
