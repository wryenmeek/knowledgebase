"""Unit tests for create_issues.py — sanitization logic only.

Subprocess-based ``gh`` CLI calls are integration-level and not tested here.
"""

from __future__ import annotations

import pytest

from scripts.github_monitor.create_issues import _sanitize_gh_md


class TestSanitizeGhMd:
    """Verify that _sanitize_gh_md strips dangerous markdown constructs."""

    def test_strips_backticks(self) -> None:
        assert _sanitize_gh_md("some `code` here") == "some code here"

    def test_strips_html_tags(self) -> None:
        assert _sanitize_gh_md("hello <b>world</b>") == "hello bworld/b"

    def test_strips_at_mentions(self) -> None:
        assert _sanitize_gh_md("cc @user and @org/team") == "cc  and"

    def test_strips_image_embeds(self) -> None:
        assert _sanitize_gh_md("![alt](url)") == "[alt](url)"

    def test_strips_auto_close_keywords(self) -> None:
        assert _sanitize_gh_md("Fixes #123 and resolves #456") == "and"

    def test_strips_close_keyword(self) -> None:
        assert _sanitize_gh_md("close #99") == ""

    def test_strips_closes_keyword(self) -> None:
        assert _sanitize_gh_md("Closes #10") == ""

    def test_strips_closed_keyword(self) -> None:
        assert _sanitize_gh_md("closed #7") == ""

    def test_strips_resolved_keyword(self) -> None:
        assert _sanitize_gh_md("resolved #42") == ""

    def test_truncates_to_max_len(self) -> None:
        result = _sanitize_gh_md("a" * 300, max_len=50)
        assert len(result) <= 50

    def test_handles_empty_string(self) -> None:
        assert _sanitize_gh_md("") == ""

    def test_preserves_plain_text(self) -> None:
        assert _sanitize_gh_md("hello world") == "hello world"

    def test_combined_sanitization(self) -> None:
        raw = "fixes #1 <script>@evil `tick` ![img](x)"
        result = _sanitize_gh_md(raw)
        assert "`" not in result
        assert "<" not in result
        assert ">" not in result
        assert "@evil" not in result
        assert "![" not in result
        assert "fixes #1" not in result.lower()
