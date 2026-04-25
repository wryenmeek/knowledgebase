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

    def test_multiline_quality_assessment_parsed_as_dict(self) -> None:
        import datetime
        text = "---\ntitle: T\nquality_assessment:\n  freshness_date: 2025-01-01\n  score: high\n---\nBody"
        fm, body = _parse_frontmatter(text)
        assert isinstance(fm["quality_assessment"], dict)
        # yaml.safe_load parses bare ISO dates as datetime.date objects.
        assert fm["quality_assessment"]["freshness_date"] == datetime.date(2025, 1, 1)
        assert fm["quality_assessment"]["score"] == "high"

    def test_aliases_list_parsed_correctly(self) -> None:
        text = "---\ntitle: T\naliases:\n  - old-name\n  - other-name\n---\nBody"
        fm, _ = _parse_frontmatter(text)
        assert fm["aliases"] == ["old-name", "other-name"]


class TestNormalizeWhitespace:
    def test_trailing_whitespace_stripped(self) -> None:
        assert _normalize_yaml_whitespace("a  \nb  ") == "a\nb"


class TestBodyUnchanged:
    def test_identical_body_passes(self, tmp_path: Path) -> None:
        text = _page("title: A\nupdated_at: 2025-01-01", "Hello world")
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
        orig = _page("title: A\nupdated_at: 2025-01-01", "Body")
        prop = _page("title: A\nupdated_at: 2025-07-01", "Body")
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

    def test_aliases_change_fails(self, tmp_path: Path) -> None:
        orig = "---\ntitle: T\naliases:\n  - old-name\n---\nBody"
        prop = "---\ntitle: T\naliases:\n  - new-name\n---\nBody"
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
    def test_quality_assessment_freshness_date_change_passes(self, tmp_path: Path) -> None:
        """Multi-line quality_assessment with only freshness_date changing: pass."""
        orig = (
            "---\n"
            "title: A\n"
            "quality_assessment:\n"
            "  freshness_date: 2025-01-01\n"
            "  score: high\n"
            "---\nBody"
        )
        prop = (
            "---\n"
            "title: A\n"
            "quality_assessment:\n"
            "  freshness_date: 2025-07-01\n"
            "  score: high\n"
            "---\nBody"
        )
        (tmp_path / "orig.md").write_text(orig)
        (tmp_path / "prop.md").write_text(prop)
        result = validate_afk_output(tmp_path / "orig.md", tmp_path / "prop.md")
        assert result.status == "pass"

    def test_quality_assessment_non_freshness_change_fails(self, tmp_path: Path) -> None:
        """Changing quality_assessment.score (non-allowed sub-field) must fail."""
        orig = (
            "---\n"
            "title: A\n"
            "quality_assessment:\n"
            "  freshness_date: 2025-01-01\n"
            "  score: high\n"
            "---\nBody"
        )
        prop = (
            "---\n"
            "title: A\n"
            "quality_assessment:\n"
            "  freshness_date: 2025-01-01\n"
            "  score: low\n"
            "---\nBody"
        )
        (tmp_path / "orig.md").write_text(orig)
        (tmp_path / "prop.md").write_text(prop)
        result = validate_afk_output(tmp_path / "orig.md", tmp_path / "prop.md")
        assert result.status == "fail"
        assert "frontmatter_fields" in result.message

    def test_updated_at_change_passes(self, tmp_path: Path) -> None:
        orig = _page("title: A\nupdated_at: 2025-01-01", "Body")
        prop = _page("title: A\nupdated_at: 2025-07-25", "Body")
        (tmp_path / "orig.md").write_text(orig)
        (tmp_path / "prop.md").write_text(prop)
        result = validate_afk_output(tmp_path / "orig.md", tmp_path / "prop.md")
        assert result.status == "pass"
