"""CLI tests for scripts.kb.lint_wiki."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
import unittest

from tests.kb.harnesses import KnowledgebaseWorkspaceTestCase

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "kb" / "lint_wiki.py"


class LintWikiCliTests(KnowledgebaseWorkspaceTestCase):
    RUNTIME_ROOT_NAME = ".runtime_lint_wiki"

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
        self.write_wiki_page(
            "index.md",
            self.build_process_page(
                "Knowledgebase Index",
                "- [Log](log.md)\n- [Source A](sources/source-a.md)",
            ),
        )
        self.write_wiki_page(
            "log.md",
            self.build_process_page("Knowledgebase Log", "- state changes appear here"),
        )
        self.write_wiki_page(
            "sources/source-a.md",
            self.build_process_page("Source A", "- [Index](../index.md)"),
        )

    def _seed_invalid_wiki(self) -> None:
        self.write_wiki_page(
            "index.md",
            self.build_process_page("Knowledgebase Index", "- [Missing](sources/missing.md)"),
        )
        self.write_wiki_page(
            "sources/orphan.md",
            self.build_process_page("Orphan", "This page is intentionally unreferenced."),
        )
        self.write_wiki_page(
            "sources/contradiction.md",
            self.build_process_page("Contradiction", "[CONTRADICTION] unresolved evidence conflict."),
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
            if line.startswith(" ") or line.startswith("\t"):
                continue  # skip hint lines (indented)
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
        self.write_wiki_page(
            "index.md",
            self.build_process_page(
                "Knowledgebase Index",
                '- [Source With Spaces](sources/source with spaces.md)',
            ),
        )
        self.write_wiki_page(
            "sources/source with spaces.md",
            self.build_process_page("Source With Spaces", "- [Index](../index.md)"),
        )

        result = self._run_lint(strict=True)

        self.assertEqual(result.returncode, 0)
        self.assertIn("Found 0 violation(s).", result.stdout)

    def test_strict_mode_accepts_internal_links_with_optional_title(self) -> None:
        self.write_wiki_page(
            "index.md",
            self.build_process_page(
                "Knowledgebase Index",
                '- [Source A](sources/source-a.md "Source A title")',
            ),
        )
        self.write_wiki_page(
            "sources/source-a.md",
            self.build_process_page("Source A", '- [Index](../index.md "Back to index")'),
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
        self.write_wiki_page(
            "index.md",
            self.build_process_page("Knowledgebase Index", "- [Escape](../outside.md)"),
        )

        self._assert_strict_violation_codes(["out-of-bounds-link"])

    def test_strict_mode_reports_missing_frontmatter_violation(self) -> None:
        self.write_wiki_page("index.md", "# Knowledgebase Index\n\nThis page omits frontmatter.\n")

        self._assert_strict_violation_codes(["missing-frontmatter"])

    def test_strict_mode_reports_missing_frontmatter_key_violation(self) -> None:
        self.write_wiki_page(
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
        self.write_wiki_page(
            "index.md",
            self.build_process_page(
                "Knowledgebase Index",
                "- [Log](log.md)\n- [Linked](sources/linked.md)",
            ),
        )
        self.write_wiki_page(
            "log.md",
            self.build_process_page("Knowledgebase Log", "- state changes appear here"),
        )
        outside_page = self.workspace / "outside.md"
        outside_page.write_text(
            self.build_process_page("Outside Page", "- external content"),
            encoding="utf-8",
        )
        linked_page = self.wiki_root / "sources" / "linked.md"
        linked_page.parent.mkdir(parents=True, exist_ok=True)
        linked_page.symlink_to(outside_page)

        result = self._run_lint(strict=True)

        self.assertEqual(result.returncode, 1)
        self.assertIn("symlinked-page", self._extract_violation_codes(result.stdout))

    def test_strict_mode_rejects_nested_topical_page_paths(self) -> None:
        self.write_wiki_page(
            "index.md",
            self.build_process_page(
                "Knowledgebase Index",
                "- [Log](log.md)\n- [Nested Concept](concepts/coverage/nested-concept.md)",
            ),
        )
        self.write_wiki_page(
            "log.md",
            self.build_process_page("Knowledgebase Log", "- state changes appear here"),
        )
        self.write_wiki_page(
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
        self.write_wiki_page(
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
        self.write_wiki_page(
            "index.md",
            self.build_process_page(
                "Knowledgebase Index",
                "- [Log](log.md)\n- [Source A](sources/source-a.md)",
            ),
        )
        self.write_wiki_page(
            "log.md",
            self.build_process_page("Knowledgebase Log", "- state changes appear here"),
        )
        artifact_path = self.workspace / "raw" / "processed" / "source-a.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("commit-bound bytes\n", encoding="utf-8")
        checksum = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        commit_sha = self._commit_all("seed authoritative source artifact")
        self.write_wiki_page(
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
        self.write_wiki_page(
            "index.md",
            self.build_process_page(
                "Knowledgebase Index",
                "- [Log](log.md)\n- [Source A](sources/source-a.md)",
            ),
        )
        self.write_wiki_page(
            "log.md",
            self.build_process_page("Knowledgebase Log", "- state changes appear here"),
        )
        artifact_path = self.workspace / "raw" / "processed" / "source-a.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("commit-bound bytes\n", encoding="utf-8")
        checksum = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        commit_sha = self._commit_all("seed authoritative source artifact")
        self.write_wiki_page(
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


class LintWikiNormalizationTests(unittest.TestCase):
    """Unit tests for internal normalization helpers (no subprocess)."""

    def test_normalize_link_target_empty_string_returns_none(self) -> None:
        from scripts.kb.lint_wiki import _normalize_link_target
        self.assertIsNone(_normalize_link_target(""))

    def test_normalize_link_target_whitespace_only_returns_none(self) -> None:
        from scripts.kb.lint_wiki import _normalize_link_target
        self.assertIsNone(_normalize_link_target("   "))

    def test_normalize_link_target_strips_angle_brackets(self) -> None:
        from scripts.kb.lint_wiki import _normalize_link_target
        result = _normalize_link_target("<wiki/sources/foo.md>")
        self.assertEqual(result, "wiki/sources/foo.md")

    def test_normalize_link_target_strips_link_title(self) -> None:
        from scripts.kb.lint_wiki import _normalize_link_target
        result = _normalize_link_target('wiki/foo.md "Some Title"')
        self.assertEqual(result, "wiki/foo.md")

    def test_normalize_link_target_strips_link_title_single_quotes(self) -> None:
        from scripts.kb.lint_wiki import _normalize_link_target
        result = _normalize_link_target("wiki/foo.md 'Some Title'")
        self.assertEqual(result, "wiki/foo.md")

    def test_normalize_link_target_strips_link_title_parens(self) -> None:
        from scripts.kb.lint_wiki import _normalize_link_target
        result = _normalize_link_target("wiki/foo.md (Some Title)")
        self.assertEqual(result, "wiki/foo.md")

    def test_normalize_link_target_external_https_returns_none(self) -> None:
        from scripts.kb.lint_wiki import _normalize_link_target
        self.assertIsNone(_normalize_link_target("https://example.com/page"))

    def test_normalize_link_target_external_http_returns_none(self) -> None:
        from scripts.kb.lint_wiki import _normalize_link_target
        self.assertIsNone(_normalize_link_target("http://example.com/page"))

    def test_normalize_link_target_custom_scheme_returns_none(self) -> None:
        from scripts.kb.lint_wiki import _normalize_link_target
        self.assertIsNone(_normalize_link_target("ftp://files.example.com/file"))

    def test_normalize_link_target_generic_scheme_returns_none(self) -> None:
        from scripts.kb.lint_wiki import _normalize_link_target
        self.assertIsNone(_normalize_link_target("repo://owner/repo/path@sha"))

    def test_normalize_link_target_javascript_returns_none(self) -> None:
        from scripts.kb.lint_wiki import _normalize_link_target
        self.assertIsNone(_normalize_link_target("javascript:void(0)"))

    def test_normalize_link_target_anchor_only_returns_none(self) -> None:
        from scripts.kb.lint_wiki import _normalize_link_target
        # After stripping the fragment, the path part is empty
        self.assertIsNone(_normalize_link_target("#section-anchor"))

    def test_normalize_link_target_strips_fragment(self) -> None:
        from scripts.kb.lint_wiki import _normalize_link_target
        result = _normalize_link_target("wiki/foo.md#section")
        self.assertEqual(result, "wiki/foo.md")

    def test_normalize_link_target_strips_query(self) -> None:
        from scripts.kb.lint_wiki import _normalize_link_target
        result = _normalize_link_target("wiki/foo.md?version=2")
        self.assertEqual(result, "wiki/foo.md")

    def test_normalize_link_target_non_md_extension_returns_none(self) -> None:
        from scripts.kb.lint_wiki import _normalize_link_target
        self.assertIsNone(_normalize_link_target("image.png"))

    def test_normalize_link_target_pdf_returns_none(self) -> None:
        from scripts.kb.lint_wiki import _normalize_link_target
        self.assertIsNone(_normalize_link_target("doc.pdf"))

    def test_normalize_link_target_md_extension_preserved(self) -> None:
        from scripts.kb.lint_wiki import _normalize_link_target
        result = _normalize_link_target("wiki/sources/foo.md")
        self.assertEqual(result, "wiki/sources/foo.md")


class LintWikiResolveTests(unittest.TestCase):
    """Unit tests for _resolve_internal_markdown_target."""

    def setUp(self) -> None:
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.wiki_root = Path(self._tmpdir) / "wiki"
        self.wiki_root.mkdir(parents=True)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_none_target_returns_none(self) -> None:
        from scripts.kb.lint_wiki import _resolve_internal_markdown_target
        source_page = self.wiki_root / "index.md"
        result = _resolve_internal_markdown_target(source_page, "", self.wiki_root)
        self.assertIsNone(result)

    def test_target_with_wiki_prefix_resolves_from_parent(self) -> None:
        from scripts.kb.lint_wiki import _resolve_internal_markdown_target
        source_page = self.wiki_root / "index.md"
        result = _resolve_internal_markdown_target(source_page, "wiki/sources/foo.md", self.wiki_root)
        expected = self.wiki_root.parent / "wiki" / "sources" / "foo.md"
        self.assertEqual(result, expected)

    def test_target_with_slash_prefix_resolves_from_wiki_root(self) -> None:
        from scripts.kb.lint_wiki import _resolve_internal_markdown_target
        source_page = self.wiki_root / "index.md"
        result = _resolve_internal_markdown_target(source_page, "/sources/bar.md", self.wiki_root)
        expected = self.wiki_root / "sources" / "bar.md"
        self.assertEqual(result, expected)

    def test_relative_target_resolves_from_source_parent(self) -> None:
        from scripts.kb.lint_wiki import _resolve_internal_markdown_target
        source_page = self.wiki_root / "sources" / "page.md"
        result = _resolve_internal_markdown_target(source_page, "../index.md", self.wiki_root)
        expected = self.wiki_root / "sources" / ".." / "index.md"
        self.assertEqual(result, expected)

    def test_no_suffix_candidate_adds_md_if_not_file(self) -> None:
        from scripts.kb.lint_wiki import _resolve_internal_markdown_target
        source_page = self.wiki_root / "index.md"
        # 'concepts/coverage' - no suffix, not an existing file
        result = _resolve_internal_markdown_target(source_page, "concepts/coverage", self.wiki_root)
        self.assertIsNotNone(result)
        self.assertTrue(str(result).endswith(".md"))

    def test_no_suffix_candidate_returns_as_is_if_file_exists(self) -> None:
        from scripts.kb.lint_wiki import _resolve_internal_markdown_target
        # Create a file with no extension
        no_ext_file = self.wiki_root / "mypage"
        no_ext_file.write_text("content")
        source_page = self.wiki_root / "index.md"
        result = _resolve_internal_markdown_target(source_page, "mypage", self.wiki_root)
        self.assertEqual(result, no_ext_file)

    def test_external_link_returns_none(self) -> None:
        from scripts.kb.lint_wiki import _resolve_internal_markdown_target
        source_page = self.wiki_root / "index.md"
        result = _resolve_internal_markdown_target(source_page, "https://example.com", self.wiki_root)
        self.assertIsNone(result)


class LintWikiDisplayPathTests(unittest.TestCase):
    """Unit tests for _display_path."""

    def setUp(self) -> None:
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.wiki_root = Path(self._tmpdir) / "wiki"
        self.wiki_root.mkdir()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_path_within_wiki_root_returns_relative(self) -> None:
        from scripts.kb.lint_wiki import _display_path
        page = self.wiki_root / "sources" / "foo.md"
        result = _display_path(page, self.wiki_root)
        self.assertEqual(result, "sources/foo.md")

    def test_path_outside_wiki_root_returns_absolute_str(self) -> None:
        from scripts.kb.lint_wiki import _display_path
        page = Path(self._tmpdir) / "outside" / "bar.md"
        result = _display_path(page, self.wiki_root)
        self.assertIn("outside", result)
        self.assertNotIn("sources", result)


class LintWikiDirectTests(KnowledgebaseWorkspaceTestCase):
    """Tests that call lint_wiki() directly (not via subprocess) for coverage."""

    RUNTIME_ROOT_NAME = ".runtime_lint_wiki_direct"

    def _write_valid_wiki(self) -> None:
        self.write_wiki_page(
            "index.md",
            self.build_process_page(
                "Index",
                "- [Log](log.md)\n- [Source A](sources/source-a.md)",
            ),
        )
        self.write_wiki_page(
            "log.md",
            self.build_process_page("Log", "- entries"),
        )
        self.write_wiki_page(
            "sources/source-a.md",
            self.build_process_page("Source A", "- [Index](../index.md)"),
        )

    def test_direct_lint_clean_wiki_returns_no_violations(self) -> None:
        from scripts.kb.lint_wiki import lint_wiki
        self._write_valid_wiki()
        violations = lint_wiki(self.wiki_root)
        self.assertEqual(violations, [])

    def test_direct_lint_detects_orphan_page(self) -> None:
        from scripts.kb.lint_wiki import lint_wiki
        self._write_valid_wiki()
        self.write_wiki_page(
            "sources/orphan.md",
            self.build_process_page("Orphan", "No links to me."),
        )
        violations = lint_wiki(self.wiki_root)
        codes = [v.code for v in violations]
        self.assertIn("orphan-page", codes)

    def test_direct_lint_skip_orphan_check(self) -> None:
        from scripts.kb.lint_wiki import lint_wiki
        self._write_valid_wiki()
        self.write_wiki_page(
            "sources/orphan.md",
            self.build_process_page("Orphan", "No links to me."),
        )
        violations = lint_wiki(self.wiki_root, skip_orphan_check=True)
        codes = [v.code for v in violations]
        self.assertNotIn("orphan-page", codes)

    def test_direct_lint_detects_missing_frontmatter(self) -> None:
        from scripts.kb.lint_wiki import lint_wiki
        self.write_wiki_page("index.md", self.build_process_page("Index", "- [Log](log.md)"))
        self.write_wiki_page("log.md", self.build_process_page("Log", ""))
        self.write_wiki_page("sources/nofm.md", "# No Frontmatter\n\nJust body text.\n")
        violations = lint_wiki(self.wiki_root, skip_orphan_check=True)
        codes = [v.code for v in violations]
        self.assertIn("missing-frontmatter", codes)

    def test_direct_lint_detects_missing_frontmatter_key(self) -> None:
        from scripts.kb.lint_wiki import lint_wiki
        self.write_wiki_page("index.md", self.build_process_page("Index", "- [Log](log.md)"))
        self.write_wiki_page("log.md", self.build_process_page("Log", ""))
        # Page missing the 'updated_at' key
        content = "---\ntype: process\ntitle: \"Test\"\nsources: []\n---\n\n# Test\n"
        self.write_wiki_page("sources/missingkey.md", content)
        violations = lint_wiki(self.wiki_root, skip_orphan_check=True)
        codes = [v.code for v in violations]
        self.assertIn("missing-frontmatter-key", codes)

    def test_direct_lint_detects_contradiction_marker(self) -> None:
        from scripts.kb.lint_wiki import lint_wiki
        self.write_wiki_page("index.md", self.build_process_page("Index", "- [Log](log.md)"))
        self.write_wiki_page("log.md", self.build_process_page("Log", ""))
        self.write_wiki_page(
            "sources/conflict.md",
            self.build_process_page(
                "Conflict", "Evidence says A but also B. [CONTRADICTION]"
            ),
        )
        violations = lint_wiki(self.wiki_root, skip_orphan_check=True)
        codes = [v.code for v in violations]
        self.assertIn("unresolved-contradiction-marker", codes)

    def test_direct_lint_detects_broken_internal_link(self) -> None:
        from scripts.kb.lint_wiki import lint_wiki
        self.write_wiki_page(
            "index.md",
            self.build_process_page(
                "Index",
                "- [Log](log.md)\n- [Missing](sources/does-not-exist.md)",
            ),
        )
        self.write_wiki_page("log.md", self.build_process_page("Log", ""))
        violations = lint_wiki(self.wiki_root, skip_orphan_check=True)
        codes = [v.code for v in violations]
        self.assertIn("missing-link-target", codes)

    def test_direct_lint_context_md_skipped(self) -> None:
        from scripts.kb.lint_wiki import lint_wiki
        # CONTEXT.md should be silently skipped; no violations from it
        self.write_wiki_page("index.md", self.build_process_page("Index", "- [Log](log.md)"))
        self.write_wiki_page("log.md", self.build_process_page("Log", ""))
        (self.wiki_root / "CONTEXT.md").write_text(
            "scope: wiki\nlast_updated: 2024-01-01\n\n## Terms\nfoo bar\n",
            encoding="utf-8",
        )
        violations = lint_wiki(self.wiki_root, skip_orphan_check=True)
        # Violations should not reference CONTEXT.md
        for v in violations:
            self.assertNotEqual(v.page.name, "CONTEXT.md")

    def test_direct_lint_symlinked_page_detected(self) -> None:
        from scripts.kb.lint_wiki import lint_wiki
        import os
        self.write_wiki_page("index.md", self.build_process_page("Index", "- [Log](log.md)"))
        self.write_wiki_page("log.md", self.build_process_page("Log", ""))
        # Create a real page and symlink it
        real_page = self.wiki_root / "sources" / "real.md"
        real_page.parent.mkdir(parents=True, exist_ok=True)
        real_page.write_text(self.build_process_page("Real"), encoding="utf-8")
        sym_page = self.wiki_root / "sources" / "symlink.md"
        os.symlink(real_page, sym_page)
        violations = lint_wiki(self.wiki_root, skip_orphan_check=True)
        codes = [v.code for v in violations]
        self.assertIn("symlinked-page", codes)

    def test_direct_lint_out_of_bounds_link_detected(self) -> None:
        from scripts.kb.lint_wiki import lint_wiki
        # A link with relative path traversal that escapes the wiki root
        # e.g., page in wiki/ links to ../../outside.md → resolves outside wiki/
        self.write_wiki_page("index.md", self.build_process_page("Index", "- [Log](log.md)"))
        self.write_wiki_page("log.md", self.build_process_page("Log", ""))
        # Link traverses up two levels from wiki/sources/ to escape wiki/
        self.write_wiki_page(
            "sources/escape.md",
            self.build_process_page("Escape", "- [OutOfBounds](../../README.md)"),
        )
        violations = lint_wiki(self.wiki_root, skip_orphan_check=True)
        codes = [v.code for v in violations]
        self.assertIn("out-of-bounds-link", codes)

    def test_direct_lint_authoritative_sourceref_invalid(self) -> None:
        from scripts.kb.lint_wiki import lint_wiki
        self.write_wiki_page("index.md", self.build_process_page("Index", "- [Log](log.md)"))
        self.write_wiki_page("log.md", self.build_process_page("Log", ""))
        # Page with a placeholder (non-authoritative) SourceRef triggers invalid-sourceref
        placeholder_ref = "repo://owner/repo/path@" + "0" * 40 + "#anchor?sha256=" + "a" * 64
        content = "\n".join([
            "---",
            "type: source",
            'title: "Test Source"',
            "status: active",
            f"sources:\n  - {placeholder_ref}",
            "open_questions: []",
            "confidence: 3",
            "sensitivity: internal",
            'updated_at: "2024-01-01T00:00:00Z"',
            "tags:",
            "  - test",
            "---",
            "",
            "# Test Source",
            "",
        ])
        self.write_wiki_page("sources/test-source.md", content)
        violations = lint_wiki(
            self.wiki_root,
            skip_orphan_check=True,
            authoritative_sourcerefs=True,
            repo_owner="owner",
            repo_name="repo",
        )
        codes = [v.code for v in violations]
        self.assertIn("invalid-sourceref", codes)


        from scripts.kb.lint_wiki import lint_wiki
        self.write_wiki_page("index.md", self.build_process_page("Index", "- [Log](log.md)"))
        self.write_wiki_page("log.md", self.build_process_page("Log", ""))
        self.write_wiki_page(
            "concepts/subdir/deep-concept.md",
            self.build_process_page("Deep Concept", ""),
        )
        violations = lint_wiki(self.wiki_root, skip_orphan_check=True)
        codes = [v.code for v in violations]
        self.assertIn("nested-topical-page", codes)


class LintWikiMainTests(KnowledgebaseWorkspaceTestCase):
    """Tests for lint_wiki.main() error paths (no subprocess)."""

    RUNTIME_ROOT_NAME = ".runtime_lint_wiki_main"

    def test_main_nonexistent_wiki_root_returns_2(self) -> None:
        from scripts.kb.lint_wiki import main
        result = main(["--wiki-root", str(self.wiki_root / "does-not-exist"), "--strict"])
        self.assertEqual(result, 2)

    def test_main_authoritative_without_owner_returns_2(self) -> None:
        from scripts.kb.lint_wiki import main
        self.wiki_root.mkdir(parents=True, exist_ok=True)
        result = main(["--wiki-root", str(self.wiki_root), "--authoritative-sourcerefs", "--repo-name", "myrepo"])
        self.assertEqual(result, 2)

    def test_main_authoritative_without_name_returns_2(self) -> None:
        from scripts.kb.lint_wiki import main
        self.wiki_root.mkdir(parents=True, exist_ok=True)
        result = main(["--wiki-root", str(self.wiki_root), "--authoritative-sourcerefs", "--repo-owner", "myowner"])
        self.assertEqual(result, 2)

    def test_main_strict_with_violations_returns_1(self) -> None:
        from scripts.kb.lint_wiki import main
        self.write_wiki_page(
            "index.md",
            self.build_process_page("Index", "- [Log](log.md)\n- [Missing](sources/ghost.md)"),
        )
        self.write_wiki_page("log.md", self.build_process_page("Log", ""))
        result = main(["--wiki-root", str(self.wiki_root), "--strict"])
        self.assertEqual(result, 1)

    def test_main_non_strict_with_violations_returns_0(self) -> None:
        from scripts.kb.lint_wiki import main
        self.write_wiki_page(
            "index.md",
            self.build_process_page("Index", "- [Log](log.md)\n- [Missing](sources/ghost.md)"),
        )
        self.write_wiki_page("log.md", self.build_process_page("Log", ""))
        result = main(["--wiki-root", str(self.wiki_root)])
        self.assertEqual(result, 0)

    def test_main_prints_remediation_hint_for_known_violation_code(self) -> None:
        """main() prints a remediation hint for violations with known codes."""
        import io
        from contextlib import redirect_stdout
        from scripts.kb.lint_wiki import main
        # Create a page with no frontmatter - produces "missing-frontmatter" which has a hint
        self.write_wiki_page("index.md", self.build_process_page("Index", "- [Log](log.md)"))
        self.write_wiki_page("log.md", self.build_process_page("Log", ""))
        self.write_wiki_page("sources/nofm.md", "# No Frontmatter\n\nJust body text.\n")
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["--wiki-root", str(self.wiki_root), "--skip-orphan-check"])
        output = buf.getvalue()
        # Should include the remediation hint (indented line) for missing-frontmatter
        self.assertIn("FIX:", output)

    def test_main_clean_wiki_strict_returns_0(self) -> None:
        from scripts.kb.lint_wiki import main
        self.write_wiki_page("index.md", self.build_process_page("Index", "- [Log](log.md)"))
        self.write_wiki_page("log.md", self.build_process_page("Log", ""))
        result = main(["--wiki-root", str(self.wiki_root), "--strict", "--skip-orphan-check"])
        self.assertEqual(result, 0)


class LintWikiOptimizationRegressionTests(KnowledgebaseWorkspaceTestCase):
    """Regression tests for #18: stat reduction and valid_page_paths optimization.

    These tests guard against regressions introduced when changing how
    _collect_valid_pages and _validate_page_content resolve link targets.
    """

    RUNTIME_ROOT_NAME = ".runtime_lint_wiki_opt"

    def test_output_is_deterministic_across_multiple_runs(self) -> None:
        """lint_wiki output ordering must be stable regardless of filesystem order."""
        from scripts.kb.lint_wiki import lint_wiki
        self.write_wiki_page("index.md", self.build_process_page("Index", "- [Log](log.md)\n- [Z Page](sources/z.md)\n- [A Page](sources/a.md)"))
        self.write_wiki_page("log.md", self.build_process_page("Log", ""))
        self.write_wiki_page("sources/a.md", self.build_process_page("A Page", ""))
        self.write_wiki_page("sources/z.md", self.build_process_page("Z Page", ""))

        run1 = lint_wiki(self.wiki_root, skip_orphan_check=True)
        run2 = lint_wiki(self.wiki_root, skip_orphan_check=True)
        self.assertEqual(
            [(v.code, str(v.page)) for v in run1],
            [(v.code, str(v.page)) for v in run2],
        )

    def test_broken_link_detected_with_valid_page_paths_optimization(self) -> None:
        """Broken links must be caught even when valid_page_paths frozenset is used."""
        from scripts.kb.lint_wiki import lint_wiki
        self.write_wiki_page("index.md", self.build_process_page("Index", "- [Log](log.md)\n- [Ghost](sources/ghost.md)"))
        self.write_wiki_page("log.md", self.build_process_page("Log", ""))

        violations = lint_wiki(self.wiki_root, skip_orphan_check=True)
        codes = [v.code for v in violations]
        self.assertIn("missing-link-target", codes)

    def test_valid_links_not_flagged_with_valid_page_paths_optimization(self) -> None:
        """Valid internal links must not be flagged as broken."""
        from scripts.kb.lint_wiki import lint_wiki
        self.write_wiki_page("index.md", self.build_process_page("Index", "- [Log](log.md)\n- [Concept](concepts/c.md)"))
        self.write_wiki_page("log.md", self.build_process_page("Log", ""))
        self.write_wiki_page("concepts/c.md", self.build_process_page("C", ""))

        violations = lint_wiki(self.wiki_root, skip_orphan_check=True)
        self.assertFalse(
            any(v.code == "missing-link-target" for v in violations),
            f"Unexpected broken-link violations: {[v for v in violations if v.code == 'missing-link-target']}",
        )

    def test_symlinked_pages_still_detected_after_lstat_optimization(self) -> None:
        """Symlinked pages must still produce symlinked-page violations after lstat change."""
        import os
        from scripts.kb.lint_wiki import lint_wiki

        real = self.wiki_root / "concepts" / "real.md"
        real.parent.mkdir(parents=True, exist_ok=True)
        real.write_text(self.build_process_page("Real", ""), encoding="utf-8")

        link = self.wiki_root / "concepts" / "linked.md"
        os.symlink(real, link)

        self.write_wiki_page("index.md", self.build_process_page("Index", "- [Log](log.md)"))
        self.write_wiki_page("log.md", self.build_process_page("Log", ""))

        violations = lint_wiki(self.wiki_root, skip_orphan_check=True)
        codes = [v.code for v in violations]
        self.assertIn("symlinked-page", codes)


if __name__ == "__main__":
    unittest.main()
