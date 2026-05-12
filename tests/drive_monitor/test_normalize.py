"""Unit tests for scripts/drive_monitor/_normalize.py.

Tests use fixed byte-level test vectors to verify the normalization algorithm
is correct and idempotent.
"""

from __future__ import annotations

import pytest
from scripts.drive_monitor._normalize import normalize_markdown_export


class TestNormalizeMarkdownExport:
    def test_crlf_normalized_to_lf(self):
        result = normalize_markdown_export(b"hello\r\nworld\r\n")
        assert result == b"hello\nworld\n"

    def test_bare_cr_normalized_to_lf(self):
        result = normalize_markdown_export(b"hello\rworld\r")
        assert result == b"hello\nworld\n"

    def test_trailing_whitespace_stripped_per_line(self):
        result = normalize_markdown_export(b"hello   \nworld\t\n")
        assert result == b"hello\nworld\n"

    def test_trailing_blank_lines_collapsed(self):
        result = normalize_markdown_export(b"hello\nworld\n\n\n\n")
        assert result == b"hello\nworld\n"

    def test_leading_blank_lines_stripped(self):
        result = normalize_markdown_export(b"\n\n\nhello\n")
        assert result == b"hello\n"

    def test_already_normalized_is_idempotent(self):
        data = b"hello\nworld\n"
        result = normalize_markdown_export(data)
        assert result == data
        # Idempotent: calling twice gives same result
        assert normalize_markdown_export(result) == result

    def test_empty_bytes_returns_single_newline(self):
        result = normalize_markdown_export(b"")
        assert result == b"\n"

    def test_all_blank_returns_single_newline(self):
        result = normalize_markdown_export(b"\n\n\n\n")
        assert result == b"\n"

    def test_blank_lines_only_spaces_returns_single_newline(self):
        result = normalize_markdown_export(b"   \n   \n   \n")
        assert result == b"\n"

    def test_single_line_no_trailing_newline_gets_one(self):
        result = normalize_markdown_export(b"hello")
        assert result == b"hello\n"

    def test_exactly_one_trailing_newline(self):
        result = normalize_markdown_export(b"# Title\n\nParagraph.\n")
        assert result.endswith(b"\n")
        assert not result.endswith(b"\n\n")

    def test_mixed_crlf_and_lf(self):
        result = normalize_markdown_export(b"line1\r\nline2\nline3\r\n")
        assert result == b"line1\nline2\nline3\n"

    def test_utf8_content_preserved(self):
        content = "# Héllo\n\n*Wörld*\n".encode("utf-8")
        result = normalize_markdown_export(content)
        assert "Héllo" in result.decode("utf-8")
        assert "Wörld" in result.decode("utf-8")

    def test_inline_blank_lines_preserved(self):
        # Blank lines within the document body should be preserved
        result = normalize_markdown_export(b"# Section\n\nParagraph.\n\n## Subsection\n")
        assert result == b"# Section\n\nParagraph.\n\n## Subsection\n"

    def test_trailing_spaces_on_multiple_lines(self):
        result = normalize_markdown_export(b"line1    \nline2  \nline3\t\t\n")
        assert result == b"line1\nline2\nline3\n"

    def test_sha256_is_stable(self):
        """Normalizing the same content twice must produce the same SHA-256."""
        import hashlib
        content = b"# My Document\r\n\r\nSome text.  \r\n\r\n"
        h1 = hashlib.sha256(normalize_markdown_export(content)).hexdigest()
        h2 = hashlib.sha256(normalize_markdown_export(content)).hexdigest()
        assert h1 == h2

    def test_sha256_differs_for_different_content(self):
        import hashlib
        a = normalize_markdown_export(b"content A\n")
        b_ = normalize_markdown_export(b"content B\n")
        assert hashlib.sha256(a).hexdigest() != hashlib.sha256(b_).hexdigest()
