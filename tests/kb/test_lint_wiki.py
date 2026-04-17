"""CLI tests for scripts.kb.lint_wiki."""

from __future__ import annotations

import hashlib
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

    def _run_lint(
        self,
        *,
        strict: bool,
        skip_orphan_check: bool = False,
        authoritative_sourcerefs: bool = False,
        repo_owner: str | None = None,
        repo_name: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(SCRIPT_PATH),
            "--wiki-root",
            str(self.wiki_root),
        ]
        if strict:
            command.append("--strict")
        if skip_orphan_check:
            command.append("--skip-orphan-check")
        if authoritative_sourcerefs:
            command.append("--authoritative-sourcerefs")
        if repo_owner is not None:
            command.extend(["--repo-owner", repo_owner])
        if repo_name is not None:
            command.extend(["--repo-name", repo_name])

        return subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def _git(self, *args: str, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.workspace,
            check=True,
            capture_output=capture_output,
            text=True,
        )

    def _init_git_repo(self) -> None:
        self._git("init")
        self._git("config", "user.name", "Test User")
        self._git("config", "user.email", "test@example.com")

    def _commit_all(self, message: str) -> str:
        self._git("add", ".")
        self._git("commit", "-m", message)
        return self._git("rev-parse", "HEAD", capture_output=True).stdout.strip()

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

    def test_strict_mode_accepts_internal_links_with_spaces_in_target(self) -> None:
        self._write_page(
            "index.md",
            self._build_page(
                "Knowledgebase Index",
                '- [Source With Spaces](sources/source with spaces.md)',
            ),
        )
        self._write_page(
            "sources/source with spaces.md",
            self._build_page("Source With Spaces", "- [Index](../index.md)"),
        )

        result = self._run_lint(strict=True)

        self.assertEqual(result.returncode, 0)
        self.assertIn("Found 0 violation(s).", result.stdout)

    def test_strict_mode_accepts_internal_links_with_optional_title(self) -> None:
        self._write_page(
            "index.md",
            self._build_page(
                "Knowledgebase Index",
                '- [Source A](sources/source-a.md "Source A title")',
            ),
        )
        self._write_page(
            "sources/source-a.md",
            self._build_page("Source A", '- [Index](../index.md "Back to index")'),
        )

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

    def test_skip_orphan_check_allows_stale_index_validation(self) -> None:
        self._seed_invalid_wiki()

        result = self._run_lint(strict=True, skip_orphan_check=True)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            self._extract_violation_codes(result.stdout),
            [
                "missing-link-target",
                "unresolved-contradiction-marker",
            ],
        )

    def test_strict_mode_rejects_symlinked_markdown_page(self) -> None:
        self._write_page(
            "index.md",
            self._build_page(
                "Knowledgebase Index",
                "- [Log](log.md)\n- [Linked](sources/linked.md)",
            ),
        )
        self._write_page(
            "log.md",
            self._build_page("Knowledgebase Log", "- state changes appear here"),
        )
        outside_page = self.workspace / "outside.md"
        outside_page.write_text(
            self._build_page("Outside Page", "- external content"),
            encoding="utf-8",
        )
        linked_page = self.wiki_root / "sources" / "linked.md"
        linked_page.parent.mkdir(parents=True, exist_ok=True)
        linked_page.symlink_to(outside_page)

        result = self._run_lint(strict=True)

        self.assertEqual(result.returncode, 1)
        self.assertIn("symlinked-page", self._extract_violation_codes(result.stdout))

    def test_strict_mode_rejects_nested_topical_page_paths(self) -> None:
        self._write_page(
            "index.md",
            self._build_page(
                "Knowledgebase Index",
                "- [Log](log.md)\n- [Nested Concept](concepts/coverage/nested-concept.md)",
            ),
        )
        self._write_page(
            "log.md",
            self._build_page("Knowledgebase Log", "- state changes appear here"),
        )
        self._write_page(
            "concepts/coverage/nested-concept.md",
            "\n".join(
                [
                    "---",
                    "type: concept",
                    'title: "Nested Concept"',
                    "status: active",
                    "sources: []",
                    "open_questions: []",
                    "confidence: 3",
                    "sensitivity: internal",
                    'updated_at: "2024-01-01T00:00:00Z"',
                    "tags: [test]",
                    "---",
                    "",
                    "# Nested Concept",
                    "",
                    "- [Index](../../index.md)",
                    "",
                ]
            ),
        )

        self._assert_strict_violation_codes(["nested-topical-page"])

    def test_authoritative_sourceref_mode_rejects_placeholder_source_refs(self) -> None:
        self._seed_valid_wiki()
        self._write_page(
            "sources/source-a.md",
            "\n".join(
                [
                    "---",
                    "type: source",
                    'title: "Source A"',
                    "status: active",
                    "sources:",
                    '  - "repo://local/repo/raw/processed/source-a.md@0000000000000000000000000000000000000000#asset?sha256='
                    + ("a" * 64)
                    + '"',
                    "open_questions: []",
                    "confidence: 5",
                    "sensitivity: internal",
                    'updated_at: "2024-01-01T00:00:00Z"',
                    "tags: [source]",
                    "---",
                    "",
                    "# Source A",
                    "",
                    "- [Index](../index.md)",
                    "",
                ]
            ),
        )

        result = self._run_lint(
            strict=True,
            authoritative_sourcerefs=True,
            repo_owner="local",
            repo_name="repo",
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid-sourceref", self._extract_violation_codes(result.stdout))
        self.assertIn("placeholder_git_sha", result.stdout)

    def test_authoritative_sourceref_mode_accepts_commit_bound_source_refs(self) -> None:
        self._init_git_repo()
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
        artifact_path = self.workspace / "raw" / "processed" / "source-a.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("commit-bound bytes\n", encoding="utf-8")
        checksum = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        commit_sha = self._commit_all("seed authoritative source artifact")
        self._write_page(
            "sources/source-a.md",
            "\n".join(
                [
                    "---",
                    "type: source",
                    'title: "Source A"',
                    "status: active",
                    "sources:",
                    f'  - "repo://local/repo/raw/processed/source-a.md@{commit_sha}#asset?sha256={checksum}"',
                    "open_questions: []",
                    "confidence: 5",
                    "sensitivity: internal",
                    'updated_at: "2024-01-01T00:00:00Z"',
                    "tags: [source]",
                    "---",
                    "",
                    "# Source A",
                    "",
                    "- [Index](../index.md)",
                    "",
                ]
            ),
        )
        self._commit_all("seed authoritative source page")

        result = self._run_lint(
            strict=True,
            authoritative_sourcerefs=True,
            repo_owner="local",
            repo_name="repo",
        )

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("Found 0 violation(s).", result.stdout)

    def test_authoritative_sourceref_mode_rejects_foreign_repo_identity(self) -> None:
        self._init_git_repo()
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
        artifact_path = self.workspace / "raw" / "processed" / "source-a.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("commit-bound bytes\n", encoding="utf-8")
        checksum = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        commit_sha = self._commit_all("seed authoritative source artifact")
        self._write_page(
            "sources/source-a.md",
            "\n".join(
                [
                    "---",
                    "type: source",
                    'title: "Source A"',
                    "status: active",
                    "sources:",
                    f'  - "repo://foreign/repo/raw/processed/source-a.md@{commit_sha}#asset?sha256={checksum}"',
                    "open_questions: []",
                    "confidence: 5",
                    "sensitivity: internal",
                    'updated_at: "2024-01-01T00:00:00Z"',
                    "tags: [source]",
                    "---",
                    "",
                    "# Source A",
                    "",
                    "- [Index](../index.md)",
                    "",
                ]
            ),
        )
        self._commit_all("seed authoritative source page")

        result = self._run_lint(
            strict=True,
            authoritative_sourcerefs=True,
            repo_owner="local",
            repo_name="repo",
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid-sourceref", self._extract_violation_codes(result.stdout))
        self.assertIn("invalid_repo", result.stdout)


    def test_read_failure_handled_in_thread_pool(self) -> None:
        self._seed_valid_wiki()

        from scripts.kb.lint_wiki import lint_wiki
        from unittest.mock import patch

        with patch("pathlib.Path.read_text") as mock_read:
            mock_read.side_effect = PermissionError("Simulated unreadable file")
            with self.assertRaises(PermissionError):
                lint_wiki(self.wiki_root)

    def test_lint_command_does_not_mutate_wiki_files(self) -> None:
        self._seed_valid_wiki()
        before_snapshot = self._snapshot_wiki_files()

        result = self._run_lint(strict=True)
        after_snapshot = self._snapshot_wiki_files()

        self.assertEqual(result.returncode, 0)
        self.assertEqual(after_snapshot, before_snapshot)


if __name__ == "__main__":
    unittest.main()
