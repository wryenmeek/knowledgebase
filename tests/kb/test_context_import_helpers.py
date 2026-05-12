"""Tests for skill-local context import helpers."""

from __future__ import annotations

import json

from tests.kb.harnesses import REPO_ROOT, RuntimeWorkspaceTestCase, load_module


VALIDATE_CONTEXT_IMPORTS_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "context-engineering"
    / "logic"
    / "validate_context_imports.py"
)
NORMALIZE_CONTEXT_IMPORTS_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "context-engineering"
    / "logic"
    / "normalize_context_imports.py"
)


class ContextImportHelperTests(RuntimeWorkspaceTestCase):
    RUNTIME_ROOT_NAME = ".runtime_context_imports"

    def setUp(self) -> None:
        super().setUp()
        self.validate_module = load_module(
            f"validate_context_imports_{self._testMethodName}",
            VALIDATE_CONTEXT_IMPORTS_PATH,
        )
        self.normalize_module = load_module(
            f"normalize_context_imports_{self._testMethodName}",
            NORMALIZE_CONTEXT_IMPORTS_PATH,
        )

    def test_validate_context_imports_rejects_out_of_scope_context_file(self) -> None:
        self.write_file(
            "wiki/context-imports.json",
            json.dumps({"version": 1, "imports": [{"path": "docs/architecture.md"}]}),
        )

        result = self.validate_module.validate_context_imports(
            "wiki/context-imports.json",
            repo_root=self.workspace,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason_code, "path_not_allowlisted")

    def test_validate_context_imports_fails_closed_when_import_count_exceeds_cap(self) -> None:
        imports = [{"path": f"docs/page-{index}.md"} for index in range(13)]
        self.write_file(
            ".github/skills/demo/context-imports.json",
            json.dumps({"version": 1, "imports": imports}),
        )

        result = self.validate_module.validate_context_imports(
            ".github/skills/demo/context-imports.json",
            repo_root=self.workspace,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason_code, "too_many_imports")

    def test_normalize_context_imports_upgrades_legacy_string_entries(self) -> None:
        self.write_file(
            ".github/skills/demo/context-imports.json",
            json.dumps({"imports": ["docs/architecture.md", "schema/page-template.md"]}),
        )

        result = self.normalize_module.normalize_context_imports(
            ".github/skills/demo/context-imports.json",
            repo_root=self.workspace,
        )

        self.assertTrue(result.valid)
        self.assertEqual(
            result.normalized_document,
            {
                "version": 1,
                "imports": [
                    {"path": "docs/architecture.md"},
                    {"path": "schema/page-template.md"},
                ],
            },
        )
