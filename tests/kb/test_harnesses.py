"""Tests for shared knowledgebase test harness helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tests.kb.harnesses import HarnessAssertionsTestCase, RuntimeWorkspaceTestCase


class HarnessAssertionsTests(HarnessAssertionsTestCase):
    def test_wrapper_routing_normalizes_tuple_records(self) -> None:
        self.assert_wrapper_routing(
            [(["python3", "scripts/kb/lint_wiki.py"], Path("/repo"), True)],
            [["python3", "scripts/kb/lint_wiki.py"]],
        )

    def test_boundary_decision_checks_reason_code(self) -> None:
        self.assert_boundary_decision(
            SimpleNamespace(allowed=False, reason_code="path_not_allowlisted"),
            allowed=False,
            reason_code="path_not_allowlisted",
        )


class RuntimeWorkspaceHarnessTests(RuntimeWorkspaceTestCase):
    RUNTIME_ROOT_NAME = ".runtime_harnesses"

    def test_append_only_accepts_prefix_preserving_growth(self) -> None:
        log_path = self.write_file("wiki/log.md", "before\n")

        log_path.write_text("before\nafter\n", encoding="utf-8")

        self.assert_append_only(log_path, "before\n", expected_suffix="after\n")

    def test_workspace_unchanged_detects_unexpected_writes(self) -> None:
        self.write_file("wiki/index.md", "index\n")
        before = self.snapshot_workspace()
        self.write_file("wiki/log.md", "new entry\n")

        with self.assertRaises(AssertionError):
            self.assert_workspace_unchanged(before)


if __name__ == "__main__":
    import unittest

    unittest.main()
