"""Tests for scripts.kb.rejection_validators."""

from __future__ import annotations

import pytest

from scripts.kb.rejection_validators import (
    REJECTION_CATEGORIES,
    validate_category,
    validate_filename,
    validate_frontmatter,
    validate_sha256,
    validate_slug,
)


class TestValidateSlug:
    def test_valid_slug(self) -> None:
        assert validate_slug("cms-manual-chapter-4") == []

    def test_valid_single_char(self) -> None:
        assert validate_slug("a") == []

    def test_empty_slug(self) -> None:
        errors = validate_slug("")
        assert any("empty" in e for e in errors)

    def test_too_long(self) -> None:
        errors = validate_slug("a" * 65)
        assert any("64" in e for e in errors)

    def test_path_separator(self) -> None:
        errors = validate_slug("foo/bar")
        assert any("separator" in e for e in errors)

    def test_backslash(self) -> None:
        errors = validate_slug("foo\\bar")
        assert any("separator" in e for e in errors)

    def test_traversal(self) -> None:
        errors = validate_slug("foo..bar")
        assert any("traversal" in e for e in errors)

    def test_null_byte(self) -> None:
        errors = validate_slug("foo\x00bar")
        assert any("null" in e for e in errors)

    def test_uppercase_rejected(self) -> None:
        errors = validate_slug("FooBar")
        assert any("pattern" in e for e in errors)

    def test_starts_with_hyphen(self) -> None:
        errors = validate_slug("-starts-bad")
        assert any("pattern" in e for e in errors)

    def test_ends_with_hyphen(self) -> None:
        errors = validate_slug("ends-bad-")
        assert any("pattern" in e for e in errors)

    def test_underscore_rejected(self) -> None:
        errors = validate_slug("has_underscore")
        assert any("pattern" in e for e in errors)


class TestValidateSha256:
    def test_valid(self) -> None:
        assert validate_sha256("a" * 64) == []

    def test_empty(self) -> None:
        errors = validate_sha256("")
        assert any("empty" in e for e in errors)

    def test_too_short(self) -> None:
        errors = validate_sha256("abcd")
        assert any("64" in e for e in errors)

    def test_uppercase_rejected(self) -> None:
        errors = validate_sha256("A" * 64)
        assert any("lowercase" in e for e in errors)

    def test_non_hex(self) -> None:
        errors = validate_sha256("g" * 64)
        assert any("hex" in e for e in errors)


class TestValidateCategory:
    def test_all_valid_categories(self) -> None:
        for cat in REJECTION_CATEGORIES:
            assert validate_category(cat) == []

    def test_empty(self) -> None:
        errors = validate_category("")
        assert any("empty" in e for e in errors)

    def test_invalid(self) -> None:
        errors = validate_category("not_a_category")
        assert any("not in allowed set" in e for e in errors)


class TestValidateFilename:
    def test_valid(self) -> None:
        assert validate_filename("cms-manual--a1b2c3d4.rejection.md") == []

    def test_empty(self) -> None:
        errors = validate_filename("")
        assert any("empty" in e for e in errors)

    def test_wrong_suffix(self) -> None:
        errors = validate_filename("foo--abcd1234.md")
        assert any(".rejection.md" in e for e in errors)

    def test_no_separator(self) -> None:
        errors = validate_filename("noseparator.rejection.md")
        assert any("--" in e for e in errors)

    def test_sha_prefix_wrong_length(self) -> None:
        errors = validate_filename("slug--abc.rejection.md")
        assert any("8 characters" in e for e in errors)

    def test_sha_prefix_uppercase(self) -> None:
        errors = validate_filename("slug--ABCD1234.rejection.md")
        assert any("lowercase" in e for e in errors)


class TestValidateFrontmatter:
    def _valid_fields(self) -> dict:
        return {
            "slug": "test-source",
            "sha256": "a" * 64,
            "rejected_date": "2025-01-01T00:00:00Z",
            "source_path": "raw/inbox/test.pdf",
            "rejection_reason": "Test reason",
            "rejection_category": "out_of_scope",
            "reviewed_by": "operator",
            "reconsidered_date": "null",
        }

    def test_valid(self) -> None:
        assert validate_frontmatter(self._valid_fields()) == []

    def test_missing_field(self) -> None:
        fields = self._valid_fields()
        del fields["slug"]
        errors = validate_frontmatter(fields)
        assert any("missing" in e for e in errors)

    def test_invalid_category(self) -> None:
        fields = self._valid_fields()
        fields["rejection_category"] = "bad"
        errors = validate_frontmatter(fields)
        assert any("not in allowed set" in e for e in errors)
