"""CLI tests for scripts.kb.lint_wiki."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "kb" / "lint_wiki.py"
_RUNTIME_ROOT = Path(__file__).resolve().parent / ".runtime_lint_wiki"


class LintWikiCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = _RUNTIME_ROOT / self._testMethodName
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.wiki_root = self.workspace / "wiki"
        self.wiki_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        if _RUNTIME_ROOT.exists() and not any(_RUNTIME_ROOT.iterdir()):
            _RUNTIME_ROOT.rmdir()

    def _build_page(self, title: str, body: str) -> str:
        return "\n".join(
            [
                "---",
                "type: process",
                f'title: "{title}"',
                "status: active",
                "sources: []",
                "open_questions: []",
                "confidence: 3",
                "sensitivity: internal",
                'updated_at: "2024-01-01T00:00:00Z"',
                "tags: [test]",
                "---",
                "",
                f"# {title}",
                "",
                body,
                "",
            ]
        )

    def _write_page(self, relative_path: str, content: str) -> None:
        page = self.wiki_root / relative_path
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(content, encoding="utf-8")

    def _run_lint(self, *, strict: bool) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(SCRIPT_PATH),
            "--wiki-root",
            str(self.wiki_root),
        ]
        if strict:
            command.append("--strict")

        return subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def _seed_valid_wiki(self) -> None:
        self._write_page(
            "index.md",
            self._build_page(
                "Knowledgebase Index",
                "- [Log](log.md)\n- [Source A](sources/source-a.md)",
            ),
        )
        self._write_page(
            "log.md",
            self._build_page("Knowledgebase Log", "- state changes appear here"),
        )
        self._write_page(
            "sources/source-a.md",
            self._build_page("Source A", "- [Index](../index.md)"),
        )

    def _seed_invalid_wiki(self) -> None:
        self._write_page(
            "index.md",
            self._build_page("Knowledgebase Index", "- [Missing](sources/missing.md)"),
        )
        self._write_page(
            "sources/orphan.md",
            self._build_page("Orphan", "This page is intentionally unreferenced."),
        )
        self._write_page(
            "sources/contradiction.md",
            self._build_page("Contradiction", "[CONTRADICTION] unresolved evidence conflict."),
        )

    def _snapshot_wiki_files(self) -> dict[str, bytes]:
        snapshot: dict[str, bytes] = {}
        for path in sorted(self.wiki_root.rglob("*")):
            if path.is_file():
                snapshot[str(path.relative_to(self.wiki_root))] = path.read_bytes()
        return snapshot

    def _extract_violation_codes(self, stdout: str) -> list[str]:
        codes: list[str] = []
        for line in stdout.splitlines():
            parts = line.split(": ", 2)
            if len(parts) == 3:
                codes.append(parts[1])
        return codes

    def _assert_strict_violation_codes(self, expected_codes: list[str]) -> None:
        before_snapshot = self._snapshot_wiki_files()
        result = self._run_lint(strict=True)
        after_snapshot = self._snapshot_wiki_files()

        self.assertEqual(result.returncode, 1)
        self.assertEqual(self._extract_violation_codes(result.stdout), expected_codes)
        self.assertIn(f"Found {len(expected_codes)} violation(s).", result.stdout)
        self.assertEqual(after_snapshot, before_snapshot)

    def test_strict_mode_passes_for_clean_wiki(self) -> None:
        self._seed_valid_wiki()

        result = self._run_lint(strict=True)

        self.assertEqual(result.returncode, 0)
        self.assertIn("Found 0 violation(s).", result.stdout)

    def test_strict_mode_fails_for_wiki_violations(self) -> None:
        self._seed_invalid_wiki()

        self._assert_strict_violation_codes(
            [
                "missing-link-target",
                "orphan-page",
                "unresolved-contradiction-marker",
                "orphan-page",
            ]
        )

    def test_strict_mode_reports_out_of_bounds_link_violation(self) -> None:
        self._write_page(
            "index.md",
            self._build_page("Knowledgebase Index", "- [Escape](../outside.md)"),
        )

        self._assert_strict_violation_codes(["out-of-bounds-link"])

    def test_strict_mode_reports_missing_frontmatter_violation(self) -> None:
        self._write_page("index.md", "# Knowledgebase Index\n\nThis page omits frontmatter.\n")

        self._assert_strict_violation_codes(["missing-frontmatter"])

    def test_strict_mode_reports_missing_frontmatter_key_violation(self) -> None:
        self._write_page(
            "index.md",
            "\n".join(
                [
                    "---",
                    "type: process",
                    'title: "Knowledgebase Index"',
                    "status: active",
                    "sources: []",
                    "open_questions: []",
                    "confidence: 3",
                    "sensitivity: internal",
                    'updated_at: "2024-01-01T00:00:00Z"',
                    "---",
                    "",
                    "# Knowledgebase Index",
                    "",
                    "- frontmatter intentionally missing tags key",
                    "",
                ]
            ),
        )

        self._assert_strict_violation_codes(["missing-frontmatter-key"])

    def test_non_strict_mode_reports_without_failing_exit_code(self) -> None:
        self._seed_invalid_wiki()

        result = self._run_lint(strict=False)

        self.assertEqual(result.returncode, 0)
        self.assertIn("Found", result.stdout)

    def test_lint_command_does_not_mutate_wiki_files(self) -> None:
        self._seed_valid_wiki()
        before_snapshot = self._snapshot_wiki_files()

        result = self._run_lint(strict=True)
        after_snapshot = self._snapshot_wiki_files()

        self.assertEqual(result.returncode, 0)
        self.assertEqual(after_snapshot, before_snapshot)


if __name__ == "__main__":
    unittest.main()
