"""Unit tests for scripts/drive_monitor/_validators.py."""

from __future__ import annotations

import pytest
from pathlib import Path

from scripts.drive_monitor._validators import (
    validate_alias,
    validate_file_id,
    validate_display_name,
    build_drive_asset_path,
    build_wiki_page_path,
)


class TestValidateAlias:
    def test_valid(self):
        assert validate_alias("my-docs") == "my-docs"
        assert validate_alias("a") == "a"
        assert validate_alias("cms-policy-2025") == "cms-policy-2025"

    def test_uppercase_rejected(self):
        with pytest.raises(ValueError):
            validate_alias("MyDocs")

    def test_underscore_rejected(self):
        with pytest.raises(ValueError):
            validate_alias("my_docs")

    def test_leading_hyphen_rejected(self):
        with pytest.raises(ValueError):
            validate_alias("-docs")

    def test_trailing_hyphen_rejected(self):
        with pytest.raises(ValueError):
            validate_alias("docs-")

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            validate_alias("")

    def test_slash_rejected(self):
        with pytest.raises(ValueError):
            validate_alias("my/docs")

    def test_non_string_rejected(self):
        with pytest.raises(ValueError):
            validate_alias(None)  # type: ignore


class TestValidateFileId:
    def test_valid_alphanumeric(self):
        assert validate_file_id("ABC123") == "ABC123"
        assert validate_file_id("1a2b3c") == "1a2b3c"
        assert validate_file_id("file_id-001") == "file_id-001"

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            validate_file_id("")

    def test_path_traversal_rejected(self):
        with pytest.raises(ValueError):
            validate_file_id("../etc/passwd")

    def test_slash_rejected(self):
        with pytest.raises(ValueError):
            validate_file_id("folder/file")

    def test_space_rejected(self):
        with pytest.raises(ValueError):
            validate_file_id("file id")


class TestValidateDisplayName:
    def test_valid(self):
        assert validate_display_name("My Document.md") == "My Document.md"
        assert validate_display_name("report-2025.pdf") == "report-2025.pdf"

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            validate_display_name("")

    def test_path_separator_rejected(self):
        with pytest.raises(ValueError):
            validate_display_name("folder/file.md")
        with pytest.raises(ValueError):
            validate_display_name("folder\\file.md")

    def test_dotdot_rejected(self):
        with pytest.raises(ValueError):
            validate_display_name("..")

    def test_control_characters_rejected(self):
        with pytest.raises(ValueError):
            validate_display_name("file\x00name")


class TestBuildDriveAssetPath:
    def test_valid_native_path(self, tmp_path):
        path = build_drive_asset_path(
            tmp_path, "my-docs", "abc123", "42", "document.md"
        )
        expected = tmp_path / "raw" / "assets" / "gdrive" / "my-docs" / "abc123" / "42" / "document.md"
        assert path == expected.resolve()

    def test_valid_non_native_path(self, tmp_path):
        md5 = "a" * 32
        path = build_drive_asset_path(
            tmp_path, "my-docs", "abc123", md5, "report.pdf"
        )
        expected = tmp_path / "raw" / "assets" / "gdrive" / "my-docs" / "abc123" / md5 / "report.pdf"
        assert path == expected.resolve()

    def test_invalid_alias_raises(self, tmp_path):
        with pytest.raises(ValueError):
            build_drive_asset_path(tmp_path, "INVALID_ALIAS", "abc123", "42", "doc.md")

    def test_invalid_file_id_raises(self, tmp_path):
        with pytest.raises(ValueError):
            build_drive_asset_path(tmp_path, "my-docs", "../evil", "42", "doc.md")

    def test_invalid_version_segment_raises(self, tmp_path):
        with pytest.raises(ValueError):
            build_drive_asset_path(tmp_path, "my-docs", "abc", "version@evil", "doc.md")

    def test_path_escapes_boundary_rejected(self, tmp_path):
        # A path containing a traversal-based filename should be caught
        with pytest.raises(ValueError):
            validate_display_name("../../../etc/passwd")


class TestBuildWikiPagePath:
    def test_valid_wiki_page(self, tmp_path):
        wiki_page = "wiki/pages/topical/doc.md"
        path = build_wiki_page_path(tmp_path, wiki_page)
        expected = (tmp_path / wiki_page).resolve()
        assert path == expected

    def test_path_outside_wiki_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="wiki"):
            build_wiki_page_path(tmp_path, "raw/inbox/evil.md")

    def test_traversal_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="wiki"):
            build_wiki_page_path(tmp_path, "wiki/../../etc/passwd")
