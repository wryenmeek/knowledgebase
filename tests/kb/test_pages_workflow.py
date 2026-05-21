"""Workflow contract checks for GitHub Pages deployment pipeline."""

from __future__ import annotations

from pathlib import Path
import unittest


WORKFLOW_PATH = Path(".github/workflows/pages.yml")


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


if __name__ == "__main__":
    unittest.main()
