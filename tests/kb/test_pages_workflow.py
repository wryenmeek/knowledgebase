"""Workflow contract checks for GitHub Pages deployment pipeline."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


WORKFLOW_PATH = Path(".github/workflows/pages.yml")
SEARCH_PAGE_PATH = Path("wiki/search.md")
RUNBOOK_PATH = Path("docs/mvp-runbook.md")
USER_GUIDE_PATH = Path("docs/user-guide.md")


class PagesWorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}")
        self.workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_qmd_runtime_install_is_pinned_and_integrity_checked(self) -> None:
        expected_markers = (
            "Install pinned qmd runtime",
            'QMD_NPM_PACKAGE="@tobilu/qmd"',
            'QMD_VERSION="2.5.1"',
            'QMD_EXPECTED_INTEGRITY="sha512-Ep9ccOj1bNRinfTIszp5UZP8xfi5AJNtmzwWDD4ZVm2YdWVS+rFobWJQovj0HD2uIAFrryvbSpZYeGa3flEO7g=="',
            'npm view "${QMD_NPM_PACKAGE}@${QMD_VERSION}" dist.integrity --registry=https://registry.npmjs.org',
            'if [ "${QMD_DIST_INTEGRITY}" != "${QMD_EXPECTED_INTEGRITY}" ]; then',
            "::error::qmd dist.integrity mismatch",
            'npm install --global "${QMD_NPM_PACKAGE}@${QMD_VERSION}" --registry=https://registry.npmjs.org',
            "qmd --version",
        )
        for marker in expected_markers:
            self.assertIn(marker, self.workflow_text)
        self.assertIn("exit 1", self.workflow_text)
        self.assertIn("Set up Node.js", self.workflow_text)
        self.assertIn("uses: actions/setup-node@a0853c24544627f65ddf259abe73b1d18a591444", self.workflow_text)

    def test_pages_qmd_steps_are_ordered_and_preflight_gates_embed(self) -> None:
        ordered_steps = (
            "Initialize qmd runtime index resource",
            "Build MkDocs site",
            "Build qmd wiki collection",
            "Run qmd preflight",
            "Build qmd embeddings",
            "Refresh qmd index export",
            "Upload qmd index artifact",
            "Install pinned Pagefind runtime",
            "Build Pagefind index",
        )
        previous_index = -1
        for step in ordered_steps:
            current_index = self.workflow_text.find(step)
            self.assertNotEqual(current_index, -1, f"Missing workflow step marker: {step}")
            self.assertGreater(
                current_index,
                previous_index,
                f"Workflow step '{step}' should appear after previous qmd/pages step",
            )
            previous_index = current_index
        self.assertIn('echo "::add-mask::${GITHUB_WORKSPACE}"', self.workflow_text)
        self.assertIn("qmd collection add wiki --name wiki", self.workflow_text)
        self.assertNotIn(".ci-bin", self.workflow_text)
        self.assertNotIn("cat > .ci-bin/qmd", self.workflow_text)

    def test_qmd_index_artifact_is_persisted_for_downstream_consumers(self) -> None:
        self.assertIn("Upload qmd index artifact", self.workflow_text)
        self.assertIn(
            "uses: actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f",
            self.workflow_text,
        )
        self.assertIn("name: qmd-index-${{ github.run_id }}-${{ github.run_attempt }}", self.workflow_text)
        self.assertIn("path: .qmd/index/", self.workflow_text)
        self.assertIn("if-no-files-found: error", self.workflow_text)
        self.assertIn("retention-days: 14", self.workflow_text)

    def test_pagefind_runtime_is_pinned_and_integrity_checked(self) -> None:
        expected_markers = (
            "Install pinned Pagefind runtime",
            'PF_NPM_PACKAGE="pagefind"',
            'PF_VERSION="1.5.2"',
            'PF_EXPECTED_INTEGRITY="sha512-XTUaK0hXMCu2jszWE584JGQT7y284TmMV9l/HX3rnG5uo3rHI/uHU56XTyyyPFjeWEBxECbAi0CaFDJOONtG0Q=="',
            'npm view "${PF_NPM_PACKAGE}@${PF_VERSION}" dist.integrity --registry=https://registry.npmjs.org',
            'if [ "${PF_DIST_INTEGRITY}" != "${PF_EXPECTED_INTEGRITY}" ]; then',
            "::error::pagefind dist.integrity mismatch",
            'npm install --global "${PF_NPM_PACKAGE}@${PF_VERSION}" --registry=https://registry.npmjs.org',
            "pagefind --version",
        )
        for marker in expected_markers:
            self.assertIn(marker, self.workflow_text)
        self.assertIn("exit 1", self.workflow_text)
        self.assertIn("run: pagefind --site site", self.workflow_text)
        self.assertNotIn("npx --yes pagefind --site site", self.workflow_text)

    def test_pages_permissions_are_split_by_job(self) -> None:
        self.assertIn("permissions:\n  contents: read", self.workflow_text)
        self.assertIn("persist-credentials: false", self.workflow_text)
        self.assertIsNone(
            re.search(
                r"(?ms)^permissions:\n(?:(?!^jobs:).)*\b(pages|id-token)\s*:\s*write\b",
                self.workflow_text,
            ),
            "Top-level permissions must not grant pages/id-token write",
        )
        build_block_match = re.search(
            r"(?ms)^  build:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)",
            self.workflow_text,
        )
        self.assertIsNotNone(build_block_match, "pages workflow missing build job block")
        self.assertIsNone(
            re.search(
                r"(?im)^\s*(pages|id-token)\s*:\s*write\s*$",
                build_block_match.group("body"),
            ),
            "Build job must not request pages/id-token write",
        )
        self.assertRegex(
            self.workflow_text,
            r"(?ms)jobs:\n  build:\n.*?permissions:\n\s+contents:\s*read",
        )
        self.assertRegex(
            self.workflow_text,
            r"(?ms)  deploy:\n\s+needs:\s+build\n.*?permissions:\n\s+pages:\s*write\n\s+id-token:\s*write",
        )


class SearchPageSemanticContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(SEARCH_PAGE_PATH.exists(), f"Missing search page: {SEARCH_PAGE_PATH}")
        self.assertTrue(RUNBOOK_PATH.exists(), f"Missing runbook: {RUNBOOK_PATH}")
        self.assertTrue(USER_GUIDE_PATH.exists(), f"Missing user guide: {USER_GUIDE_PATH}")
        self.search_page_text = SEARCH_PAGE_PATH.read_text(encoding="utf-8")
        self.runbook_text = RUNBOOK_PATH.read_text(encoding="utf-8")
        self.user_guide_text = USER_GUIDE_PATH.read_text(encoding="utf-8")

    def test_search_page_keeps_pagefind_and_declares_semantic_api_markers(self) -> None:
        expected_markers = (
            "new PagefindUI(",
            'element: "#pagefind-search"',
            'const STORAGE_KEY = "kb-semantic-search-endpoint";',
            'const SEARCH_PATH = "/query";',
            '"Content-Type": "application/json"',
            "query,",
            "limit: RESULT_LIMIT",
            "semantic_api_http_",
            "semantic_api_content_type",
            "semantic_api_json_parse",
            "semantic_api_payload_shape",
            "function sanitizeEndpoint(rawEndpoint)",
            "function sanitizeResultUrl(rawUrl)",
            'if (parsedUrl.protocol !== "http:" && parsedUrl.protocol !== "https:")',
            'id="semantic-search"',
            'id="semantic-api-status"',
            'id="semantic-results-list"',
            "Pagefind results remain available.",
        )
        for marker in expected_markers:
            self.assertIn(marker, self.search_page_text)
        self.assertNotIn("innerHTML", self.search_page_text)

    def test_runbook_documents_semantic_api_contract(self) -> None:
        expected_markers = (
            "## Wiki search semantic API contract (repo-local)",
            "`kb-semantic-search-endpoint`",
            "Endpoint values must resolve to `http` or `https`",
            "`POST <base-endpoint>/query`",
            "`results` array",
            '"title": "Result title"',
            '"url": "/knowledgebase/concepts/example/"',
            '"snippet": "Short excerpt from the result."',
            '"score": 0.92',
            "Missing endpoint: semantic lane stays disabled",
            "Network failure: semantic lane reports unavailable state",
            "Non-2xx HTTP status: semantic lane reports HTTP fallback state",
            "Non-JSON `Content-Type`, JSON parse errors, or missing `results` array",
            "text nodes (`textContent`)",
            "Pagefind results remain",
        )
        for marker in expected_markers:
            self.assertIn(marker, self.runbook_text)

    def test_user_guide_documents_semantic_api_configuration_and_fallback(self) -> None:
        expected_markers = (
            "### Optional semantic API results in wiki/search.md",
            "Enter an `http`/`https` endpoint and click **Save endpoint**.",
            "`kb-semantic-search-endpoint`",
            "`POST <base-endpoint>/query`",
            "Pagefind results remain",
        )
        for marker in expected_markers:
            self.assertIn(marker, self.user_guide_text)


if __name__ == "__main__":
    unittest.main()
