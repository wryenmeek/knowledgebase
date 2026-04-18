"""Contract checks for the change-patrol runtime lane."""

from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
CHANGE_PATROL_AGENT_PATH = REPO_ROOT / ".github" / "agents" / "change-patrol.md"
POLICY_DIFF_SKILL_ROOT = REPO_ROOT / ".github" / "skills" / "policy-diff-review"
POLICY_DIFF_SKILL_PATH = POLICY_DIFF_SKILL_ROOT / "SKILL.md"
LOG_PATROL_SKILL_ROOT = REPO_ROOT / ".github" / "skills" / "log-patrol-incident"
LOG_PATROL_SKILL_PATH = LOG_PATROL_SKILL_ROOT / "SKILL.md"


class ChangePatrolRuntimeTests(unittest.TestCase):
    def test_policy_diff_skill_is_doc_only_and_routes_follow_up_back_through_governance(self) -> None:
        text = POLICY_DIFF_SKILL_PATH.read_text(encoding="utf-8")

        self.assertTrue(POLICY_DIFF_SKILL_PATH.is_file())
        self.assertFalse((POLICY_DIFF_SKILL_ROOT / "logic").exists())
        self.assertIn("## Overview", text)
        self.assertIn("## When to Use", text)
        self.assertIn("## Contract", text)
        self.assertIn("## Assertions", text)
        self.assertIn("## References", text)
        self.assertIn("doc-only workflow", text.lower())
        self.assertIn("diff-based", text)
        self.assertIn("knowledgebase-orchestrator", text)
        self.assertIn("evidence-verifier", text)
        self.assertIn("policy-arbiter", text)
        self.assertIn("No direct revert, remediation, suppression, or content rewrite", text)
        self.assertIn("policy-diff review bundle", text)

    def test_log_patrol_incident_skill_is_doc_only_and_remains_append_only_in_design(self) -> None:
        text = LOG_PATROL_SKILL_PATH.read_text(encoding="utf-8")

        self.assertTrue(LOG_PATROL_SKILL_PATH.is_file())
        self.assertFalse((LOG_PATROL_SKILL_ROOT / "logic").exists())
        self.assertIn("## Overview", text)
        self.assertIn("## When to Use", text)
        self.assertIn("## Contract", text)
        self.assertIn("## Assertions", text)
        self.assertIn("## References", text)
        self.assertIn("doc-only workflow", text.lower())
        self.assertIn("append-only", text)
        self.assertIn("knowledgebase-orchestrator", text)
        self.assertIn("wiki/log.md", text)
        self.assertIn("No direct revert, remediation, or destructive history edit", text)

    def test_change_patrol_agent_uses_policy_diff_and_incident_skills_without_auto_fixing(self) -> None:
        text = CHANGE_PATROL_AGENT_PATH.read_text(encoding="utf-8")

        self.assertIn(".github/skills/policy-diff-review/SKILL.md", text)
        self.assertIn(".github/skills/log-patrol-incident/SKILL.md", text)
        self.assertIn("Policy-diff review bundle", text)
        self.assertIn("Incident note", text)
        self.assertIn("policy/citation-risk review is recommendation-first", text.lower())
        self.assertIn("no direct remediation, revert, or cleanup path opens from this persona", text)
        self.assertIn("No direct revert, silent suppression, or out-of-band write is permitted", text)


if __name__ == "__main__":
    unittest.main()
