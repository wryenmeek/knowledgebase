"""Byte-level contract tests for `extract_frontmatter`.

Covers happy-path LF + CRLF inputs, leading whitespace, empty frontmatter,
missing/unclosed delimiters, the file-ends-at-closing-delim edge case,
and UTF-8 BOM-prefixed inputs (Issue #321). The `name` parameter on each
case is plumbed only as a pytest-generated test ID label; it is not
asserted in the test body.

BOM handling (#321): the parser strips a single leading `\\ufeff` before
detecting frontmatter so files saved by Windows editors with a UTF-8 BOM
still resolve their frontmatter. The stripped BOM is not echoed back into
the returned body.
"""
import pytest
from scripts.kb.page_template_utils import extract_frontmatter

@pytest.mark.parametrize(
    "name, text, expected_fm, expected_body",
    [
        ("Happy LF", "---\nfm\n---\nbody\n", "fm", "body\n"),
        ("Happy CRLF", "---\r\nfm\r\n---\r\nbody\r\n", "fm", "body\r\n"),
        ("Leading whitespace", "  ---\nfm\n---\nbody", "fm", "body"),
        ("Empty frontmatter", "---\n---\nbody\n", "", "body\n"),
        ("No frontmatter pass-through", "no frontmatter\n", None, "no frontmatter\n"),
        ("Unclosed delim", "---\nunclosed\nbody\n", None, "---\nunclosed\nbody\n"),
        ("mid-body", "---\nfm\n---\nbody\n---\nmore\n", "fm", "body\n---\nmore\n"),
        ("File ending at closing delim", "---\nfm\n---", "fm", ""),
        # BOM cases (Issue #321): leading \ufeff must be stripped before
        # frontmatter detection, otherwise the parser silently treats
        # Windows-saved files as frontmatter-less.
        ("BOM + LF", "\ufeff---\nfm\n---\nbody\n", "fm", "body\n"),
        ("BOM + CRLF", "\ufeff---\r\nfm\r\n---\r\nbody\r\n", "fm", "body\r\n"),
        # Edge case: BOM with no frontmatter — BOM is stripped, body returned
        # without the BOM (caller can re-add if they need byte identity).
        ("BOM + no frontmatter", "\ufeffno frontmatter\n", None, "no frontmatter\n"),
    ]
)
def test_extract_frontmatter_cases(name, text, expected_fm, expected_body):
    fm, body = extract_frontmatter(text)
    assert fm == expected_fm
    assert body == expected_body
