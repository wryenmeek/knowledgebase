"""Unit tests for page_template_utils convenience helpers."""

from __future__ import annotations

import unittest

from scripts.kb.page_template_utils import (
    extract_sources_from_frontmatter,
    parse_page_frontmatter,
)


class ParsePageFrontmatterTests(unittest.TestCase):
    def test_returns_parsed_dict_for_valid_frontmatter(self) -> None:
        text = "---\ntitle: Hello\nstatus: draft\n---\n# Hello\n"
        result = parse_page_frontmatter(text)
        self.assertEqual(result["title"], "Hello")
        self.assertEqual(result["status"], "draft")

    def test_returns_empty_dict_when_no_frontmatter(self) -> None:
        text = "# Just a heading\nno frontmatter here\n"
        self.assertEqual(parse_page_frontmatter(text), {})

    def test_returns_empty_dict_for_empty_text(self) -> None:
        self.assertEqual(parse_page_frontmatter(""), {})

    def test_returns_empty_dict_when_frontmatter_block_unclosed(self) -> None:
        text = "---\ntitle: Hello\n"
        self.assertEqual(parse_page_frontmatter(text), {})

    def test_body_content_not_included_in_result(self) -> None:
        text = "---\ntitle: Test\n---\nbody: not-a-key\n"
        result = parse_page_frontmatter(text)
        self.assertNotIn("body", result)
        self.assertIn("title", result)


class ExtractSourcesFromFrontmatterTests(unittest.TestCase):
    def test_extracts_multi_item_yaml_list(self) -> None:
        frontmatter = "type: source\nsources:\n  - repo://owner/repo/path@abc123#x?sha256=aabbcc\n  - repo://owner/repo/other@abc123#y?sha256=ddeeff\n"
        result = extract_sources_from_frontmatter(frontmatter)
        self.assertEqual(len(result), 2)
        self.assertIn("repo://owner/repo/path@abc123#x?sha256=aabbcc", result)

    def test_extracts_inline_single_source(self) -> None:
        frontmatter = "type: source\nsources: repo://owner/repo/path@abc123#x?sha256=aabbcc\n"
        result = extract_sources_from_frontmatter(frontmatter)
        self.assertEqual(result, ["repo://owner/repo/path@abc123#x?sha256=aabbcc"])

    def test_returns_empty_list_for_empty_sources_bracket(self) -> None:
        frontmatter = "type: source\nsources: []\n"
        result = extract_sources_from_frontmatter(frontmatter)
        self.assertEqual(result, [])

    def test_returns_empty_list_when_no_sources_key(self) -> None:
        frontmatter = "type: source\ntitle: No sources here\n"
        result = extract_sources_from_frontmatter(frontmatter)
        self.assertEqual(result, [])

    def test_returns_empty_list_for_empty_frontmatter(self) -> None:
        self.assertEqual(extract_sources_from_frontmatter(""), [])

    def test_strips_quotes_from_inline_source(self) -> None:
        frontmatter = 'sources: "repo://owner/repo/path@abc123#x?sha256=aabbcc"\n'
        result = extract_sources_from_frontmatter(frontmatter)
        self.assertEqual(result, ["repo://owner/repo/path@abc123#x?sha256=aabbcc"])

    def test_strips_quotes_from_list_items(self) -> None:
        frontmatter = "sources:\n  - 'repo://owner/repo/path@abc123#x?sha256=aabbcc'\n"
        result = extract_sources_from_frontmatter(frontmatter)
        self.assertEqual(result, ["repo://owner/repo/path@abc123#x?sha256=aabbcc"])

    def test_list_extraction_stops_at_non_indented_line(self) -> None:
        frontmatter = "sources:\n  - repo://a\nnext_key: value\n"
        result = extract_sources_from_frontmatter(frontmatter)
        self.assertEqual(result, ["repo://a"])


if __name__ == "__main__":
    unittest.main()
