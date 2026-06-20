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
    ]
)
def test_extract_frontmatter_cases(name, text, expected_fm, expected_body):
    fm, body = extract_frontmatter(text)
    assert fm == expected_fm
    assert body == expected_body
