"""Tests for skill-local wiki topology validation."""

from __future__ import annotations

from tests.kb.harnesses import REPO_ROOT, RuntimeWorkspaceTestCase, load_module


VALIDATE_WIKI_TOPOLOGY_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "check-link-topology"
    / "logic"
    / "validate_wiki_topology.py"
)


class ValidateWikiTopologyTests(RuntimeWorkspaceTestCase):
    RUNTIME_ROOT_NAME = ".runtime_wiki_topology"

    def setUp(self) -> None:
        super().setUp()
        self.module = load_module(
            f"validate_wiki_topology_{self._testMethodName}",
            VALIDATE_WIKI_TOPOLOGY_PATH,
        )

    def test_validate_wiki_topology_rejects_scope_outside_wiki_surface(self) -> None:
        self.write_file("docs/outside.md", "# Outside\n")

        result = self.module.validate_wiki_topology(
            ("docs/outside.md",),
            repo_root=self.workspace,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason_code, "path_not_allowlisted")

    def test_validate_wiki_topology_reports_missing_control_artifacts_and_orphans(self) -> None:
        self.write_file("wiki/sources/orphan.md", "# Orphan\n")

        result = self.module.validate_wiki_topology(
            ("wiki/sources/orphan.md",),
            repo_root=self.workspace,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason_code, "topology_invalid")
        self.assertEqual(
            tuple(violation.code for violation in result.violations),
            ("missing-control-artifact", "missing-control-artifact", "orphan-page"),
        )

    def test_validate_wiki_topology_accepts_indexed_page_with_heading(self) -> None:
        self.write_file("wiki/log.md", "# Log\n")
        self.write_file("wiki/index.md", "# Index\n\n- [Page](sources/page.md)\n")
        self.write_file("wiki/sources/page.md", "# Page\n\n[Index](../index.md)\n")

        result = self.module.validate_wiki_topology(
            ("wiki/sources/page.md",),
            repo_root=self.workspace,
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.violations, ())
