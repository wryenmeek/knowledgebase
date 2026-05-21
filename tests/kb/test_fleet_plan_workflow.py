"""Workflow contract checks for Fleet Plan bootstrap behavior."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


WORKFLOW_PATH = Path(".github/workflows/fleet-plan.yml")


class FleetPlanWorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}")
        self.workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_store_pending_session_step_uses_explicit_fetch_fallback(self) -> None:
        self.assertIn("Store pending session ID", self.workflow_text)
        self.assertIn("if git fetch origin fleet-state 2>/dev/null; then", self.workflow_text)
        self.assertIn("git checkout -B fleet-state origin/fleet-state", self.workflow_text)
        self.assertIn("git checkout --orphan fleet-state", self.workflow_text)

    def test_store_pending_session_step_avoids_and_or_branch_checkout_chain(self) -> None:
        self.assertIsNone(
            re.search(
                r"git fetch origin fleet-state[^\n]*&&[^\n]*git checkout -B fleet-state origin/fleet-state[^\n]*\|\|",
                self.workflow_text,
            ),
            "fleet-plan branch selection must use explicit if/else, not && ... || chaining",
        )


if __name__ == "__main__":
    unittest.main()
