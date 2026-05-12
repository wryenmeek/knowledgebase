"""Tests for skill-local documentation helpers."""

from __future__ import annotations

from tests.kb.harnesses import REPO_ROOT, RuntimeWorkspaceTestCase, load_module


REPAIR_MARKDOWN_STRUCTURE_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "documentation-and-adrs"
    / "logic"
    / "repair_markdown_structure.py"
)
VALIDATE_DOC_BATCH_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "documentation-and-adrs"
    / "logic"
    / "validate_doc_batch.py"
)


class DocumentationHelperTests(RuntimeWorkspaceTestCase):
    RUNTIME_ROOT_NAME = ".runtime_documentation_helpers"

    def setUp(self) -> None:
        super().setUp()
        self.repair_module = load_module(
            f"repair_markdown_structure_{self._testMethodName}",
            REPAIR_MARKDOWN_STRUCTURE_PATH,
        )
        self.validate_module = load_module(
            f"validate_doc_batch_{self._testMethodName}",
            VALIDATE_DOC_BATCH_PATH,
        )

    def test_repair_markdown_structure_rejects_non_document_paths(self) -> None:
        self.write_file("raw/processed/not-allowed.md", "# Raw\n")

        result = self.repair_module.repair_markdown_structure(
            "raw/processed/not-allowed.md",
            repo_root=self.workspace,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason_code, "path_not_allowlisted")

    def test_repair_markdown_structure_normalizes_duplicate_headings_and_unclosed_fences(self) -> None:
        self.write_file(
            "docs/guide.md",
            "# Guide\n## Steps\n## Steps\n```python\nprint('x')\n",
        )

        result = self.repair_module.repair_markdown_structure(
            "docs/guide.md",
            repo_root=self.workspace,
        )

        self.assertTrue(result.valid)
        self.assertTrue(result.changed)
        self.assertEqual(result.normalized_text.count("## Steps"), 1)
        self.assertTrue(result.normalized_text.endswith("```\n"))

    def test_validate_doc_batch_fails_closed_on_missing_internal_link(self) -> None:
        self.write_file("docs/guide.md", "# Guide\n\n[Missing](missing.md)\n")

        result = self.validate_module.validate_doc_batch(
            ("docs/guide.md",),
            repo_root=self.workspace,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason_code, "batch_invalid")
        self.assertEqual(result.results[0].reason_code, "missing_link")
