"""Parser-level syntax checks for GitHub workflow YAML files."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest


WORKFLOWS_DIR = Path(".github/workflows")


class WorkflowYamlSyntaxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(WORKFLOWS_DIR.exists(), f"Missing workflows directory: {WORKFLOWS_DIR}")

    @unittest.skipUnless(shutil.which("ruby"), "Ruby is required for YAML syntax validation")
    def test_all_workflows_are_parseable_yaml(self) -> None:
        workflow_files = sorted(str(path) for path in WORKFLOWS_DIR.glob("*.yml"))
        self.assertGreater(len(workflow_files), 0, "Expected at least one .yml workflow file")

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
        self.assertEqual(
            result.returncode,
            0,
            "Workflow YAML parse failed.\nSTDOUT:\n"
            f"{result.stdout}\nSTDERR:\n{result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
