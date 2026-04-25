"""Tests for scripts.hooks.check_frontmatter."""

import tempfile
import textwrap
import unittest
from pathlib import Path

from scripts.hooks.check_frontmatter import main


def _write_file(tmp: Path, name: str, content: str) -> str:
    p = tmp / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(p)


class CheckFrontmatterWikiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self._root = Path(self._tmp)
        # Build a fake wiki directory structure.
        (self._root / "wiki").mkdir()

    def _wiki(self, name: str, content: str) -> str:
        p = self._root / "wiki" / name
        p.write_text(textwrap.dedent(content), encoding="utf-8")
        return str(p)

    def test_valid_wiki_page_exits_0(self) -> None:
        path = self._wiki("page.md", """\
            ---
            type: entity
            title: My Page
            status: active
            updated_at: "2025-01-01T00:00:00Z"
            ---
            # My Page
        """)
        self.assertEqual(main([path]), 0)

    def test_wiki_page_missing_title_exits_1(self) -> None:
        path = self._wiki("no-title.md", """\
            ---
            type: entity
            status: active
            updated_at: "2025-01-01T00:00:00Z"
            ---
            # No Title
        """)
        self.assertEqual(main([path]), 1)

    def test_wiki_page_empty_title_exits_1(self) -> None:
        path = self._wiki("empty-title.md", """\
            ---
            type: entity
            title:
            status: active
            updated_at: "2025-01-01T00:00:00Z"
            ---
        """)
        self.assertEqual(main([path]), 1)

    def test_wiki_page_no_frontmatter_exits_1(self) -> None:
        path = self._wiki("no-fm.md", """\
            # Just a heading

            No frontmatter here.
        """)
        self.assertEqual(main([path]), 1)

    def test_non_wiki_markdown_exits_0(self) -> None:
        """Markdown files outside wiki/** and SKILL.md are skipped."""
        p = self._root / "README.md"
        p.write_text("# README\n", encoding="utf-8")
        self.assertEqual(main([str(p)]), 0)


class CheckFrontmatterSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self._root = Path(self._tmp)

    def _skill_md(self, subdir: str, content: str) -> str:
        d = self._root / subdir
        d.mkdir(parents=True, exist_ok=True)
        p = d / "SKILL.md"
        p.write_text(textwrap.dedent(content), encoding="utf-8")
        return str(p)

    def test_valid_skill_md_exits_0(self) -> None:
        path = self._skill_md(".github/skills/my-skill", """\
            ---
            name: my-skill
            description: Does things.
            ---
            # My Skill
        """)
        self.assertEqual(main([path]), 0)

    def test_skill_md_missing_name_exits_1(self) -> None:
        path = self._skill_md(".github/skills/no-name", """\
            ---
            description: Does things.
            ---
        """)
        self.assertEqual(main([path]), 1)

    def test_skill_md_takes_precedence_over_wiki_pattern(self) -> None:
        """wiki/SKILL.md matches SKILL.md pattern first, not wiki/**/*.md."""
        wiki_dir = self._root / "wiki"
        wiki_dir.mkdir(parents=True, exist_ok=True)
        p = wiki_dir / "SKILL.md"
        # Valid SKILL.md fields only (no wiki fields like type/status).
        p.write_text(textwrap.dedent("""\
            ---
            name: wiki-skill
            description: A skill in the wiki directory.
            ---
            # Wiki Skill
        """), encoding="utf-8")
        # Should pass because SKILL.md check applies, not wiki check.
        self.assertEqual(main([str(p)]), 0)

    def test_skill_md_takes_precedence_missing_wiki_field(self) -> None:
        """wiki/SKILL.md with SKILL.md fields but missing wiki 'type' field passes."""
        wiki_dir = self._root / "wiki"
        wiki_dir.mkdir(parents=True, exist_ok=True)
        p = wiki_dir / "SKILL.md"
        p.write_text(textwrap.dedent("""\
            ---
            name: wiki-skill
            description: Skill doc.
            ---
        """), encoding="utf-8")
        # If wiki check applied, 'type' would be required. SKILL.md check only needs name+description.
        self.assertEqual(main([str(p)]), 0)


class CheckFrontmatterEdgeCaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self._root = Path(self._tmp)

    def test_empty_argv_exits_0(self) -> None:
        self.assertEqual(main([]), 0)


if __name__ == "__main__":
    unittest.main()
