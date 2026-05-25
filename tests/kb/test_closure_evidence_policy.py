"""Contract checks for closure-evidence policy docs and script alignment."""

from __future__ import annotations

from pathlib import Path
import unittest

from scripts.validation import check_issue_closure_evidence


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK_PATH = REPO_ROOT / "docs" / "mvp-runbook.md"
RUNBOOK_FIELD_LABELS = {
    "implementation_reference": "Implementation reference:",
    "key_files_surfaces_changed": "Key files/surfaces changed:",
    "validation_commands": "Validation commands:",
    "pass_fail_summary": "Pass/fail summary:",
}


class ClosureEvidencePolicyContractTests(unittest.TestCase):
    def test_runbook_template_includes_required_closure_evidence_fields(self) -> None:
        text = RUNBOOK_PATH.read_text(encoding="utf-8")
        self.assertIn("## Issue closure evidence policy", text)
        self.assertIn("### Closure evidence", text)
        for field_key, label in RUNBOOK_FIELD_LABELS.items():
            with self.subTest(field=field_key):
                self.assertIn(field_key, check_issue_closure_evidence.REQUIRED_EVIDENCE_FIELDS)
                self.assertIn(label, text)

    def test_runbook_documents_default_target_labels(self) -> None:
        text = RUNBOOK_PATH.read_text(encoding="utf-8")
        for label in check_issue_closure_evidence.DEFAULT_TARGET_LABELS:
            with self.subTest(label=label):
                self.assertIn(f"`{label}`", text)


if __name__ == "__main__":
    unittest.main()
