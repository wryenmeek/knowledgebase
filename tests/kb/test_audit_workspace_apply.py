"""Tests for audit-workspace apply-mode write target allowlisting."""

from __future__ import annotations

import io
from pathlib import Path
import unittest

from tests.kb.harnesses import RuntimeWorkspaceTestCase, load_module


REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_WORKSPACE_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "audit-knowledgebase-workspace"
    / "logic"
    / "audit_workspace.py"
)


class AuditWorkspaceApplyAllowlistTests(RuntimeWorkspaceTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.module = load_module("audit_workspace_apply", AUDIT_WORKSPACE_PATH)
        self.write_file("AGENTS.md", "# AGENTS\n")
        self.write_file(".github/copilot-instructions.md", "# Copilot instructions\n")
        self.write_file(
            ".github/skills/audit-knowledgebase-workspace/SKILL.md",
            "# Audit Knowledgebase Workspace\n",
        )
        self.write_file(".github/skills/other-skill/SKILL.md", "# Other Skill\n")
        self.write_file(".github/hooks/hooks.json", "{}\n")
        self.write_file("wiki/log.md", "# Log\n")

    def test_apply_allows_declared_create_targets(self) -> None:
        for target_path in (
            ".github/instructions/new-scope.instructions.md",
            ".github/instructions/nested/new-scope.instructions.md",
            ".github/hooks/new-hook.py",
            ".github/hooks/nested/new-hook.py",
        ):
            with self.subTest(target_path=target_path):
                decision = self.module.validate_apply_target_path(
                    self.workspace_root,
                    target_path,
                )

                self.assertTrue(decision.allowed)
                self.assertEqual(decision.operation, "create")
                self.assertEqual(decision.reason_code, "ok")

    def test_apply_allows_declared_modify_targets(self) -> None:
        for target_path in (
            ".github/copilot-instructions.md",
            "AGENTS.md",
            ".github/skills/audit-knowledgebase-workspace/SKILL.md",
        ):
            with self.subTest(target_path=target_path):
                decision = self.module.validate_apply_target_path(
                    self.workspace_root,
                    target_path,
                )

                self.assertTrue(decision.allowed)
                self.assertEqual(decision.operation, "modify")
                self.assertEqual(decision.reason_code, "ok")

    def test_apply_rejects_outside_allowlist_via_surface_result(self) -> None:
        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            apply_targets=("wiki/log.md",),
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "path_not_allowlisted")
        self.assertEqual(result.items[0]["reason_code"], "outside_allowlist")
        self.assertEqual(result.items[0]["path"], "wiki/log.md")

    def test_apply_rejects_cross_skill_target_for_out_of_band_routing(self) -> None:
        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            apply_targets=(".github/skills/other-skill/SKILL.md",),
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "path_not_allowlisted")
        self.assertEqual(result.items[0]["reason_code"], "cross_skill_finding")

    def test_apply_rejects_existing_hook_registry_modification(self) -> None:
        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            apply_targets=(".github/hooks/hooks.json",),
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "path_not_allowlisted")
        self.assertEqual(result.items[0]["reason_code"], "outside_allowlist")

    def test_apply_rejects_instruction_create_without_instruction_suffix(self) -> None:
        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            apply_targets=(".github/instructions/new-scope.md",),
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "path_not_allowlisted")
        self.assertEqual(result.items[0]["reason_code"], "outside_allowlist")

    def test_apply_rejects_parent_directory_traversal(self) -> None:
        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            apply_targets=(".github/instructions/../copilot-instructions.md",),
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "path_not_allowlisted")

    def test_apply_rejects_symlink_components(self) -> None:
        real_dir = self.workspace_root / ".github" / "instructions" / "real"
        real_dir.mkdir(parents=True, exist_ok=True)
        symlink_dir = self.workspace_root / ".github" / "instructions" / "link"
        symlink_dir.symlink_to(real_dir, target_is_directory=True)

        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            apply_targets=(".github/instructions/link/new-scope.instructions.md",),
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "path_not_allowlisted")
        self.assertIn("symlink", result.items[0]["message"])

    def test_cli_apply_validates_caller_provided_targets(self) -> None:
        output = io.StringIO()
        exit_code = self.module.run_cli(
            [
                "--repo-root",
                str(self.workspace_root),
                "--mode",
                "apply",
                "--apply-target",
                "wiki/log.md",
            ],
            output_stream=output,
        )

        self.assertEqual(exit_code, 1)
        self.assertIn('"reason_code": "path_not_allowlisted"', output.getvalue())


if __name__ == "__main__":
    unittest.main()
