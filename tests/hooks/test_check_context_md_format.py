"""Tests for scripts.hooks.check_context_md_format."""

import tempfile
import textwrap
import unittest
from pathlib import Path

from scripts.hooks.check_context_md_format import MAX_LINES, main

VALID_CONTENT = textwrap.dedent("""\
    ---
    scope: repo
    last_updated: 2025-07-01
    ---

    # CONTEXT

    ## Terms

    | Term | Definition |
    |------|------------|
    | foo | bar |

    ## Invariants

    | Invariant | Description |
    |-----------|-------------|
    | fail closed | Always. |

    ## File Roles

    | Path | Role |
    |------|------|
    | `wiki/` | Wiki pages. |
""")


class CheckContextMdFormatTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()

    def _write(self, name: str, content: str) -> str:
        p = Path(self._tmp) / name
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_valid_file_exits_0(self) -> None:
        path = self._write("CONTEXT.md", VALID_CONTENT)
        self.assertEqual(main([path]), 0)

    def test_missing_invariants_section_exits_1(self) -> None:
        content = VALID_CONTENT.replace("## Invariants\n", "").replace(
            "| Invariant | Description |\n|-----------|--------------|\n| fail closed | Always. |\n", ""
        )
        path = self._write("CONTEXT.md", content)
        self.assertEqual(main([path]), 1)

    def test_missing_terms_section_exits_1(self) -> None:
        content = VALID_CONTENT.replace("## Terms\n", "").replace(
            "| Term | Definition |\n|------|------------|\n| foo | bar |\n", ""
        )
        path = self._write("CONTEXT.md", content)
        self.assertEqual(main([path]), 1)

    def test_missing_file_roles_section_exits_1(self) -> None:
        content = VALID_CONTENT.replace("## File Roles\n", "").replace(
            "| Path | Role |\n|------|------|\n| `wiki/` | Wiki pages. |\n", ""
        )
        path = self._write("CONTEXT.md", content)
        self.assertEqual(main([path]), 1)

    def test_lowercase_invariants_exits_1(self) -> None:
        content = VALID_CONTENT.replace("## Invariants", "## invariants")
        path = self._write("CONTEXT.md", content)
        self.assertEqual(main([path]), 1)

    def test_exactly_200_lines_exits_0(self) -> None:
        # Build a file with exactly MAX_LINES lines.
        lines = VALID_CONTENT.splitlines()
        padding = MAX_LINES - len(lines)
        content = VALID_CONTENT + "\n" * padding
        # Verify our construction.
        assert len(content.splitlines()) == MAX_LINES, len(content.splitlines())
        path = self._write("CONTEXT.md", content)
        self.assertEqual(main([path]), 0)

    def test_201_lines_exits_1(self) -> None:
        lines = VALID_CONTENT.splitlines()
        padding = (MAX_LINES + 1) - len(lines)
        content = VALID_CONTENT + "\n" * padding
        assert len(content.splitlines()) == MAX_LINES + 1
        path = self._write("CONTEXT.md", content)
        self.assertEqual(main([path]), 1)

    def test_empty_file_exits_1_cleanly(self) -> None:
        path = self._write("CONTEXT.md", "")
        # Must exit 1 with a message, not raise an exception.
        result = main([path])
        self.assertEqual(result, 1)

    def test_missing_frontmatter_scope_exits_1(self) -> None:
        content = VALID_CONTENT.replace("scope: repo\n", "")
        path = self._write("CONTEXT.md", content)
        self.assertEqual(main([path]), 1)

    def test_missing_frontmatter_last_updated_exits_1(self) -> None:
        content = VALID_CONTENT.replace("last_updated: 2025-07-01\n", "")
        path = self._write("CONTEXT.md", content)
        self.assertEqual(main([path]), 1)

    def test_section_inside_fenced_code_block_does_not_count(self) -> None:
        """Headings inside code fences do not satisfy section requirements."""
        content = textwrap.dedent("""\
            ---
            scope: repo
            last_updated: 2025-07-01
            ---

            # CONTEXT

            ## Terms

            | Term | Definition |
            |------|------------|
            | foo | bar |

            ```
            ## Invariants
            ## File Roles
            ```
        """)
        path = self._write("CONTEXT.md", content)
        # Missing Invariants and File Roles outside fences → should fail.
        self.assertEqual(main([path]), 1)

    def test_empty_argv_exits_0(self) -> None:
        self.assertEqual(main([]), 0)


if __name__ == "__main__":
    unittest.main()
