"""Contract checks for the maintenance recommendation runtime."""

from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
MAINTENANCE_AGENT_PATH = REPO_ROOT / ".github" / "agents" / "maintenance-auditor.md"
SCAN_FRESHNESS_SKILL_PATH = (
    REPO_ROOT / ".github" / "skills" / "scan-content-freshness" / "SKILL.md"
)
RECOMMEND_MAINTENANCE_SKILL_ROOT = (
    REPO_ROOT / ".github" / "skills" / "recommend-maintenance-follow-up"
)
RECOMMEND_MAINTENANCE_SKILL_PATH = RECOMMEND_MAINTENANCE_SKILL_ROOT / "SKILL.md"


class MaintenanceRuntimeTests(unittest.TestCase):
    def test_recommend_maintenance_skill_is_doc_only_and_governed(self) -> None:
        text = RECOMMEND_MAINTENANCE_SKILL_PATH.read_text(encoding="utf-8")

        self.assertTrue(RECOMMEND_MAINTENANCE_SKILL_PATH.is_file())
        self.assertFalse((RECOMMEND_MAINTENANCE_SKILL_ROOT / "logic").exists())
        self.assertIn("## Overview", text)
        self.assertIn("## When to Use", text)
        self.assertIn("## Contract", text)
        self.assertIn("## Assertions", text)
        self.assertIn("## Commands", text)
        self.assertIn("doc-only workflow", text.lower())
        self.assertIn("recommendation-first", text)
        self.assertIn("knowledgebase-orchestrator", text)
        self.assertIn("evidence-verifier", text)
        self.assertIn("policy-arbiter", text)
        self.assertIn("No direct wiki write", text)
        self.assertIn("scripts/validation/check_doc_freshness.py", text)
        self.assertIn(
            ".github/skills/validate-wiki-governance/logic/validate_wiki_governance.py",
            text,
        )

    def test_maintenance_agent_references_read_only_runtime_inputs(self) -> None:
        text = MAINTENANCE_AGENT_PATH.read_text(encoding="utf-8")

        self.assertIn("read-only and recommendation-first lane", text)
        self.assertIn(".github/skills/recommend-maintenance-follow-up/SKILL.md", text)
        self.assertIn(".github/skills/scan-content-freshness/SKILL.md", text)
        self.assertIn("knowledgebase-orchestrator", text)
        self.assertIn("evidence-verifier", text)
        self.assertIn("policy-arbiter", text)
        self.assertIn("No direct bulk rewrite, archive action, or out-of-band write", text)

    def test_scan_content_freshness_routes_stale_findings_back_to_governance(self) -> None:
        text = SCAN_FRESHNESS_SKILL_PATH.read_text(encoding="utf-8")

        self.assertIn("maintenance-auditor", text)
        self.assertIn("recommend-maintenance-follow-up", text)
        self.assertIn("read-only evidence", text)
        self.assertIn("knowledgebase-orchestrator", text)
        self.assertIn("evidence-verifier", text)
        self.assertIn("policy-arbiter", text)
        self.assertIn("No direct remediation", text)


if __name__ == "__main__":
    unittest.main()
