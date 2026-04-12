"""Tests for deterministic wiki index generation and write policy behavior."""

from __future__ import annotations

import contextlib
import hashlib
import io
from pathlib import Path
import shutil
import unittest

from scripts.kb import update_index


class UpdateIndexCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = Path(__file__).resolve().parent / ".runtime_update_index"
        if self.workspace.exists():
            shutil.rmtree(self.workspace)

        self.wiki_root = self.workspace / "wiki"
        for directory in ("sources", "entities", "concepts", "analyses"):
            (self.wiki_root / directory).mkdir(parents=True, exist_ok=True)

        (self.workspace / "raw").mkdir(parents=True, exist_ok=True)
        (self.workspace / "raw" / "sentinel.txt").write_text("raw-is-immutable\n", encoding="utf-8")

        (self.wiki_root / "index.md").write_text("stale-index\n", encoding="utf-8")
        (self.wiki_root / "log.md").write_text("log-should-not-change\n", encoding="utf-8")

        self._write_page("sources/zeta-source.md", "Zeta Source", "source", "2")
        self._write_page("sources/alpha-source.md", "Alpha Source", "source", "4")
        self._write_page("entities/beneficiary.md", "Beneficiary", "entity", "5")
        self._write_page("concepts/network-adequacy.md", "Network Adequacy", "concept", "3")
        self._write_page("analyses/prior-auth-review.md", "Prior Auth Review", "analysis", "4")

    def tearDown(self) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)

    def _write_page(
        self,
        relative_path: str,
        title: str,
        page_type: str,
        confidence: str,
    ) -> None:
        page_path = self.wiki_root / relative_path
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            f"""---
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
""",
            encoding="utf-8",
        )

    def _run_command(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = update_index.main(list(args))
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def _snapshot_hashes(self) -> dict[str, str]:
        digest_map: dict[str, str] = {}
        for file_path in sorted(self.workspace.rglob("*")):
            if not file_path.is_file():
                continue
            digest_map[file_path.relative_to(self.workspace).as_posix()] = hashlib.sha256(
                file_path.read_bytes()
            ).hexdigest()
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
        self.assertEqual(first_stdout, update_index.generate_index_content(self.wiki_root))
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


if __name__ == "__main__":
    unittest.main()
