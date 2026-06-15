"""Adversarial QA gate for audit-workspace apply-mode composition."""

from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

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


class AuditWorkspaceApplyAdversarialTests(RuntimeWorkspaceTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.module = load_module(
            f"audit_workspace_apply_adversarial_{self._testMethodName}",
            AUDIT_WORKSPACE_PATH,
        )
        self.write_file("AGENTS.md", "# AGENTS\n")
        self.write_file(".github/copilot-instructions.md", "# Copilot instructions\n")
        self.write_file(
            ".github/skills/audit-knowledgebase-workspace/SKILL.md",
            "# Audit Knowledgebase Workspace\n",
        )
        self.write_file(".github/skills/other-skill/SKILL.md", "# Other Skill\n")
        self.write_file(".github/hooks/hooks.json", "{}\n")
        self.write_file("wiki/log.md", "# Log\n")

    def test_mixed_allowed_and_disallowed_targets_fail_entire_apply_batch(self) -> None:
        before_agents = (self.workspace_root / "AGENTS.md").read_text(encoding="utf-8")
        before_log = (self.workspace_root / "wiki" / "log.md").read_text(encoding="utf-8")

        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            approval="approved",
            apply_targets=("AGENTS.md", "wiki/log.md"),
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "path_not_allowlisted")
        self.assertEqual(result.summary["write_targets_validated"], 2)
        self.assertEqual(result.summary["write_targets_allowed"], 1)
        self.assertEqual(result.summary["write_targets_rejected"], 1)
        self.assertEqual(result.summary["writes_attempted"], 0)
        self.assertEqual(result.summary["writes_performed"], 0)
        self.assertTrue(result.summary["lock_acquired"])
        items_by_path = {item["path"]: item for item in result.items}
        self.assertEqual(items_by_path["AGENTS.md"]["status"], "pass")
        self.assertEqual(items_by_path["wiki/log.md"]["status"], "fail")
        self.assertEqual(
            items_by_path["wiki/log.md"]["reason_code"],
            "outside_allowlist",
        )
        self.assertFalse(
            write_utils.is_write_lock_held(
                self.workspace_root,
                contracts.CUSTOMIZATIONS_LOCK_PATH,
            )
        )
        self.assertEqual(
            (self.workspace_root / "AGENTS.md").read_text(encoding="utf-8"),
            before_agents,
        )
        self.assertEqual(
            (self.workspace_root / "wiki" / "log.md").read_text(encoding="utf-8"),
            before_log,
        )

    def test_unapproved_apply_validates_targets_without_acquiring_lock(self) -> None:
        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            approval="none",
            apply_targets=("AGENTS.md", "wiki/log.md"),
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "path_not_allowlisted")
        self.assertFalse(result.lock_required)
        self.assertIsNone(result.lock_path)
        self.assertFalse(result.summary["lock_acquired"])
        self.assertEqual(result.summary["write_targets_validated"], 2)
        self.assertEqual(result.summary["write_targets_allowed"], 1)
        self.assertEqual(result.summary["write_targets_rejected"], 1)
        self.assertFalse(
            (self.workspace_root / contracts.CUSTOMIZATIONS_LOCK_PATH).exists()
        )

    def test_approved_apply_with_empty_target_list_is_zero_write_noop(self) -> None:
        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            approval="approved",
            apply_targets=(),
        )

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.reason_code, "ok")
        self.assertTrue(result.lock_required)
        self.assertTrue(result.summary["lock_acquired"])
        self.assertEqual(result.summary["write_targets_validated"], 0)
        self.assertEqual(result.summary["writes_attempted"], 0)
        self.assertEqual(result.summary["writes_performed"], 0)
        self.assertFalse(
            write_utils.is_write_lock_held(
                self.workspace_root,
                contracts.CUSTOMIZATIONS_LOCK_PATH,
            )
        )

    def test_unapproved_apply_with_empty_target_list_is_no_lock_noop(self) -> None:
        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            approval="none",
            apply_targets=(),
        )

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.reason_code, "ok")
        self.assertFalse(result.lock_required)
        self.assertIsNone(result.lock_path)
        self.assertFalse(result.summary["lock_acquired"])
        self.assertEqual(result.summary["write_targets_validated"], 0)
        self.assertEqual(result.summary["writes_attempted"], 0)
        self.assertFalse(
            (self.workspace_root / contracts.CUSTOMIZATIONS_LOCK_PATH).exists()
        )

    def test_parent_directory_traversal_target_is_rejected_without_lock(self) -> None:
        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            approval="none",
            apply_targets=("../../etc/passwd",),
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "path_not_allowlisted")
        self.assertEqual(result.items[0]["path"], "../../etc/passwd")
        self.assertEqual(result.items[0]["reason_code"], "outside_allowlist")
        self.assertIn("forbidden path segment", result.items[0]["message"])
        self.assertEqual(result.summary["writes_attempted"], 0)
        self.assertFalse(
            (self.workspace_root / contracts.CUSTOMIZATIONS_LOCK_PATH).exists()
        )

    @unittest.expectedFailure
    def test_null_byte_apply_target_is_rejected_gracefully_followup_272(self) -> None:
        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            approval="none",
            apply_targets=(".github/hooks/bad\x00hook.py",),
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "path_not_allowlisted")
        self.assertEqual(result.items[0]["reason_code"], "outside_allowlist")
        self.assertEqual(result.summary["writes_attempted"], 0)

    @unittest.expectedFailure
    def test_control_character_apply_target_is_rejected_followup_272(self) -> None:
        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            approval="none",
            apply_targets=(".github/hooks/bad\nhook.py",),
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "path_not_allowlisted")
        self.assertEqual(result.items[0]["reason_code"], "outside_allowlist")
        self.assertEqual(result.summary["writes_attempted"], 0)

    def test_symlinked_apply_target_resolving_outside_allowlist_is_rejected(self) -> None:
        symlink_dir = self.workspace_root / ".github" / "hooks" / "wiki-link"
        symlink_dir.parent.mkdir(parents=True, exist_ok=True)
        symlink_dir.symlink_to(self.workspace_root / "wiki", target_is_directory=True)

        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            approval="none",
            apply_targets=(".github/hooks/wiki-link/injected.py",),
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "path_not_allowlisted")
        self.assertEqual(result.items[0]["reason_code"], "outside_allowlist")
        self.assertIn("symlinked path component", result.items[0]["message"])
        self.assertEqual(result.summary["writes_attempted"], 0)

    def test_stale_customizations_lock_metadata_is_reclaimable_after_crash(self) -> None:
        lock_path = self.workspace_root / contracts.CUSTOMIZATIONS_LOCK_PATH
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("stale owner metadata\n", encoding="utf-8")

        first = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            approval="approved",
            apply_targets=("AGENTS.md",),
        )
        lock_path.unlink()
        second = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            approval="approved",
            apply_targets=("AGENTS.md",),
        )

        self.assertEqual(first.status, "pass")
        self.assertTrue(first.summary["lock_acquired"])
        self.assertEqual(second.status, "pass")
        self.assertTrue(second.summary["lock_acquired"])
        self.assertFalse(
            write_utils.is_write_lock_held(
                self.workspace_root,
                contracts.CUSTOMIZATIONS_LOCK_PATH,
            )
        )

    def test_partial_write_artifact_left_by_crashed_writer_is_not_touched(self) -> None:
        partial_path = self.workspace_root / ".github" / "hooks" / "new-hook.py.tmp"
        partial_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path.write_text("partial write from killed process\n", encoding="utf-8")
        final_path = self.workspace_root / ".github" / "hooks" / "new-hook.py"

        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            approval="approved",
            apply_targets=(".github/hooks/new-hook.py",),
        )

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.summary["writes_attempted"], 0)
        self.assertFalse(final_path.exists())
        self.assertEqual(
            partial_path.read_text(encoding="utf-8"),
            "partial write from killed process\n",
        )
        self.assertFalse(
            write_utils.is_write_lock_held(
                self.workspace_root,
                contracts.CUSTOMIZATIONS_LOCK_PATH,
            )
        )

    def test_live_customizations_lock_contention_fails_closed_then_retry_succeeds(
        self,
    ) -> None:
        with write_utils.exclusive_write_lock(
            self.workspace_root,
            lock_path=contracts.CUSTOMIZATIONS_LOCK_PATH,
        ):
            blocked = self._run_cli(
                "--mode",
                "apply",
                "--approval",
                "approved",
                "--apply-target",
                "AGENTS.md",
            )

        retried = self._run_cli(
            "--mode",
            "apply",
            "--approval",
            "approved",
            "--apply-target",
            "AGENTS.md",
        )

        self.assertEqual(blocked.returncode, 1)
        blocked_payload = json.loads(blocked.stdout)
        self.assertEqual(blocked_payload["status"], "fail")
        self.assertEqual(blocked_payload["reason_code"], "lock_unavailable")
        self.assertTrue(blocked_payload["lock_required"])
        self.assertFalse(blocked_payload["summary"]["lock_acquired"])
        self.assertEqual(retried.returncode, 0)
        retried_payload = json.loads(retried.stdout)
        self.assertEqual(retried_payload["status"], "pass")
        self.assertTrue(retried_payload["summary"]["lock_acquired"])

    def test_symlinked_customizations_lock_path_is_rejected_not_replaced(self) -> None:
        external_lock_target = self.workspace_root / "outside-customizations.lock"
        external_lock_target.write_text("external lock target\n", encoding="utf-8")
        lock_path = self.workspace_root / contracts.CUSTOMIZATIONS_LOCK_PATH
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.symlink_to(external_lock_target)

        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            approval="approved",
            apply_targets=("AGENTS.md",),
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "lock_unavailable")
        self.assertTrue(result.lock_required)
        self.assertFalse(result.summary["lock_acquired"])
        self.assertTrue(lock_path.is_symlink())
        self.assertEqual(
            external_lock_target.read_text(encoding="utf-8"),
            "external lock target\n",
        )
        self.assertFalse(
            write_utils.is_write_lock_held(
                self.workspace_root,
                contracts.CUSTOMIZATIONS_LOCK_PATH,
            )
        )

    def test_cross_skill_apply_target_is_refused_under_approved_lock(self) -> None:
        before_other_skill = (
            self.workspace_root / ".github" / "skills" / "other-skill" / "SKILL.md"
        ).read_text(encoding="utf-8")

        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="apply",
            approval="approved",
            apply_targets=(".github/skills/other-skill/SKILL.md",),
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "path_not_allowlisted")
        self.assertEqual(result.items[0]["reason_code"], "cross_skill_finding")
        self.assertEqual(result.summary["writes_attempted"], 0)
        self.assertEqual(
            (
                self.workspace_root
                / ".github"
                / "skills"
                / "other-skill"
                / "SKILL.md"
            ).read_text(encoding="utf-8"),
            before_other_skill,
        )
        self.assertFalse(
            write_utils.is_write_lock_held(
                self.workspace_root,
                contracts.CUSTOMIZATIONS_LOCK_PATH,
            )
        )

    def test_outofband_dotdot_path_resolving_to_audit_skill_stays_intra_skill(
        self,
    ) -> None:
        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="improve",
            classifier_findings=(
                self._finding(
                    suggested_artifact_path=(
                        ".github/skills/audit-knowledgebase-workspace/references/"
                        "../SKILL.md"
                    )
                ),
            ),
        )

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.summary["finding_count"], 1)
        self.assertEqual(result.summary["out_of_band_handoff_count"], 0)
        self.assertEqual(
            result.summary["findings"][0]["suggested_artifact_path"],
            ".github/skills/audit-knowledgebase-workspace/SKILL.md",
        )
        self.assertEqual(result.summary["writes_attempted"], 0)

    def test_outofband_misleading_cross_skill_marker_does_not_override_resolved_path(
        self,
    ) -> None:
        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="improve",
            classifier_findings=(
                self._finding(
                    route_scope="other_skill",
                    target_persona="framework-engineer",
                    suggested_artifact_path=(
                        ".github/skills/other-skill/../"
                        "audit-knowledgebase-workspace/SKILL.md"
                    ),
                ),
            ),
        )

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.summary["finding_count"], 1)
        self.assertEqual(result.summary["out_of_band_handoff_count"], 0)
        self.assertEqual(
            result.summary["findings"][0]["suggested_artifact_path"],
            ".github/skills/audit-knowledgebase-workspace/SKILL.md",
        )
        self.assertEqual(result.summary["writes_attempted"], 0)

    def test_outofband_missing_suggested_artifact_path_fails_closed(self) -> None:
        finding = self._finding()
        finding.pop("suggested_artifact_path")

        result = self.module.audit(
            repo_root=self.workspace_root,
            mode="improve",
            classifier_findings=(finding,),
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "invalid_input")
        self.assertIn("missing required field", result.message)
        self.assertIn("suggested_artifact_path", result.message)

    def test_cli_rejects_dry_run_flag_with_apply_mode_before_lock_acquisition(
        self,
    ) -> None:
        output = io.StringIO()

        exit_code = self.module.run_cli(
            [
                "--repo-root",
                str(self.workspace_root),
                "--mode",
                "apply",
                "--approval",
                "approved",
                "--dry-run",
                "--apply-target",
                "AGENTS.md",
            ],
            output_stream=output,
        )

        self.assertEqual(exit_code, 1)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertIn("--dry-run", payload["message"])
        self.assertFalse(payload["lock_required"])
        self.assertFalse(
            (self.workspace_root / contracts.CUSTOMIZATIONS_LOCK_PATH).exists()
        )

    def test_cli_default_without_mode_flag_is_documented_read_only_default(self) -> None:
        completed = self._run_cli()

        self.assertEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["mode"], "default")
        self.assertEqual(payload["status"], "pass")
        self.assertTrue(payload["summary"]["dry_run"])
        self.assertTrue(payload["summary"]["read_only"])
        self.assertEqual(payload["summary"]["writes_attempted"], 0)

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(AUDIT_WORKSPACE_PATH),
                "--repo-root",
                str(self.workspace_root),
                *args,
            ],
            check=False,
            capture_output=True,
            cwd=REPO_ROOT,
            text=True,
        )

    @staticmethod
    def _finding(**overrides: object) -> dict[str, object]:
        finding: dict[str, object] = {
            "source_file": "AGENTS.md",
            "source_section": "## Write-surface matrix",
            "proposed_destination": "Locality 2",
            "rationale": "Audit-owned guidance remains in the audit skill.",
            "compliance_risk": "agent-dependent",
            "expected_token_efficiency_rank": 2,
            "cache_strategy": "mtime_first_para",
            "suggested_artifact_path": ".github/skills/audit-knowledgebase-workspace/SKILL.md",
        }
        finding.update(overrides)
        return finding


if __name__ == "__main__":
    unittest.main()
