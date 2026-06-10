"""Tests for the audit-knowledgebase-workspace read-only scaffold."""

from __future__ import annotations

from contextlib import ExitStack
import io
from pathlib import Path
from unittest import TestCase
import unittest
from unittest.mock import patch

from tests.kb.harnesses import load_module


REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_WORKSPACE_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "audit-knowledgebase-workspace"
    / "logic"
    / "audit_workspace.py"
)


class AuditWorkspaceScaffoldTests(TestCase):
    def _module(self):
        return load_module("audit_workspace", AUDIT_WORKSPACE_PATH)

    def _audit_with_write_guards(self, module, *, mode: str):
        guarded_calls = (
            "builtins.open",
            "pathlib.Path.open",
            "pathlib.Path.write_text",
            "pathlib.Path.write_bytes",
            "pathlib.Path.touch",
            "pathlib.Path.mkdir",
            "pathlib.Path.unlink",
            "pathlib.Path.rename",
            "pathlib.Path.replace",
            "os.makedirs",
            "os.remove",
            "os.unlink",
            "os.rename",
            "os.replace",
            "shutil.copyfile",
            "shutil.move",
            "subprocess.run",
        )
        with ExitStack() as stack:
            mocks = [stack.enter_context(patch(call)) for call in guarded_calls]
            result = module.audit(repo_root=REPO_ROOT, mode=mode)
            for mocked_call in mocks:
                mocked_call.assert_not_called()
            return result

    def test_improve_scaffold_returns_empty_findings_and_zero_writes(self) -> None:
        module = self._module()
        result = self._audit_with_write_guards(module, mode="improve")

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.items, ())
        self.assertEqual(result.summary["findings"], [])
        self.assertEqual(result.summary["finding_count"], 0)
        self.assertEqual(result.summary["writes_attempted"], 0)
        self.assertTrue(result.summary["read_only"])

    def test_default_compatibility_mode_is_read_only_and_empty(self) -> None:
        module = self._module()
        result = self._audit_with_write_guards(module, mode="default")

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.reason_code, "ok")
        self.assertIn("compatibility scaffold", result.message)
        self.assertEqual(result.summary["findings"], [])
        self.assertEqual(result.summary["writes_attempted"], 0)
        self.assertFalse(result.summary["structural_lint_executed"])
        self.assertTrue(result.path_rules["read_only"])
        self.assertTrue(result.path_rules["writes_forbidden"])

    def test_path_rules_cover_declared_read_only_scope(self) -> None:
        module = self._module()
        result = module.audit(repo_root=REPO_ROOT, mode="default")

        self.assertGreaterEqual(
            set(result.path_rules["allowed_roots"]),
            {
                ".github/copilot-instructions.md",
                ".github/agents",
                ".github/prompts",
                ".github/skills",
                ".github/hooks",
                "AGENTS.md",
                "tests/kb",
            },
        )

    def test_non_none_approval_is_rejected(self) -> None:
        module = self._module()
        result = module.audit(repo_root=REPO_ROOT, mode="improve", approval="approved")
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "invalid_input")

        output = io.StringIO()
        exit_code = module.run_cli(
            ["--repo-root", str(REPO_ROOT), "--mode", "improve", "--approval", "approved"],
            output_stream=output,
        )

        self.assertEqual(exit_code, 1)
        self.assertIn('"reason_code": "invalid_input"', output.getvalue())

    def test_cli_emits_empty_findings_json(self) -> None:
        module = self._module()
        output = io.StringIO()
        exit_code = module.run_cli(
            ["--repo-root", str(REPO_ROOT), "--mode", "improve"],
            output_stream=output,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn('"findings": []', output.getvalue())
        self.assertIn('"writes_attempted": 0', output.getvalue())

    def test_dry_run_flag_is_not_a_cli_argument(self) -> None:
        """Regression: gh PR #218 review removed the always-True --dry-run flag.

        The scaffold is unconditionally read-only; exposing a CLI flag that
        cannot be disabled was misleading. Argparse must reject --dry-run.
        """
        module = self._module()
        output = io.StringIO()
        exit_code = module.run_cli(
            ["--repo-root", str(REPO_ROOT), "--mode", "improve", "--dry-run"],
            output_stream=output,
        )
        self.assertNotEqual(exit_code, 0)

    def test_dry_run_kwarg_is_not_accepted_by_audit(self) -> None:
        """Regression: gh PR #218 review removed the always-True dry_run kwarg."""
        module = self._module()
        with self.assertRaises(TypeError):
            module.audit(repo_root=REPO_ROOT, mode="improve", dry_run=True)


if __name__ == "__main__":
    unittest.main()
