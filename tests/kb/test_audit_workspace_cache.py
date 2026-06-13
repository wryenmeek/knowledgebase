"""Tests for audit-workspace skill-corpus cache extraction and invalidation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from unittest.mock import patch

from tests.kb.harnesses import RuntimeWorkspaceTestCase, load_module


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_CORPUS_CACHE_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "audit-knowledgebase-workspace"
    / "logic"
    / "skill_corpus_cache.py"
)


class SkillCorpusCacheTests(RuntimeWorkspaceTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.module = load_module("skill_corpus_cache", SKILL_CORPUS_CACHE_PATH)
        self.skill_root = self.workspace_root / ".github" / "skills"
        self.cache_dir = (
            self.workspace_root / ".github" / "skills" / "audit-knowledgebase-workspace" / ".cache"
        )

    def _write_skill(self, name: str, body: str) -> Path:
        skill_path = self.skill_root / name / "SKILL.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(body, encoding="utf-8")
        return skill_path

    @staticmethod
    def _skill_body(name: str, first_paragraph: str, *, leading_blank: bool) -> str:
        spacer = "\n\n" if leading_blank else "\n"
        return (
            "---\n"
            f"name: {name}\n"
            f"description: {name} description\n"
            "category: dev-support\n"
            "---"
            f"{spacer}"
            f"{first_paragraph}\n"
            "\n"
            "Second paragraph ignored by the cache.\n"
        )

    @staticmethod
    def _skill_body_with_headings(name: str, first_paragraph: str) -> str:
        return (
            "---\n"
            f"name: {name}\n"
            f"description: {name} description\n"
            "---\n"
            "\n"
            f"# {name.title()}\n"
            "\n"
            "## Overview\n"
            "\n"
            f"{first_paragraph}\n"
            "\n"
            "Second paragraph ignored by the cache.\n"
        )

    def _entry_for(self, corpus: dict[str, dict[str, object]], path: Path) -> dict[str, object]:
        return corpus[str(path.resolve())]

    def test_extracts_frontmatter_and_first_paragraph_with_and_without_leading_blank_lines(
        self,
    ) -> None:
        blank_first = "First paragraph after leading blank\ncontinues here"
        immediate_first = "Immediate first paragraph"
        blank_skill = self._write_skill(
            "blank-leading",
            self._skill_body("blank-leading", blank_first, leading_blank=True),
        )
        immediate_skill = self._write_skill(
            "no-leading-blank",
            self._skill_body("no-leading-blank", immediate_first, leading_blank=False),
        )
        headed_skill = self._write_skill(
            "headed-skill",
            self._skill_body_with_headings("headed-skill", "First prose paragraph"),
        )

        corpus = self.module.get_skill_corpus(self.skill_root, self.cache_dir)

        blank_entry = self._entry_for(corpus, blank_skill)
        self.assertEqual(blank_entry["frontmatter"]["name"], "blank-leading")
        self.assertEqual(blank_entry["frontmatter"]["description"], "blank-leading description")
        self.assertEqual(blank_entry["first_paragraph"], blank_first)
        self.assertEqual(blank_entry["cache_strategy"], "mtime_first_para")

        immediate_entry = self._entry_for(corpus, immediate_skill)
        self.assertEqual(immediate_entry["frontmatter"]["name"], "no-leading-blank")
        self.assertEqual(immediate_entry["first_paragraph"], immediate_first)
        self.assertEqual(immediate_entry["cache_strategy"], "mtime_first_para")

        headed_entry = self._entry_for(corpus, headed_skill)
        self.assertEqual(headed_entry["frontmatter"]["name"], "headed-skill")
        self.assertEqual(headed_entry["first_paragraph"], "First prose paragraph")
        self.assertEqual(headed_entry["cache_strategy"], "mtime_first_para")

    def test_mtime_change_causes_cache_miss_and_reextracts(self) -> None:
        skill_path = self._write_skill(
            "mtime-miss",
            self._skill_body("mtime-miss", "Original first paragraph", leading_blank=True),
        )
        original = self.module.get_skill_corpus(self.skill_root, self.cache_dir)
        original_mtime_ns = self._entry_for(original, skill_path)["mtime_ns"]

        skill_path.write_text(
            self._skill_body("mtime-miss", "Updated first paragraph", leading_blank=True),
            encoding="utf-8",
        )
        os.utime(
            skill_path,
            ns=(skill_path.stat().st_atime_ns + 1_000_000_000, original_mtime_ns + 1_000_000_000),
        )

        refreshed = self.module.get_skill_corpus(self.skill_root, self.cache_dir)
        refreshed_entry = self._entry_for(refreshed, skill_path)
        self.assertEqual(refreshed_entry["first_paragraph"], "Updated first paragraph")
        self.assertGreater(refreshed_entry["mtime_ns"], original_mtime_ns)

    def test_no_mtime_change_uses_cache_without_rereading_skill_file(self) -> None:
        skill_path = self._write_skill(
            "mtime-hit",
            self._skill_body("mtime-hit", "Cached first paragraph", leading_blank=True),
        )
        cached = self.module.get_skill_corpus(self.skill_root, self.cache_dir)

        with patch.object(
            self.module,
            "_extract_skill_entry",
            side_effect=AssertionError("cache hit must not re-read SKILL.md"),
        ):
            second = self.module.get_skill_corpus(self.skill_root, self.cache_dir)

        self.assertEqual(second, cached)
        self.assertEqual(self._entry_for(second, skill_path)["first_paragraph"], "Cached first paragraph")

    def test_touch_without_content_change_is_accepted_cache_miss_edge_case(self) -> None:
        """Q11 accepts touch-only mtime changes as cache misses with same content."""

        skill_path = self._write_skill(
            "touch-edge",
            self._skill_body("touch-edge", "Touch-stable first paragraph", leading_blank=True),
        )
        self.module.get_skill_corpus(self.skill_root, self.cache_dir)

        original_mtime_ns = skill_path.stat().st_mtime_ns
        time.sleep(0.01)
        skill_path.touch()
        self.assertNotEqual(skill_path.stat().st_mtime_ns, original_mtime_ns)

        with patch.object(
            self.module,
            "_extract_skill_entry",
            wraps=self.module._extract_skill_entry,
        ) as extract_skill_entry:
            refreshed = self.module.get_skill_corpus(self.skill_root, self.cache_dir)

        extract_skill_entry.assert_called_once()
        self.assertEqual(
            self._entry_for(refreshed, skill_path)["first_paragraph"],
            "Touch-stable first paragraph",
        )

    def test_force_write_with_mtime_reset_hits_stale_cache_as_q11_false_negative(self) -> None:
        """Q11 accepts stale hits when content changes but mtime is force-reset."""

        skill_path = self._write_skill(
            "stale-edge",
            self._skill_body("stale-edge", "Original cached first paragraph", leading_blank=True),
        )
        cached = self.module.get_skill_corpus(self.skill_root, self.cache_dir)
        original_stat = skill_path.stat()

        skill_path.write_text(
            self._skill_body("stale-edge", "Updated but stale first paragraph", leading_blank=True),
            encoding="utf-8",
        )
        os.utime(skill_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

        stale = self.module.get_skill_corpus(self.skill_root, self.cache_dir)

        self.assertEqual(stale, cached)
        self.assertEqual(
            self._entry_for(stale, skill_path)["first_paragraph"],
            "Original cached first paragraph",
        )

    def test_force_refresh_reextracts_even_with_unchanged_mtime(self) -> None:
        skill_path = self._write_skill(
            "force-refresh",
            self._skill_body("force-refresh", "Original first paragraph", leading_blank=True),
        )
        self.module.get_skill_corpus(self.skill_root, self.cache_dir)
        original_stat = skill_path.stat()

        skill_path.write_text(
            self._skill_body("force-refresh", "Force-refreshed first paragraph", leading_blank=True),
            encoding="utf-8",
        )
        os.utime(skill_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

        stale = self.module.get_skill_corpus(self.skill_root, self.cache_dir)
        self.assertEqual(self._entry_for(stale, skill_path)["first_paragraph"], "Original first paragraph")

        refreshed = self.module.get_skill_corpus(self.skill_root, self.cache_dir, force_refresh=True)
        self.assertEqual(
            self._entry_for(refreshed, skill_path)["first_paragraph"],
            "Force-refreshed first paragraph",
        )

    def test_corrupt_cache_json_is_recovered_silently(self) -> None:
        skill_path = self._write_skill(
            "corrupt-cache",
            self._skill_body("corrupt-cache", "Recovered first paragraph", leading_blank=True),
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self.cache_dir / self.module.CACHE_FILENAME
        cache_path.write_text("{not valid json", encoding="utf-8")

        with patch.object(
            self.module,
            "_extract_skill_entry",
            wraps=self.module._extract_skill_entry,
        ) as extract_skill_entry:
            corpus = self.module.get_skill_corpus(self.skill_root, self.cache_dir)

        extract_skill_entry.assert_called_once()
        self.assertEqual(
            self._entry_for(corpus, skill_path)["first_paragraph"],
            "Recovered first paragraph",
        )
        persisted = json.loads(cache_path.read_text(encoding="utf-8"))
        self.assertEqual(
            persisted[str(skill_path.resolve())]["first_paragraph"],
            "Recovered first paragraph",
        )

    def test_symlinked_cache_path_is_rejected(self) -> None:
        self._write_skill(
            "symlink-cache",
            self._skill_body("symlink-cache", "Symlink first paragraph", leading_blank=True),
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        target = self.workspace_root / "cache-target.json"
        target.write_text("{}", encoding="utf-8")
        os.symlink(target, self.cache_dir / self.module.CACHE_FILENAME)

        with self.assertRaises(OSError):
            self.module.get_skill_corpus(self.skill_root, self.cache_dir)

    def test_empty_or_no_frontmatter_skill_md(self) -> None:
        cases = (
            ("empty-skill", "", {}, ""),
            (
                "body-only",
                "Body-only first paragraph\ncontinues here\n\nSecond paragraph ignored.\n",
                {},
                "Body-only first paragraph\ncontinues here",
            ),
            ("frontmatter-only", "---\nname: frontmatter-only\n---\n", {"name": "frontmatter-only"}, ""),
        )
        for name, content, expected_frontmatter, expected_first_paragraph in cases:
            with self.subTest(name=name):
                skill_path = self._write_skill(name, content)
                corpus = self.module.get_skill_corpus(self.skill_root, self.cache_dir, force_refresh=True)
                entry = self._entry_for(corpus, skill_path)
                self.assertEqual(entry["frontmatter"], expected_frontmatter)
                self.assertEqual(entry["first_paragraph"], expected_first_paragraph)
                self.assertEqual(entry["cache_strategy"], "mtime_first_para")

    def test_cache_dir_outside_skill_local_cache_fails_closed(self) -> None:
        self.skill_root.mkdir(parents=True, exist_ok=True)

        with self.assertRaisesRegex(ValueError, "skill-local"):
            self.module.get_skill_corpus(self.skill_root, self.workspace_root / "other-cache")

    def test_governed_cache_dir_fails_closed(self) -> None:
        self.skill_root.mkdir(parents=True, exist_ok=True)

        with self.assertRaisesRegex(ValueError, "governed path"):
            self.module.get_skill_corpus(self.skill_root, self.workspace_root / "docs" / ".cache")


class SkillCorpusCacheBoundaryTests(RuntimeWorkspaceTestCase):
    def test_missing_skill_root_fails_closed(self) -> None:
        module = load_module("skill_corpus_cache_boundary", SKILL_CORPUS_CACHE_PATH)
        missing_root = self.workspace_root / ".github" / "skills" / "missing-skill-root"
        cache_dir = self.workspace_root / ".github" / "skills" / "audit-knowledgebase-workspace" / ".cache"

        with self.assertRaises(FileNotFoundError):
            module.get_skill_corpus(missing_root, cache_dir)
