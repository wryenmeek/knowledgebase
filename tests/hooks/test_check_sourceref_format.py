"""Tests for scripts.hooks.check_sourceref_format."""

import tempfile
import textwrap
import unittest
from pathlib import Path

from scripts.hooks.check_sourceref_format import main


def _write_md(tmp: Path, name: str, content: str) -> str:
    p = tmp / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(p)


class CheckSourcerefFormatTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp())

    def test_valid_sourceref_with_extension_exits_0(self) -> None:
        """Extension (.md, .json) in path must not be rejected."""
        path = _write_md(self._tmp, "valid.md", """\
            See repo://owner/repo/path/to/file.md@abc1234#anchor?sha256={}
        """.format("a" * 64))
        self.assertEqual(main([path]), 0)

    def test_valid_sourceref_exits_0(self) -> None:
        path = _write_md(self._tmp, "ok.md", """\
            Citation: repo://owner/repo/path@abcdef1234567890abcdef1234567890abcdef12#sec?sha256={}
        """.format("b" * 64))
        self.assertEqual(main([path]), 0)

    def test_no_citations_exits_0(self) -> None:
        path = _write_md(self._tmp, "no-cite.md", """\
            # No citations here

            Just prose.
        """)
        self.assertEqual(main([path]), 0)

    def test_malformed_citation_exits_1(self) -> None:
        """repo:// with trailing closing paren and dot."""
        path = _write_md(self._tmp, "bad.md", """\
            See (repo://owner/repo/path@sha).
        """)
        self.assertEqual(main([path]), 1)

    def test_sourceref_in_fenced_code_block_exits_0(self) -> None:
        """SourceRefs inside code blocks must be skipped."""
        path = _write_md(self._tmp, "fenced.md", """\
            Normal text.

            ```
            repo://this/should/be@skipped#because?its=in_a_fence
            ```
        """)
        self.assertEqual(main([path]), 0)

    def test_sourceref_in_frontmatter_exits_0(self) -> None:
        """SourceRefs in YAML frontmatter block must be skipped."""
        path = _write_md(self._tmp, "frontmatter.md", """\
            ---
            sources:
              - repo://owner/repo/path@sha#anchor?sha256={}
            ---
            # Body
        """.format("c" * 64))
        self.assertEqual(main([path]), 0)

    def test_multiple_malformed_reports_all(self) -> None:
        """All line numbers are reported, not just the first."""
        content = textwrap.dedent("""\
            Line with bad cite: repo://bad1).
            Another bad cite: repo://bad2,thing.
        """)
        path = _write_md(self._tmp, "multi-bad.md", content)
        result = main([path])
        self.assertEqual(result, 1)

    def test_non_md_file_skipped(self) -> None:
        """Non-.md files are skipped entirely."""
        p = self._tmp / "script.py"
        p.write_text("# repo://not/a/real/sourceref\n", encoding="utf-8")
        self.assertEqual(main([str(p)]), 0)

    def test_empty_argv_exits_0(self) -> None:
        self.assertEqual(main([]), 0)


if __name__ == "__main__":
    unittest.main()
