"""Tests for deterministic qmd preflight checks."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
import unittest

from scripts.kb import qmd_preflight


class QmdPreflightTests(unittest.TestCase):
    def test_preflight_passes_when_runtime_and_resources_are_available(self) -> None:
        report = qmd_preflight.run_preflight(
            repo_root=Path("/repo"),
            required_resources=(".qmd/index", "wiki"),
            which_fn=lambda _binary: "/usr/local/bin/qmd",
            path_exists_fn=lambda _path: True,
        )

        payload = report.to_dict()
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["reason_code"], "ok")
        self.assertEqual(
            [check["status"] for check in payload["checks"]],
            ["pass", "pass", "pass"],
        )

    def test_preflight_fails_when_qmd_runtime_is_unavailable(self) -> None:
        report = qmd_preflight.run_preflight(
            repo_root=Path("/repo"),
            required_resources=(".qmd/index",),
            which_fn=lambda _binary: None,
            path_exists_fn=lambda _path: True,
        )

        payload = report.to_dict()
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["reason_code"], "prereq_missing:qmd_runtime")
        self.assertEqual(payload["message"], "required runtime/tool unavailable: qmd")

    def test_preflight_fails_when_required_resource_is_unavailable(self) -> None:
        report = qmd_preflight.run_preflight(
            repo_root=Path("/repo"),
            required_resources=(".qmd/index",),
            which_fn=lambda _binary: "/usr/local/bin/qmd",
            path_exists_fn=lambda path: str(path) != "/repo/.qmd/index",
        )

        payload = report.to_dict()
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["reason_code"], "prereq_missing:qmd_index_resource")
        self.assertEqual(
            payload["message"],
            "required index/resource unavailable: .qmd/index",
        )

    def test_cli_returns_non_zero_and_reason_coded_json_on_failure(self) -> None:
        output = StringIO()
        exit_code = qmd_preflight.run_cli(
            argv=["--repo-root", "/repo", "--required-resource", ".qmd/index"],
            output_stream=output,
            which_fn=lambda _binary: None,
            path_exists_fn=lambda _path: True,
        )

        self.assertEqual(exit_code, 1)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["reason_code"], "prereq_missing:qmd_runtime")
        self.assertEqual(payload["message"], "required runtime/tool unavailable: qmd")

    def test_preflight_rejects_blank_qmd_binary(self) -> None:
        report = qmd_preflight.run_preflight(
            repo_root=Path("/repo"),
            qmd_binary="   ",
            which_fn=lambda _binary: "/usr/local/bin/qmd",
            path_exists_fn=lambda _path: True,
        )

        payload = report.to_dict()
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertEqual(payload["checks"][0]["reason_code"], "invalid_input")

    def test_preflight_rejects_required_resource_that_escapes_repo_root(self) -> None:
        report = qmd_preflight.run_preflight(
            repo_root=Path("/repo"),
            required_resources=("../outside",),
            which_fn=lambda _binary: "/usr/local/bin/qmd",
            path_exists_fn=lambda _path: True,
        )

        payload = report.to_dict()
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertEqual(payload["checks"][1]["target"], "../outside")

    def test_preflight_deduplicates_required_resources(self) -> None:
        report = qmd_preflight.run_preflight(
            repo_root=Path("/repo"),
            required_resources=(".qmd/index", "wiki", ".qmd/index", "wiki"),
            which_fn=lambda _binary: "/usr/local/bin/qmd",
            path_exists_fn=lambda _path: True,
        )

        payload = report.to_dict()
        self.assertEqual(
            [check["check_id"] for check in payload["checks"]],
            ["runtime:qmd", "resource:.qmd/index", "resource:wiki"],
        )

    def test_preflight_rejects_blank_required_resource(self) -> None:
        report = qmd_preflight.run_preflight(
            repo_root=Path("/repo"),
            required_resources=("",),
            which_fn=lambda _binary: "/usr/local/bin/qmd",
            path_exists_fn=lambda _path: True,
        )

        payload = report.to_dict()
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertEqual(payload["checks"][0]["check_id"], "resource:input")

    def test_preflight_rejects_whitespace_only_required_resource(self) -> None:
        report = qmd_preflight.run_preflight(
            repo_root=Path("/repo"),
            required_resources=("   ",),
            which_fn=lambda _binary: "/usr/local/bin/qmd",
            path_exists_fn=lambda _path: True,
        )

        payload = report.to_dict()
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["reason_code"], "invalid_input")


if __name__ == "__main__":
    unittest.main()
