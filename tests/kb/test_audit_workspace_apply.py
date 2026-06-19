"""Tests for audit-workspace apply-mode write target allowlisting."""

from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts.kb import contracts, write_utils
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

    def test_null_byte_in_path_returns_path_not_allowlisted(self) -> None:
        target_path = ".github/hooks/bad\x00hook.py"

        decision = self.module.validate_apply_target_path(
            self.workspace_root,
            target_path,
        )
        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            apply_targets=(target_path,),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "outside_allowlist")
        self.assertIn("ASCII control character", decision.message)
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "path_not_allowlisted")
        self.assertEqual(result.items[0]["path"], target_path)
        self.assertEqual(result.items[0]["reason_code"], "outside_allowlist")
        self.assertIn("ASCII control character", result.items[0]["message"])
        self.assertEqual(result.summary["writes_attempted"], 0)

    def test_control_character_in_path_returns_path_not_allowlisted(self) -> None:
        for control_character in ("\n", "\r", "\t", "\x7f"):
            target_path = f".github/hooks/bad{control_character}hook.py"
            with self.subTest(control_character=repr(control_character)):
                decision = self.module.validate_apply_target_path(
                    self.workspace_root,
                    target_path,
                )
                result = self.module.audit(
                    repo_root=self.workspace_root,
                    mode="apply",
                    apply_targets=(target_path,),
                )

                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason_code, "outside_allowlist")
                self.assertIn("ASCII control character", decision.message)
                self.assertEqual(result.status, "fail")
                self.assertEqual(result.reason_code, "path_not_allowlisted")
                self.assertEqual(result.items[0]["path"], target_path)
                self.assertEqual(result.items[0]["reason_code"], "outside_allowlist")
                self.assertIn("ASCII control character", result.items[0]["message"])
                self.assertEqual(result.summary["writes_attempted"], 0)

    def test_control_char_target_does_not_acquire_lock(self) -> None:
        target_path = ".github/hooks/bad\nhook.py"

        with patch.object(
            self.module.write_utils,
            "exclusive_write_lock",
            side_effect=AssertionError("control-char targets must fail before lock"),
        ) as lock_mock:
            result = self.module.audit(
                repo_root=self.workspace_root,
                mode="apply",
                approval="approved",
                apply_targets=(target_path,),
            )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "path_not_allowlisted")
        self.assertTrue(result.lock_required)
        self.assertEqual(result.lock_path, contracts.CUSTOMIZATIONS_LOCK_PATH)
        self.assertFalse(result.summary["lock_acquired"])
        self.assertEqual(result.summary["writes_attempted"], 0)
        lock_mock.assert_not_called()

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

    def test_approved_apply_acquires_customizations_lock_before_validation(self) -> None:
        observed_lock_states: list[bool] = []
        original_validate = self.module.validate_apply_target_path

        def observing_validate(repo_root, target_path, *, operation=None):
            observed_lock_states.append(
                write_utils.is_write_lock_held(
                    repo_root,
                    contracts.CUSTOMIZATIONS_LOCK_PATH,
                )
            )
            return original_validate(repo_root, target_path, operation=operation)

        with patch.object(
            self.module,
            "validate_apply_target_path",
            side_effect=observing_validate,
        ):
            result = self.module.audit(
                repo_root=self.workspace_root,
                mode="apply",
                approval="approved",
                apply_targets=("AGENTS.md",),
            )

        self.assertEqual(result.status, "pass")
        self.assertEqual(observed_lock_states, [True])

    def test_unapproved_apply_validates_without_customizations_lock(self) -> None:
        observed_lock_states: list[bool] = []
        original_validate = self.module.validate_apply_target_path

        def observing_validate(repo_root, target_path, *, operation=None):
            observed_lock_states.append(
                write_utils.is_write_lock_held(
                    repo_root,
                    contracts.CUSTOMIZATIONS_LOCK_PATH,
                )
            )
            return original_validate(repo_root, target_path, operation=operation)

        with patch.object(
            self.module,
            "validate_apply_target_path",
            side_effect=observing_validate,
        ):
            result = self.module.audit(
                repo_root=self.workspace_root,
                mode="apply",
                apply_targets=("AGENTS.md",),
            )

        self.assertEqual(result.status, "pass")
        self.assertEqual(observed_lock_states, [False])
        self.assertFalse(result.lock_required)
        self.assertIsNone(result.lock_path)

    def test_approved_apply_fails_before_customizations_lock_when_sibling_lock_held(
        self,
    ) -> None:
        for sibling_lock_path in (
            contracts.WRITE_LOCK_PATH,
            contracts.REJECTION_REGISTRY_LOCK_PATH,
        ):
            with self.subTest(sibling_lock_path=sibling_lock_path):
                with write_utils.exclusive_write_lock(
                    self.workspace_root,
                    lock_path=sibling_lock_path,
                ):
                    with patch.object(
                        self.module.write_utils,
                        "exclusive_write_lock",
                        side_effect=AssertionError(
                            "customizations lock must not be acquired"
                        ),
                    ):
                        result = self.module.audit(
                            repo_root=self.workspace_root,
                            mode="apply",
                            approval="approved",
                            apply_targets=("AGENTS.md",),
                        )

                self.assertEqual(result.status, "fail")
                self.assertEqual(result.reason_code, "lock_unavailable")
                self.assertTrue(result.lock_required)
                self.assertEqual(result.lock_path, contracts.CUSTOMIZATIONS_LOCK_PATH)
                self.assertEqual(result.summary["sibling_lock_held"], sibling_lock_path)
                self.assertFalse(result.summary["lock_acquired"])
                self.assertEqual(result.summary["write_targets_validated"], 0)
                self.assertFalse(
                    write_utils.is_write_lock_held(
                        self.workspace_root,
                        contracts.CUSTOMIZATIONS_LOCK_PATH,
                    )
                )

    def test_approved_apply_releases_customizations_lock_on_success(self) -> None:
        first = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            approval="approved",
            apply_targets=("AGENTS.md",),
        )
        second = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            approval="approved",
            apply_targets=("AGENTS.md",),
        )

        self.assertEqual(first.status, "pass")
        self.assertTrue(first.lock_required)
        self.assertEqual(first.lock_path, contracts.CUSTOMIZATIONS_LOCK_PATH)
        self.assertTrue(first.summary["lock_acquired"])
        self.assertEqual(second.status, "pass")
        self.assertFalse(
            write_utils.is_write_lock_held(
                self.workspace_root,
                contracts.CUSTOMIZATIONS_LOCK_PATH,
            )
        )

    def test_approved_apply_reclaims_stale_customizations_lock_file(self) -> None:
        stale_lock_path = self.workspace_root / contracts.CUSTOMIZATIONS_LOCK_PATH
        stale_lock_path.parent.mkdir(parents=True, exist_ok=True)
        stale_lock_path.write_text("stale owner metadata\n", encoding="utf-8")

        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            approval="approved",
            apply_targets=("AGENTS.md",),
        )

        self.assertEqual(result.status, "pass")
        self.assertTrue(result.summary["lock_acquired"])
        self.assertTrue(stale_lock_path.exists())
        self.assertFalse(
            write_utils.is_write_lock_held(
                self.workspace_root,
                contracts.CUSTOMIZATIONS_LOCK_PATH,
            )
        )

    def test_approved_apply_releases_customizations_lock_on_validation_failure(self) -> None:
        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            approval="approved",
            apply_targets=("wiki/log.md",),
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "path_not_allowlisted")
        self.assertFalse(
            write_utils.is_write_lock_held(
                self.workspace_root,
                contracts.CUSTOMIZATIONS_LOCK_PATH,
            )
        )

    def test_approved_apply_releases_customizations_lock_on_exception(self) -> None:
        with patch.object(
            self.module,
            "validate_apply_target_path",
            side_effect=RuntimeError("validation crashed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "validation crashed"):
                self.module.audit(
                    repo_root=self.workspace_root,
                    mode="apply",
                    approval="approved",
                    apply_targets=("AGENTS.md",),
                )

        self.assertFalse(
            write_utils.is_write_lock_held(
                self.workspace_root,
                contracts.CUSTOMIZATIONS_LOCK_PATH,
            )
        )

    def test_approved_apply_returns_lock_unavailable_when_customizations_lock_busy(self) -> None:
        with patch.object(
            self.module.write_utils,
            "exclusive_write_lock",
            side_effect=write_utils.LockUnavailableError(
                contracts.CUSTOMIZATIONS_LOCK_PATH
            ),
        ) as lock_mock:
            result = self.module.audit(
                repo_root=self.workspace_root,
                mode="apply",
                approval="approved",
                apply_targets=("AGENTS.md",),
            )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "lock_unavailable")
        self.assertTrue(result.lock_required)
        self.assertEqual(result.lock_path, contracts.CUSTOMIZATIONS_LOCK_PATH)
        self.assertIn(contracts.CUSTOMIZATIONS_LOCK_PATH, result.message)
        lock_mock.assert_called_once_with(
            self.workspace_root.resolve(),
            lock_path=contracts.CUSTOMIZATIONS_LOCK_PATH,
        )

    def test_approved_apply_cli_returns_lock_unavailable_when_live_lock_busy(self) -> None:
        with write_utils.exclusive_write_lock(
            self.workspace_root,
            lock_path=contracts.CUSTOMIZATIONS_LOCK_PATH,
        ):
            completed = subprocess.run(
                [
                    sys.executable,
                    str(AUDIT_WORKSPACE_PATH),
                    "--repo-root",
                    str(self.workspace_root),
                    "--mode",
                    "apply",
                    "--approval",
                    "approved",
                    "--apply-target",
                    "AGENTS.md",
                ],
                check=False,
                capture_output=True,
                cwd=REPO_ROOT,
                text=True,
            )

        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["reason_code"], "lock_unavailable")
        self.assertEqual(payload["lock_path"], contracts.CUSTOMIZATIONS_LOCK_PATH)
        self.assertTrue(payload["lock_required"])

    def test_approved_apply_cli_returns_lock_unavailable_when_live_sibling_lock_busy(
        self,
    ) -> None:
        for sibling_lock_path in (
            contracts.WRITE_LOCK_PATH,
            contracts.REJECTION_REGISTRY_LOCK_PATH,
        ):
            with self.subTest(sibling_lock_path=sibling_lock_path):
                with write_utils.exclusive_write_lock(
                    self.workspace_root,
                    lock_path=sibling_lock_path,
                ):
                    completed = subprocess.run(
                        [
                            sys.executable,
                            str(AUDIT_WORKSPACE_PATH),
                            "--repo-root",
                            str(self.workspace_root),
                            "--mode",
                            "apply",
                            "--approval",
                            "approved",
                            "--apply-target",
                            "AGENTS.md",
                        ],
                        check=False,
                        capture_output=True,
                        cwd=REPO_ROOT,
                        text=True,
                    )

                self.assertEqual(completed.returncode, 1)
                payload = json.loads(completed.stdout)
                self.assertEqual(payload["reason_code"], "lock_unavailable")
                self.assertEqual(
                    payload["summary"]["sibling_lock_held"],
                    sibling_lock_path,
                )
                self.assertEqual(payload["lock_path"], contracts.CUSTOMIZATIONS_LOCK_PATH)
                self.assertTrue(payload["lock_required"])

    def test_approved_apply_ignores_sibling_lock_deleted_before_probe_open(self) -> None:
        disappearing_lock_path = self.workspace_root / contracts.WRITE_LOCK_PATH
        disappearing_lock_path.parent.mkdir(parents=True, exist_ok=True)
        disappearing_lock_path.write_text("stale metadata\n", encoding="utf-8")
        original_open = self.module.os.open

        def deleting_open(path, flags, *args, **kwargs):
            if Path(path) == disappearing_lock_path:
                disappearing_lock_path.unlink()
                raise FileNotFoundError(path)
            return original_open(path, flags, *args, **kwargs)

        with patch.object(self.module.os, "open", side_effect=deleting_open):
            result = self.module.audit(
                repo_root=self.workspace_root,
                mode="apply",
                approval="approved",
                apply_targets=("AGENTS.md",),
            )

        self.assertEqual(result.status, "pass")
        self.assertTrue(result.summary["lock_acquired"])


if __name__ == "__main__":
    unittest.main()
