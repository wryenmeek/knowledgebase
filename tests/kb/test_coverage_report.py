"""Tests for scripts/reporting/coverage_report.py."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
import unittest

from tests.kb.harnesses import RuntimeWorkspaceTestCase, load_module

REPO_ROOT = Path(__file__).resolve().parents[2]
COVERAGE_REPORT_PATH = REPO_ROOT / "scripts" / "reporting" / "coverage_report.py"


def _topical_page(title: str = "Test Page") -> str:
    """Minimal well-formed wiki page with a recent updated_at."""
    return (
        "---\n"
        f'title: "{title}"\n'
        'type: concept\n'
        'status: active\n'
        'updated_at: "2099-01-01"\n'
        "sources: []\n"
        "---\n\n"
        f"# {title}\n\nBody text.\n"
    )


def _stale_page(title: str = "Stale Page") -> str:
    """Wiki page with an updated_at in the distant past (triggers stale detection)."""
    return (
        "---\n"
        f'title: "{title}"\n'
        'type: concept\n'
        'status: active\n'
        'updated_at: "2000-01-01"\n'
        "sources: []\n"
        "---\n\n"
        f"# {title}\n\nBody text.\n"
    )


def _placeholder_page(title: str = "Placeholder Page") -> str:
    """Wiki page containing a placeholder marker."""
    return (
        "---\n"
        f'title: "{title}"\n'
        'type: concept\n'
        'status: draft\n'
        'updated_at: "2099-01-01"\n'
        "sources: []\n"
        "---\n\n"
        f"# {title}\n\n{{{{fill}}}}\n"
    )


class CoverageReportSummaryModeTests(RuntimeWorkspaceTestCase):
    RUNTIME_ROOT_NAME = ".runtime_coverage_report"

    def setUp(self) -> None:
        super().setUp()
        # Minimal repo root marker
        (self.workspace / "AGENTS.md").write_text("fixture\n", encoding="utf-8")
        self.module = load_module(
            f"coverage_report_{self._testMethodName}", COVERAGE_REPORT_PATH
        )

    def _write_wiki_page(self, rel_path: str, content: str) -> Path:
        page = self.workspace / "wiki" / rel_path
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(content, encoding="utf-8")
        return page

    # ------------------------------------------------------------------
    # Test 1: Summary mode happy path
    # ------------------------------------------------------------------
    def test_summary_mode_happy_path(self) -> None:
        """3 pages: 2 topical + 1 analyses; verify counts and status=pass."""
        (self.workspace / "wiki").mkdir(parents=True, exist_ok=True)
        self._write_wiki_page("page_a.md", _topical_page("Page A"))
        self._write_wiki_page("page_b.md", _topical_page("Page B"))
        self._write_wiki_page("analyses/analysis_one.md", _topical_page("Analysis One"))

        result = self.module.run_coverage_report(
            repo_root=self.workspace,
            mode="summary",
        )

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.mode, "summary")
        self.assertEqual(result.summary["total_pages"], 3)
        self.assertEqual(result.summary["pages_by_namespace"]["topical"], 2)
        self.assertEqual(result.summary["pages_by_namespace"]["analyses"], 1)
        self.assertEqual(result.summary["total_placeholders"], 0)
        self.assertEqual(result.summary["coverage_ratio"], 1.0)

    # ------------------------------------------------------------------
    # Test 2: Persist mode without approval → fail, approval_required
    # ------------------------------------------------------------------
    def test_persist_mode_without_approval_fails(self) -> None:
        """Persist mode without --approval approved must return status=fail."""
        (self.workspace / "wiki").mkdir(parents=True, exist_ok=True)
        self._write_wiki_page("page.md", _topical_page())

        result = self.module.run_coverage_report(
            repo_root=self.workspace,
            mode="persist",
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "approval_required")
        self.assertTrue(result.lock_required)
        # Verify no artifact was written
        reports_dir = self.workspace / "wiki" / "reports"
        self.assertFalse(
            reports_dir.exists(),
            "No artifact file should be written when approval is missing",
        )

    # ------------------------------------------------------------------
    # Test 3: Persist mode with approval → artifact written
    # ------------------------------------------------------------------
    def test_persist_mode_with_approval_writes_artifact(self) -> None:
        """Persist mode with --approval approved writes a governed JSON artifact."""
        (self.workspace / "wiki").mkdir(parents=True, exist_ok=True)
        self._write_wiki_page("page.md", _topical_page("My Page"))

        result = self.module.run_coverage_report(
            repo_root=self.workspace,
            mode="persist",
            approval="approved",
        )

        self.assertEqual(result.status, "pass", result.message)
        # Artifact file must exist under wiki/reports/coverage-report-*.json
        reports_dir = self.workspace / "wiki" / "reports"
        artifacts = list(reports_dir.glob("coverage-report-*.json"))
        self.assertEqual(len(artifacts), 1, "Exactly one artifact should be written")
        artifact_data = json.loads(artifacts[0].read_text(encoding="utf-8"))
        self.assertIn("total_pages", artifact_data["summary"])
        self.assertEqual(artifact_data["report_type"], "coverage-report")
        self.assertEqual(artifact_data["summary"]["total_pages"], 1)

    # ------------------------------------------------------------------
    # Test 4: Empty wiki → total_pages=0, coverage_ratio=1.0, empty_namespaces
    # ------------------------------------------------------------------
    def test_empty_wiki_returns_zero_coverage(self) -> None:
        """An existing but empty wiki/ directory returns safe empty coverage stats."""
        (self.workspace / "wiki").mkdir(parents=True, exist_ok=True)

        result = self.module.run_coverage_report(
            repo_root=self.workspace,
            mode="summary",
        )

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.summary["total_pages"], 0)
        self.assertAlmostEqual(result.summary["coverage_ratio"], 1.0)
        # empty_namespaces should list all declared TOPICAL_NAMESPACES
        self.assertIsInstance(result.summary["empty_namespaces"], list)
        self.assertGreater(
            len(result.summary["empty_namespaces"]),
            0,
            "At least one TOPICAL_NAMESPACE should appear in empty_namespaces",
        )

    # ------------------------------------------------------------------
    # Test 5: Path safety — walker is bounded to wiki/
    # ------------------------------------------------------------------
    def test_walker_bounded_to_wiki_root(self) -> None:
        """Pages outside wiki/ are never counted in the coverage report."""
        (self.workspace / "wiki").mkdir(parents=True, exist_ok=True)
        self._write_wiki_page("page.md", _topical_page("Inside Wiki"))
        # Create a markdown file outside wiki/ — must NOT be counted
        outside = self.workspace / "docs"
        outside.mkdir(parents=True, exist_ok=True)
        (outside / "outside.md").write_text(_topical_page("Outside Wiki"), encoding="utf-8")

        result = self.module.run_coverage_report(
            repo_root=self.workspace,
            mode="summary",
        )

        self.assertEqual(result.summary["total_pages"], 1)
        paths = [item["path"] for item in result.items]
        self.assertTrue(all(p.startswith("wiki/") for p in paths), paths)

    # ------------------------------------------------------------------
    # Test 6: Placeholder detection
    # ------------------------------------------------------------------
    def test_placeholder_detection(self) -> None:
        """A page with {{fill}} must appear in placeholder_pages_by_namespace."""
        (self.workspace / "wiki").mkdir(parents=True, exist_ok=True)
        self._write_wiki_page("normal.md", _topical_page("Normal"))
        self._write_wiki_page("draft.md", _placeholder_page("Draft"))

        result = self.module.run_coverage_report(
            repo_root=self.workspace,
            mode="summary",
        )

        self.assertEqual(result.summary["total_pages"], 2)
        self.assertEqual(result.summary["total_placeholders"], 1)
        self.assertIn("topical", result.summary["placeholder_pages_by_namespace"])
        self.assertEqual(
            result.summary["placeholder_pages_by_namespace"]["topical"], 1
        )
        # coverage_ratio must be < 1.0 when there are placeholders
        self.assertAlmostEqual(result.summary["coverage_ratio"], 0.5)

    # ------------------------------------------------------------------
    # Test 7: Stale page detection
    # ------------------------------------------------------------------
    def test_stale_page_detection(self) -> None:
        """A page with updated_at: '2000-01-01' must appear in stale_pages_by_namespace."""
        (self.workspace / "wiki").mkdir(parents=True, exist_ok=True)
        self._write_wiki_page("fresh.md", _topical_page("Fresh"))
        self._write_wiki_page("old.md", _stale_page("Old"))

        result = self.module.run_coverage_report(
            repo_root=self.workspace,
            mode="summary",
        )

        self.assertEqual(result.summary["total_pages"], 2)
        self.assertEqual(result.summary["total_stale"], 1)
        self.assertIn("topical", result.summary["stale_pages_by_namespace"])
        self.assertEqual(result.summary["stale_pages_by_namespace"]["topical"], 1)

    # ------------------------------------------------------------------
    # Additional: Excluded top-level files are not counted
    # ------------------------------------------------------------------
    def test_excluded_top_level_files_not_counted(self) -> None:
        """Canonical top-level artifact files (log.md, index.md, etc.) are excluded."""
        wiki = self.workspace / "wiki"
        wiki.mkdir(parents=True, exist_ok=True)
        for excluded_name in (
            "index.md",
            "log.md",
            "status.md",
            "backlog.md",
            "open-questions.md",
            "redirects.md",
        ):
            (wiki / excluded_name).write_text("# Excluded\n", encoding="utf-8")
        # Add one real page
        self._write_wiki_page("real.md", _topical_page("Real"))

        result = self.module.run_coverage_report(
            repo_root=self.workspace,
            mode="summary",
        )

        self.assertEqual(result.summary["total_pages"], 1)

    # ------------------------------------------------------------------
    # Additional: run_cli emits valid JSON and returns correct exit codes
    # ------------------------------------------------------------------
    def test_run_cli_summary_emits_json(self) -> None:
        """run_cli in summary mode writes valid JSON to output_stream."""
        (self.workspace / "wiki").mkdir(parents=True, exist_ok=True)
        self._write_wiki_page("page.md", _topical_page())

        stdout = StringIO()
        exit_code = self.module.run_cli(
            ["--repo-root", str(self.workspace), "--mode", "summary"],
            output_stream=stdout,
        )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "pass")
        self.assertIn("total_pages", payload["summary"])

    def test_run_cli_persist_without_approval_exits_nonzero(self) -> None:
        """run_cli in persist mode without approval must exit 1."""
        (self.workspace / "wiki").mkdir(parents=True, exist_ok=True)
        self._write_wiki_page("page.md", _topical_page())

        stdout = StringIO()
        exit_code = self.module.run_cli(
            ["--repo-root", str(self.workspace), "--mode", "persist"],
            output_stream=stdout,
        )

        self.assertEqual(exit_code, 1)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["reason_code"], "approval_required")

    # ------------------------------------------------------------------
    # Additional: SURFACE and SUPPORTED_MODES constants are correct
    # ------------------------------------------------------------------
    def test_module_constants(self) -> None:
        self.assertEqual(
            self.module.SURFACE, "scripts/reporting/coverage_report.py"
        )
        self.assertEqual(self.module.SUPPORTED_MODES, ("summary", "persist"))
        self.assertTrue(hasattr(self.module, "run_cli"))
        self.assertTrue(hasattr(self.module, "run_coverage_report"))
        self.assertTrue(hasattr(self.module, "main"))


if __name__ == "__main__":
    unittest.main()
