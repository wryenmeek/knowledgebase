"""Tests for scripts.validation.validate_afk_output."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scripts.validation.validate_afk_output import (
    _AFK_ALLOWED_FIELDS,
    _normalize_yaml_whitespace,
    _parse_frontmatter,
    validate_afk_output,
)


def _page(fm: str = "", body: str = "") -> str:
    return f"---\n{fm}\n---\n{body}"


class TestParserFrontmatter:
    def test_basic_parse(self) -> None:
        fm, body = _parse_frontmatter("---\ntitle: Test\n---\nBody text")
        assert fm["title"] == "Test"
        assert body == "Body text"

    def test_no_frontmatter(self) -> None:
        fm, body = _parse_frontmatter("Just text")
        assert fm == {}
        assert body == "Just text"


class TestNormalizeWhitespace:
    def test_trailing_whitespace_stripped(self) -> None:
        assert _normalize_yaml_whitespace("a  \nb  ") == "a\nb"


class TestBodyUnchanged:
    def test_identical_body_passes(self, tmp_path: Path) -> None:
        text = _page("title: A\nlast_updated: 2025-01-01", "Hello world")
        (tmp_path / "orig.md").write_text(text)
        (tmp_path / "prop.md").write_text(text)
        result = validate_afk_output(tmp_path / "orig.md", tmp_path / "prop.md")
        assert result.status == "pass"

    def test_body_changed_fails(self, tmp_path: Path) -> None:
        orig = _page("title: A", "Hello world")
        prop = _page("title: A", "Changed body")
        (tmp_path / "orig.md").write_text(orig)
        (tmp_path / "prop.md").write_text(prop)
        result = validate_afk_output(tmp_path / "orig.md", tmp_path / "prop.md")
        assert result.status == "fail"
        assert "body_unchanged" in result.message


class TestFrontmatterAllowedFields:
    def test_allowed_field_change_passes(self, tmp_path: Path) -> None:
        orig = _page("title: A\nlast_updated: 2025-01-01", "Body")
        prop = _page("title: A\nlast_updated: 2025-07-01", "Body")
        (tmp_path / "orig.md").write_text(orig)
        (tmp_path / "prop.md").write_text(prop)
        result = validate_afk_output(tmp_path / "orig.md", tmp_path / "prop.md")
        assert result.status == "pass"

    def test_disallowed_field_change_fails(self, tmp_path: Path) -> None:
        orig = _page("title: A\nstatus: draft", "Body")
        prop = _page("title: A\nstatus: published", "Body")
        (tmp_path / "orig.md").write_text(orig)
        (tmp_path / "prop.md").write_text(prop)
        result = validate_afk_output(tmp_path / "orig.md", tmp_path / "prop.md")
        assert result.status == "fail"
        assert "frontmatter_fields" in result.message


class TestCitationsUnchanged:
    def test_added_citation_fails(self, tmp_path: Path) -> None:
        orig = _page("title: A", "See repo://owner/repo/path@sha#anchor?sha256=abcd1234")
        prop = _page("title: A", "See repo://owner/repo/path@sha#anchor?sha256=abcd1234 and repo://new/ref@sha#a?sha256=0000")
        (tmp_path / "orig.md").write_text(orig)
        (tmp_path / "prop.md").write_text(prop)
        result = validate_afk_output(tmp_path / "orig.md", tmp_path / "prop.md")
        assert result.status == "fail"
        assert "citations_unchanged" in result.message

    def test_no_citations_either_side_passes(self, tmp_path: Path) -> None:
        text = _page("title: A", "Plain body")
        (tmp_path / "orig.md").write_text(text)
        (tmp_path / "prop.md").write_text(text)
        result = validate_afk_output(tmp_path / "orig.md", tmp_path / "prop.md")
        assert result.status == "pass"


class TestLinksUnchanged:
    def test_added_link_fails(self, tmp_path: Path) -> None:
        orig = _page("title: A", "[See](other.md)")
        prop = _page("title: A", "[See](other.md) [New](new.md)")
        (tmp_path / "orig.md").write_text(orig)
        (tmp_path / "prop.md").write_text(prop)
        result = validate_afk_output(tmp_path / "orig.md", tmp_path / "prop.md")
        assert result.status == "fail"
        assert "links_unchanged" in result.message


class TestIdentityUnchanged:
    def test_title_change_fails(self, tmp_path: Path) -> None:
        orig = _page("title: Original", "Body")
        prop = _page("title: Changed", "Body")
        (tmp_path / "orig.md").write_text(orig)
        (tmp_path / "prop.md").write_text(prop)
        result = validate_afk_output(tmp_path / "orig.md", tmp_path / "prop.md")
        assert result.status == "fail"
        assert "identity_unchanged" in result.message


class TestFileReadError:
    def test_missing_file_fails(self, tmp_path: Path) -> None:
        result = validate_afk_output(
            tmp_path / "nonexistent.md",
            tmp_path / "also-nonexistent.md",
        )
        assert result.status == "fail"
        assert result.reason_code == "invalid_input"


class TestAllowedFields:
    def test_quality_assessment_allowed(self, tmp_path: Path) -> None:
        orig = _page("title: A\nquality_assessment: old", "Body")
        prop = _page("title: A\nquality_assessment: new", "Body")
        (tmp_path / "orig.md").write_text(orig)
        (tmp_path / "prop.md").write_text(prop)
        result = validate_afk_output(tmp_path / "orig.md", tmp_path / "prop.md")
        assert result.status == "pass"
