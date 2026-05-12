"""Tests for deterministic document freshness analysis."""

from __future__ import annotations

import json
from io import StringIO
import subprocess
import sys

from tests.kb.harnesses import REPO_ROOT, RuntimeWorkspaceTestCase, load_module


FRESHNESS_SCRIPT_PATH = REPO_ROOT / "scripts" / "validation" / "check_doc_freshness.py"


class CheckDocFreshnessTests(RuntimeWorkspaceTestCase):
    RUNTIME_ROOT_NAME = ".runtime_doc_freshness"

    def setUp(self) -> None:
        super().setUp()
        self.module = load_module(
            f"check_doc_freshness_{self._testMethodName}",
            FRESHNESS_SCRIPT_PATH,
        )
        self.write_file("AGENTS.md", "# Test repo\n")

    def test_run_freshness_emits_stable_json_shape(self) -> None:
        self.write_file("wiki/reference.md", self._build_page("Reference", "2024-01-01T00:00:00Z"))

        report = self.module.run_freshness(
            repo_root=self.workspace,
            scope="wiki",
            as_of="2024-01-31",
            max_age_days=45,
        )

        payload = report.to_dict()
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["reason_code"], "ok")
        self.assertEqual(payload["scope"], "wiki")
        self.assertEqual(payload["as_of"], "2024-01-31")
        self.assertEqual(payload["max_age_days"], 45)
        self.assertEqual(payload["files"], [
            {
                "age_days": 30,
                "message": "document freshness within threshold",
                "path": "wiki/reference.md",
                "reason_code": "ok",
                "status": "pass",
                "updated_at": "2024-01-01",
            }
        ])

    def test_cli_runs_from_repo_root_without_writing_workspace(self) -> None:
        self.write_file("wiki/reference.md", self._build_page("Reference", "2024-01-01T00:00:00Z"))
        before = self.snapshot_workspace()

        completed = subprocess.run(
            [
                sys.executable,
                str(FRESHNESS_SCRIPT_PATH),
                "--scope",
                "wiki",
                "--as-of",
                "2024-01-31",
                "--max-age-days",
                "45",
            ],
            cwd=self.workspace,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["files"][0]["path"], "wiki/reference.md")
        self.assert_workspace_unchanged(before)

    def test_cli_returns_json_for_parser_level_invalid_input(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(FRESHNESS_SCRIPT_PATH),
                "--scope",
                "wiki",
                "--as-of",
                "2024-01-31",
                "--max-age-days",
                "nope",
            ],
            cwd=self.workspace,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertEqual(payload["scope"], "unknown")

    def test_cli_fails_closed_when_requested_path_escapes_repo_root(self) -> None:
        output = StringIO()

        exit_code = self.module.run_cli(
            argv=[
                "--scope",
                "wiki",
                "--path",
                "../outside.md",
                "--as-of",
                "2024-01-31",
                "--max-age-days",
                "45",
            ],
            output_stream=output,
            repo_root=self.workspace,
        )

        self.assertEqual(exit_code, 1)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertIn("escapes repository root", payload["message"])

    def test_cli_fails_closed_on_missing_updated_at_metadata(self) -> None:
        self.write_file("wiki/reference.md", "# Reference\n")
        output = StringIO()

        exit_code = self.module.run_cli(
            argv=["--scope", "wiki", "--as-of", "2024-01-31", "--max-age-days", "45"],
            output_stream=output,
            repo_root=self.workspace,
        )

        self.assertEqual(exit_code, 1)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["reason_code"], "missing_updated_at")
        self.assertEqual(payload["files"][0]["path"], "wiki/reference.md")

    def _build_page(self, title: str, updated_at: str) -> str:
        return self.build_process_page(title).replace(
            'updated_at: "2024-01-01T00:00:00Z"',
            f'updated_at: "{updated_at}"',
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
