"""Tests for deterministic wiki index generation and write policy behavior."""

from __future__ import annotations

import contextlib
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts.kb import update_index
from scripts.kb import write_utils

from tests.kb.harnesses import KnowledgebaseWorkspaceTestCase


REPO_ROOT = Path(__file__).resolve().parents[2]
UPDATE_INDEX_SCRIPT = REPO_ROOT / "scripts" / "kb" / "update_index.py"


class UpdateIndexCommandTests(KnowledgebaseWorkspaceTestCase):
    WIKI_SECTIONS = ("sources", "entities", "concepts", "analyses")

    def setUp(self) -> None:
        super().setUp()

        (self.workspace / "raw").mkdir(parents=True, exist_ok=True)
        (self.workspace / "raw" / "sentinel.txt").write_text(
            "raw-is-immutable\n", encoding="utf-8"
        )

        (self.wiki_root / "index.md").write_text("stale-index\n", encoding="utf-8")
        (self.wiki_root / ".kb_write.lock").write_text("", encoding="utf-8")
        (self.wiki_root / "log.md").write_text(
            "log-should-not-change\n", encoding="utf-8"
        )

        self.write_wiki_page("sources/zeta-source.md", self._build_page("Zeta Source", "source", "2"))
        self.write_wiki_page("sources/alpha-source.md", self._build_page("Alpha Source", "source", "4"))
        self.write_wiki_page("entities/beneficiary.md", self._build_page("Beneficiary", "entity", "5"))
        self.write_wiki_page(
            "concepts/network-adequacy.md", self._build_page("Network Adequacy", "concept", "3")
        )
        self.write_wiki_page(
            "analyses/prior-auth-review.md", self._build_page("Prior Auth Review", "analysis", "4")
        )

    def _build_page(self, title: str, page_type: str, confidence: str) -> str:
        return f"""---
type: {page_type}
title: "{title}"
status: active
sources: []
open_questions: []
confidence: {confidence}
sensitivity: internal
updated_at: "2024-01-01T00:00:00Z"
tags:
  - test
---

# {title}

Fixture page.
"""

    def _run_command(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = update_index.main(list(args))
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def _run_cli_command(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(REPO_ROOT)
            if not existing_pythonpath
            else f"{REPO_ROOT}{os.pathsep}{existing_pythonpath}"
        )
        return subprocess.run(
            [sys.executable, str(UPDATE_INDEX_SCRIPT), *args],
            capture_output=True,
            check=False,
            cwd=self.workspace,
            env=env,
            text=True,
        )

    def _snapshot_hashes(self) -> dict[str, str]:
        digest_map: dict[str, str] = {}
        for file_path in sorted(self.workspace.rglob("*")):
            if not file_path.is_file():
                continue
            digest_map[file_path.relative_to(self.workspace).as_posix()] = (
                hashlib.sha256(file_path.read_bytes()).hexdigest()
            )
        return digest_map

    def test_preview_is_deterministic_and_read_only(self) -> None:
        before = self._snapshot_hashes()

        first_code, first_stdout, first_stderr = self._run_command(
            "--wiki-root",
            str(self.wiki_root),
        )
        second_code, second_stdout, second_stderr = self._run_command(
            "--wiki-root",
            str(self.wiki_root),
        )

        self.assertEqual(first_code, 0)
        self.assertEqual(second_code, 0)
        self.assertEqual(first_stderr, "")
        self.assertEqual(second_stderr, "")
        self.assertEqual(first_stdout, second_stdout)
        self.assertEqual(
            first_stdout, update_index.generate_index_content(self.wiki_root)
        )
        self.assertEqual(before, self._snapshot_hashes())

    def test_write_updates_only_index_file_when_needed(self) -> None:
        before = self._snapshot_hashes()

        exit_code, stdout, stderr = self._run_command(
            "--wiki-root",
            str(self.wiki_root),
            "--write",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout, "written\n")

        after = self._snapshot_hashes()
        changed_paths = {
            path
            for path in set(before) | set(after)
            if before.get(path) != after.get(path)
        }
        self.assertEqual(changed_paths, {"wiki/index.md"})
        self.assertEqual(
            (self.wiki_root / "index.md").read_text(encoding="utf-8"),
            update_index.generate_index_content(self.wiki_root),
        )

    def test_check_mode_fails_closed_when_index_is_stale(self) -> None:
        before = self._snapshot_hashes()

        exit_code, stdout, stderr = self._run_command(
            "--wiki-root",
            str(self.wiki_root),
            "--check",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout, "drifted\n")
        self.assertEqual(before, self._snapshot_hashes())

    def test_check_mode_passes_when_index_is_current(self) -> None:
        generated = update_index.generate_index_content(self.wiki_root)
        (self.wiki_root / "index.md").write_text(generated, encoding="utf-8")
        before = self._snapshot_hashes()

        exit_code, stdout, stderr = self._run_command(
            "--wiki-root",
            str(self.wiki_root),
            "--check",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout, "unchanged\n")
        self.assertEqual(before, self._snapshot_hashes())

    def test_relative_wiki_root_cli_check_succeeds_from_workspace_root(self) -> None:
        generated = update_index.generate_index_content(self.wiki_root)
        (self.wiki_root / "index.md").write_text(generated, encoding="utf-8")

        completed = self._run_cli_command("--wiki-root", "wiki", "--check")

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "unchanged\n")
        self.assertEqual(completed.stderr, "")

    def test_write_is_noop_when_index_is_already_current(self) -> None:
        generated = update_index.generate_index_content(self.wiki_root)
        (self.wiki_root / "index.md").write_text(generated, encoding="utf-8")
        before = self._snapshot_hashes()

        first_code, first_stdout, first_stderr = self._run_command(
            "--wiki-root",
            str(self.wiki_root),
            "--write",
        )
        second_code, second_stdout, second_stderr = self._run_command(
            "--wiki-root",
            str(self.wiki_root),
            "--write",
        )

        self.assertEqual(first_code, 0)
        self.assertEqual(second_code, 0)
        self.assertEqual(first_stderr, "")
        self.assertEqual(second_stderr, "")
        self.assertEqual(first_stdout, "unchanged\n")
        self.assertEqual(second_stdout, "unchanged\n")
        self.assertEqual(before, self._snapshot_hashes())

    def test_write_preserves_existing_index_when_atomic_replace_fails(self) -> None:
        before = self._snapshot_hashes()
        stale_index = (self.wiki_root / "index.md").read_text(encoding="utf-8")

        with patch("scripts.kb.update_index.os.replace", side_effect=OSError("boom")):
            exit_code, stdout, stderr = self._run_command(
                "--wiki-root",
                str(self.wiki_root),
                "--write",
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("unable to write index", stderr)
        self.assertEqual(
            (self.wiki_root / "index.md").read_text(encoding="utf-8"),
            stale_index,
        )
        self.assertFalse((self.wiki_root / "index.md.tmp").exists())
        after = self._snapshot_hashes()
        self.assertEqual(before, after)

    def test_write_rejects_preexisting_temp_symlink(self) -> None:
        external_target = self.workspace / "outside-target.md"
        external_target.write_text("external-target\n", encoding="utf-8")
        temp_index_path = self.wiki_root / "index.md.tmp"
        temp_index_path.symlink_to(external_target)
        stale_index = (self.wiki_root / "index.md").read_text(encoding="utf-8")

        exit_code, stdout, stderr = self._run_command(
            "--wiki-root",
            str(self.wiki_root),
            "--write",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("unable to write index", stderr)
        self.assertEqual(external_target.read_text(encoding="utf-8"), "external-target\n")
        self.assertEqual((self.wiki_root / "index.md").read_text(encoding="utf-8"), stale_index)
        self.assertTrue(temp_index_path.is_symlink())

    def test_write_fails_closed_when_write_lock_is_held(self) -> None:
        stale_index = (self.wiki_root / "index.md").read_text(encoding="utf-8")

        with write_utils.exclusive_write_lock(self.workspace):
            completed = self._run_cli_command("--wiki-root", "wiki", "--write")

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, "")
        self.assertIn("lock_unavailable", completed.stderr)
        self.assertIn(".kb_write.lock", completed.stderr)
        self.assertEqual(
            (self.wiki_root / "index.md").read_text(encoding="utf-8"),
            stale_index,
        )

    def test_generate_index_rejects_symlinked_markdown_page(self) -> None:
        outside_page = self.workspace / "outside-source.md"
        outside_page.write_text(
            "\n".join(
                [
                    "---",
                    "type: source",
                    'title: "Outside Source"',
                    "status: active",
                    "sources: []",
                    "open_questions: []",
                    "confidence: 1",
                    "sensitivity: internal",
                    'updated_at: "2024-01-01T00:00:00Z"',
                    "tags:",
                    "  - test",
                    "---",
                ]
            ),
            encoding="utf-8",
        )
        linked_page = self.wiki_root / "sources" / "outside-source.md"
        linked_page.symlink_to(outside_page)

        with self.assertRaises(update_index.IndexGenerationError) as ctx:
            update_index.generate_index_content(self.wiki_root)

        self.assertIn("symlinked markdown pages are not allowed", str(ctx.exception))

    def test_generate_index_rejects_nested_topical_page(self) -> None:
        self.write_wiki_page(
            "concepts/coverage/nested-concept.md",
            self._build_page("Nested Concept", "concept", "3"),
        )

        with self.assertRaises(update_index.IndexGenerationError) as ctx:
            update_index.generate_index_content(self.wiki_root)

        self.assertIn("nested topical markdown pages are not allowed", str(ctx.exception))

    def test_cli_check_fails_closed_for_nested_topical_page(self) -> None:
        self.write_wiki_page(
            "entities/medicare/beneficiary.md",
            self._build_page("Nested Beneficiary", "entity", "5"),
        )

        completed = self._run_cli_command("--wiki-root", "wiki", "--check")

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, "")
        self.assertIn("nested topical markdown pages are not allowed", completed.stderr)

    def test_pool_parse_error(self) -> None:
        wiki_root = self.workspace / "test_wiki_root"
        wiki_root.mkdir(exist_ok=True)

        source_root = wiki_root / "sources"
        source_root.mkdir(exist_ok=True)

        # simulate multiple files to test executor parsing
        for i in range(55):
            page = source_root / f"good{i}.md"
            page.write_text(
                f"""---
type: source
title: "Good {i}"
status: active
sources: []
open_questions: []
confidence: 1
sensitivity: internal
updated_at: "2024-01-01T00:00:00Z"
tags:
  - test
---""",
                encoding="utf-8",
            )

        page = source_root / "bad.md"
        page.write_text("---bad", encoding="utf-8")

        with self.assertRaises(update_index.IndexGenerationError):
            update_index.generate_index_content(wiki_root)

        exit_code, stdout, stderr = self._run_command(
            "--wiki-root",
            str(wiki_root),
            "--write",
        )

        self.assertEqual(exit_code, 1)
        self.assertIn(
            "sources/bad.md: missing YAML frontmatter start delimiter", stderr
        )

        index_path = wiki_root / "index.md"
        self.assertFalse(index_path.exists())


if __name__ == "__main__":
    unittest.main()
