"""Workflow contract checks for GitHub Pages deployment pipeline."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW_PATH = Path(".github/workflows/pages.yml")
SEARCH_PAGE_PATH = Path("wiki/search.md")
RUNBOOK_PATH = Path("docs/mvp-runbook.md")
USER_GUIDE_PATH = Path("docs/user-guide.md")
SEMANTIC_BEHAVIOR_HARNESS_PATH = Path("tests/kb/fixtures/semantic_behavior_harness.js")
SEMANTIC_INLINE_SCRIPT_PATH = Path("tests/kb/fixtures/semantic_inline_script.js")


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


class SearchPageSemanticBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(SEARCH_PAGE_PATH.exists(), f"Missing search page: {SEARCH_PAGE_PATH}")
        self.assertTrue(
            SEMANTIC_BEHAVIOR_HARNESS_PATH.exists(),
            f"Missing semantic behavior harness fixture: {SEMANTIC_BEHAVIOR_HARNESS_PATH}",
        )
        self.assertTrue(
            SEMANTIC_INLINE_SCRIPT_PATH.exists(),
            f"Missing semantic inline script fixture: {SEMANTIC_INLINE_SCRIPT_PATH}",
        )
        self.search_page_text = SEARCH_PAGE_PATH.read_text(encoding="utf-8")
        self.semantic_behavior_harness = SEMANTIC_BEHAVIOR_HARNESS_PATH.read_text(encoding="utf-8")
        self.semantic_inline_script = SEMANTIC_INLINE_SCRIPT_PATH.read_text(encoding="utf-8")
        node_path = shutil.which("node")
        if not node_path:
            self.skipTest("Node runtime is required for semantic behavior tests")
        self.node_path = node_path

    def _extract_inline_semantic_script(self) -> str:
        script_match = re.search(
            r"<script>\s*(?P<script>\(function\(\)\s*\{.*?\}\)\(\);)\s*</script>",
            self.search_page_text,
            re.DOTALL,
        )
        self.assertIsNotNone(script_match, "Missing inline semantic script in wiki/search.md")
        return textwrap.dedent(script_match.group("script")).strip()

    def _run_semantic_behavior_scenario(self, scenario: str) -> dict[str, object]:
        inline_script = self._extract_inline_semantic_script()
        normalized_fixture_script = "\n".join(
            line.lstrip() for line in self.semantic_inline_script.strip().splitlines()
        )
        normalized_search_script = "\n".join(
            line.lstrip() for line in inline_script.splitlines()
        )
        self.assertEqual(
            normalized_fixture_script,
            normalized_search_script,
            "semantic_inline_script.js must stay in sync with wiki/search.md inline script",
        )
        harness_script = self.semantic_behavior_harness.replace(
            "__INLINE_SCRIPT__", json.dumps(inline_script)
        ).replace("__SCENARIO__", json.dumps(scenario))
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".js", delete=False
        ) as harness_file:
            harness_file.write(harness_script)
            harness_path = Path(harness_file.name)
        try:
            completed = subprocess.run(
                [self.node_path, str(harness_path)],
                check=False,
                capture_output=True,
                text=True,
            )
        finally:
            harness_path.unlink(missing_ok=True)
        self.assertEqual(
            completed.returncode,
            0,
            (
                f"Semantic behavior harness failed for scenario {scenario}\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            ),
        )
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            self.fail(
                (
                    f"Semantic behavior harness did not emit JSON for scenario {scenario}: {error}\n"
                    f"stdout:\n{completed.stdout}\n"
                    f"stderr:\n{completed.stderr}"
                )
            )

    def test_stale_response_cannot_overwrite_newest_query_results(self) -> None:
        result = self._run_semantic_behavior_scenario("stale-response")
        self.assertEqual(result["fetchCallCount"], 2)
        self.assertTrue(result["firstRequestAborted"])
        self.assertEqual(result["resultCount"], 1)
        self.assertEqual(result["renderedTitles"], ["Newest semantic result"])
        self.assertEqual(
            result["statusMessage"],
            "Semantic API query complete. Pagefind results remain available.",
        )

    def test_unsafe_result_urls_are_non_clickable_text(self) -> None:
        result = self._run_semantic_behavior_scenario("unsafe-url")
        self.assertEqual(result["childTag"], "span")
        self.assertFalse(result["hasHref"])
        self.assertEqual(result["renderedTitle"], "Unsafe semantic result")

    def test_http_error_sets_http_fallback_status(self) -> None:
        result = self._run_semantic_behavior_scenario("fallback-http-error")
        self.assertEqual(result["fetchCallCount"], 1)
        self.assertEqual(result["resultCount"], 0)
        self.assertEqual(
            result["statusMessage"],
            "Semantic API returned an HTTP error. Pagefind results remain available.",
        )

    def test_non_json_content_type_sets_content_type_fallback_status(self) -> None:
        result = self._run_semantic_behavior_scenario("fallback-content-type")
        self.assertEqual(result["fetchCallCount"], 1)
        self.assertEqual(result["resultCount"], 0)
        self.assertEqual(
            result["statusMessage"],
            "Semantic API response was not JSON. Pagefind results remain available.",
        )

    def test_json_parse_error_sets_parse_fallback_status(self) -> None:
        result = self._run_semantic_behavior_scenario("fallback-json-parse")
        self.assertEqual(result["fetchCallCount"], 1)
        self.assertEqual(result["resultCount"], 0)
        self.assertEqual(
            result["statusMessage"],
            "Semantic API response could not be parsed. Pagefind results remain available.",
        )

    def test_missing_results_array_sets_payload_shape_fallback_status(self) -> None:
        result = self._run_semantic_behavior_scenario("fallback-payload-shape")
        self.assertEqual(result["fetchCallCount"], 1)
        self.assertEqual(result["resultCount"], 0)
        self.assertEqual(
            result["statusMessage"],
            "Semantic API response was missing a results array. Pagefind results remain available.",
        )

    def test_unclassified_semantic_error_sets_unavailable_fallback_status(self) -> None:
        result = self._run_semantic_behavior_scenario("fallback-unavailable")
        self.assertEqual(result["fetchCallCount"], 1)
        self.assertEqual(result["resultCount"], 0)
        self.assertEqual(
            result["statusMessage"],
            "Semantic API is unavailable. Pagefind results remain available.",
        )


if __name__ == "__main__":
    unittest.main()
