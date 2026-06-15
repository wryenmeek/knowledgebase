"""Tests for audit-workspace OutOfBand handoff routing."""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from tests.kb.harnesses import load_module


REPO_ROOT = Path(__file__).resolve().parents[2]
HANDOFF_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "audit-knowledgebase-workspace"
    / "logic"
    / "outofband_handoff.py"
)
AUDIT_WORKSPACE_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "audit-knowledgebase-workspace"
    / "logic"
    / "audit_workspace.py"
)


class AuditWorkspaceOutOfBandRoutingTests(TestCase):
    def _handoff_module(self):
        return load_module(f"outofband_handoff_{self._testMethodName}", HANDOFF_PATH)

    def _audit_module(self):
        return load_module(f"audit_workspace_outofband_{self._testMethodName}", AUDIT_WORKSPACE_PATH)

    def _audit_with_write_guards(self, module, **kwargs: object):
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
            result = module.audit(**kwargs)
            for mocked_call in mocks:
                mocked_call.assert_not_called()
            return result

    def test_cross_skill_agent_and_prompt_paths_route_to_framework_engineer(self) -> None:
        module = self._handoff_module()

        for suggested_path in (
            ".github/skills/context-engineering/SKILL.md",
            ".github/agents/framework-engineer.md",
            ".github/prompts/review-plan.prompt.md",
        ):
            with self.subTest(suggested_path=suggested_path):
                routed = module.route_findings(
                    (self._finding(suggested_artifact_path=suggested_path),),
                    repo_root=REPO_ROOT,
                )

                self.assertEqual(routed.eligible_findings, ())
                self.assertEqual(len(routed.out_of_band_handoffs), 1)
                record = routed.out_of_band_handoffs[0]
                self.assertEqual(
                    set(record),
                    {
                        "finding_id",
                        "source_file",
                        "source_section",
                        "suggested_artifact_path",
                        "rationale",
                        "target_persona",
                    },
                )
                self.assertTrue(record["finding_id"].startswith("outofband-"))
                self.assertEqual(record["source_file"], "AGENTS.md")
                self.assertEqual(record["source_section"], "## Write-surface matrix")
                self.assertEqual(record["suggested_artifact_path"], suggested_path)
                self.assertEqual(record["rationale"], self._finding()["rationale"])
                self.assertEqual(record["target_persona"], "framework-engineer")

    def test_audit_skill_own_directory_remains_eligible_not_outofband(self) -> None:
        module = self._handoff_module()
        finding = self._finding(
            suggested_artifact_path=".github/skills/audit-knowledgebase-workspace/SKILL.md"
        )

        routed = module.route_findings((finding,), repo_root=REPO_ROOT)

        self.assertEqual(routed.eligible_findings, (finding,))
        self.assertEqual(routed.out_of_band_handoffs, ())

    def test_subtle_path_variation_resolves_before_cross_skill_classification(self) -> None:
        module = self._handoff_module()

        routed = module.route_findings(
            (
                self._finding(
                    suggested_artifact_path=(
                        ".github/skills/audit-knowledgebase-workspace/../"
                        "context-engineering/SKILL.md"
                    )
                ),
            ),
            repo_root=REPO_ROOT,
        )

        self.assertEqual(routed.eligible_findings, ())
        self.assertEqual(
            routed.out_of_band_handoffs[0]["suggested_artifact_path"],
            ".github/skills/context-engineering/SKILL.md",
        )

    def test_unknown_finding_category_fails_closed(self) -> None:
        module = self._handoff_module()

        with self.assertRaisesRegex(module.OutOfBandRoutingError, "unsupported proposed_destination"):
            module.route_findings(
                (self._finding(proposed_destination="Mystery Locality"),),
                repo_root=REPO_ROOT,
            )

    def test_orchestrator_summary_includes_outofband_records(self) -> None:
        module = self._audit_module()

        result = self._audit_with_write_guards(
            module,
            repo_root=REPO_ROOT,
            mode="improve",
            classifier_findings=(
                self._finding(
                    suggested_artifact_path=".github/agents/documentation-engineer.md"
                ),
            ),
        )

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.summary["findings"], [])
        self.assertEqual(result.summary["finding_count"], 0)
        self.assertEqual(result.summary["out_of_band_handoff_count"], 1)
        self.assertEqual(
            result.summary["out_of_band_handoffs"][0]["target_persona"],
            "framework-engineer",
        )
        self.assertEqual(result.summary["writes_attempted"], 0)
        self.assertTrue(result.summary["read_only"])

    def test_orchestrator_fails_closed_for_malformed_non_string_category(self) -> None:
        module = self._audit_module()

        result = module.audit(
            repo_root=REPO_ROOT,
            mode="improve",
            classifier_findings=(self._finding(proposed_destination=[]),),
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "invalid_input")
        self.assertIn("unsupported proposed_destination", result.message)

    @staticmethod
    def _finding(**overrides: object) -> dict[str, object]:
        finding: dict[str, object] = {
            "source_file": "AGENTS.md",
            "source_section": "## Write-surface matrix",
            "proposed_destination": "Locality 2",
            "rationale": "Cross-skill guidance belongs with its owning framework surface.",
            "compliance_risk": "agent-dependent",
            "expected_token_efficiency_rank": 2,
            "cache_strategy": "mtime_first_para",
            "suggested_artifact_path": ".github/skills/context-engineering/SKILL.md",
        }
        finding.update(overrides)
        return finding
