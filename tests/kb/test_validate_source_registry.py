"""Tests for skill-local source registry validation."""

from __future__ import annotations

import json

from tests.kb.harnesses import REPO_ROOT, RuntimeWorkspaceTestCase, load_module


VALIDATE_SOURCE_REGISTRY_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "validate-inbox-source"
    / "logic"
    / "validate_source_registry.py"
)


class ValidateSourceRegistryTests(RuntimeWorkspaceTestCase):
    RUNTIME_ROOT_NAME = ".runtime_source_registry"

    def setUp(self) -> None:
        super().setUp()
        self.module = load_module(
            f"validate_source_registry_{self._testMethodName}",
            VALIDATE_SOURCE_REGISTRY_PATH,
        )

    def test_validate_source_registry_accepts_local_and_external_entries(self) -> None:
        self.write_file(
            "raw/processed/example.source-registry.json",
            json.dumps(
                {
                    "version": 1,
                    "sources": [
                        {"id": "local-source", "kind": "local", "location": "raw/processed/a.md"},
                        {"id": "cms", "kind": "external", "location": "https://www.cms.gov/"},
                    ],
                }
            ),
        )

        result = self.module.validate_source_registry(
            "raw/processed/example.source-registry.json",
            repo_root=self.workspace,
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.entry_count, 2)

    def test_validate_source_registry_rejects_registry_outside_declared_surface(self) -> None:
        self.write_file(
            "wiki/example.source-registry.json",
            json.dumps({"version": 1, "sources": []}),
        )

        result = self.module.validate_source_registry(
            "wiki/example.source-registry.json",
            repo_root=self.workspace,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason_code, "path_not_allowlisted")

    def test_validate_source_registry_fails_closed_on_non_authoritative_source_locations(self) -> None:
        self.write_file(
            "raw/processed/example.source-registry.json",
            json.dumps(
                {
                    "version": 1,
                    "sources": [
                        {"id": "bad-local", "kind": "local", "location": "docs/guide.md"},
                        {"id": "bad-external", "kind": "external", "location": "http://example.com"},
                    ],
                }
            ),
        )

        result = self.module.validate_source_registry(
            "raw/processed/example.source-registry.json",
            repo_root=self.workspace,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason_code, "invalid_registry")
        self.assertEqual(
            tuple(issue.reason_code for issue in result.issues),
            ("local_path_not_allowlisted", "invalid_external_url"),
        )
