import unittest
from scripts.kb.page_template_utils import extract_frontmatter

class TestExtractFrontmatter(unittest.TestCase):

    def test_extract_frontmatter_cases(self):
        cases = [
            ("Happy LF", "---\nfm\n---\nbody\n", "fm", "body\n"),
            ("Happy CRLF", "---\r\nfm\r\n---\r\nbody\r\n", "fm", "body\r\n"),
            ("Leading whitespace", "  ---\nfm\n---\nbody", "fm", "body"),
            ("Empty frontmatter", "---\n---\nbody\n", "", "body\n"),
            ("No frontmatter pass-through", "no frontmatter\n", None, "no frontmatter\n"),
            ("Unclosed delim", "---\nunclosed\nbody\n", None, "---\nunclosed\nbody\n"),
            ("mid-body", "---\nfm\n---\nbody\n---\nmore\n", "fm", "body\n---\nmore\n"),
            ("File ending at closing delim", "---\nfm\n---", "fm", ""),
        ]

        for name, text, expected_fm, expected_body in cases:
            with self.subTest(name=name):
                fm, body = extract_frontmatter(text)
                self.assertEqual(fm, expected_fm)
                self.assertEqual(body, expected_body)

if __name__ == '__main__':
    unittest.main()
