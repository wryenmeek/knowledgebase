"""Byte-level contract tests for ``extract_frontmatter``.

Issue #303 locks the regex-based extraction behavior introduced by PR #298:
returned body text is preserved verbatim, including CRLF sequences and trailing
newlines. The BOM cases preserve the Issue #321 regression coverage in this
dedicated test file.
"""

from __future__ import annotations

import pytest

from scripts.kb.page_template_utils import extract_frontmatter


@pytest.mark.parametrize(
    "name, text, expected_fm, expected_body",
    [
        ("happy_lf", "---\nfm\n---\nbody\n", "fm", "body\n"),
        ("happy_crlf", "---\r\nfm\r\n---\r\nbody\r\n", "fm", "body\r\n"),
        ("leading_whitespace", "  ---\nfm\n---\nbody", "fm", "body"),
        ("empty_frontmatter", "---\n---\nbody\n", "", "body\n"),
        ("no_frontmatter_pass_through", "no frontmatter\n", None, "no frontmatter\n"),
        ("unclosed_delim", "---\nunclosed\nbody\n", None, "---\nunclosed\nbody\n"),
        (
            "mid_body_delimiter_without_opening",
            "body\n---\nfake: value\n---\nmore\n",
            None,
            "body\n---\nfake: value\n---\nmore\n",
        ),
        (
            "body_delimiter_after_frontmatter",
            "---\nfm\n---\nbody\n---\nmore\n",
            "fm",
            "body\n---\nmore\n",
        ),
        ("file_ending_at_closing_delim", "---\nfm\n---", "fm", ""),
        ("bom_lf", "\ufeff---\nfm\n---\nbody\n", "fm", "body\n"),
        ("bom_crlf", "\ufeff---\r\nfm\r\n---\r\nbody\r\n", "fm", "body\r\n"),
        ("bom_no_frontmatter", "\ufeffno frontmatter\n", None, "no frontmatter\n"),
    ],
)
def test_extract_frontmatter_byte_contract(
    name: str,
    text: str,
    expected_fm: str | None,
    expected_body: str,
) -> None:
    fm, body = extract_frontmatter(text)

    assert fm == expected_fm, f"{name}: fm mismatch"
    assert body == expected_body, f"{name}: body mismatch (byte contract drift)"
