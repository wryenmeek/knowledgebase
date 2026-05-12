"""Unit tests for scripts/drive_monitor/_types.py."""

from __future__ import annotations

import pytest
from scripts.drive_monitor._types import (
    DRIVE_MIME_ALLOWLIST,
    MIME_EXPORT_MAP,
    REGISTRY_VERSION,
    DRIFT_REPORT_VERSION,
    validate_drive_registry_file,
    validate_drive_drift_report,
)


# ---------------------------------------------------------------------------
# validate_drive_registry_file
# ---------------------------------------------------------------------------

def _minimal_registry(**overrides) -> dict:
    base = {
        "version": "1",
        "alias": "my-docs",
        "credential_secret_name": "GDRIVE_SA_KEY",
        "changes_page_token": None,
        "last_full_scan_at": None,
        "folder_entries": [
            {
                "folder_id": "ABC123",
                "folder_name": "My Folder",
                "wiki_namespace": "cms/",
                "tracking_status": "active",
            }
        ],
        "file_entries": [],
    }
    base.update(overrides)
    return base


class TestValidateDriveRegistryFile:
    def test_valid_minimal(self):
        data = _minimal_registry()
        result = validate_drive_registry_file(data)
        assert result["alias"] == "my-docs"

    def test_wrong_type_rejected(self):
        with pytest.raises(ValueError, match="JSON object"):
            validate_drive_registry_file(["not", "a", "dict"])

    def test_missing_version(self):
        data = _minimal_registry()
        del data["version"]
        with pytest.raises(ValueError, match="missing required field 'version'"):
            validate_drive_registry_file(data)

    def test_wrong_version(self):
        data = _minimal_registry(version="2")
        with pytest.raises(ValueError, match="version must be"):
            validate_drive_registry_file(data)

    def test_invalid_alias_uppercase(self):
        data = _minimal_registry(alias="My-Docs")
        with pytest.raises(ValueError, match="alias"):
            validate_drive_registry_file(data)

    def test_invalid_alias_underscore(self):
        data = _minimal_registry(alias="my_docs")
        with pytest.raises(ValueError, match="alias"):
            validate_drive_registry_file(data)

    def test_invalid_alias_leading_hyphen(self):
        data = _minimal_registry(alias="-docs")
        with pytest.raises(ValueError, match="alias"):
            validate_drive_registry_file(data)

    def test_single_char_alias_valid(self):
        data = _minimal_registry(alias="a")
        result = validate_drive_registry_file(data)
        assert result["alias"] == "a"

    def test_folder_entries_not_list(self):
        data = _minimal_registry(folder_entries="not-a-list")
        with pytest.raises(ValueError, match="list"):
            validate_drive_registry_file(data)

    def test_folder_entry_missing_required_field(self):
        data = _minimal_registry(folder_entries=[{"folder_id": "ABC"}])
        with pytest.raises(ValueError, match="missing required field"):
            validate_drive_registry_file(data)

    def test_folder_entry_invalid_tracking_status(self):
        data = _minimal_registry(folder_entries=[{
            "folder_id": "ABC123",
            "folder_name": "Test",
            "wiki_namespace": "cms/",
            "tracking_status": "unknown_status",
        }])
        with pytest.raises(ValueError, match="unrecognised tracking_status"):
            validate_drive_registry_file(data)

    def test_file_entry_valid(self):
        data = _minimal_registry(file_entries=[{
            "file_id": "file1abc",
            "tracking_status": "active",
        }])
        result = validate_drive_registry_file(data)
        assert result["file_entries"][0]["file_id"] == "file1abc"

    def test_file_entry_invalid_sha256(self):
        data = _minimal_registry(file_entries=[{
            "file_id": "file1",
            "tracking_status": "active",
            "sha256_at_last_applied": "not-a-sha256",
        }])
        with pytest.raises(ValueError, match="sha256_at_last_applied"):
            validate_drive_registry_file(data)

    def test_file_entry_valid_sha256(self):
        sha256 = "a" * 64
        data = _minimal_registry(file_entries=[{
            "file_id": "file1",
            "tracking_status": "active",
            "sha256_at_last_applied": sha256,
        }])
        result = validate_drive_registry_file(data)
        assert result["file_entries"][0]["sha256_at_last_applied"] == sha256

    def test_file_entry_invalid_md5(self):
        data = _minimal_registry(file_entries=[{
            "file_id": "file1",
            "tracking_status": "active",
            "md5_checksum_at_last_applied": "tooshort",
        }])
        with pytest.raises(ValueError, match="md5_checksum_at_last_applied"):
            validate_drive_registry_file(data)

    def test_file_entry_null_fields_allowed(self):
        data = _minimal_registry(file_entries=[{
            "file_id": "file1",
            "tracking_status": "uninitialized",
            "sha256_at_last_applied": None,
            "md5_checksum_at_last_applied": None,
            "drive_version": None,
        }])
        result = validate_drive_registry_file(data)
        assert result["file_entries"][0]["drive_version"] is None

    def test_file_entry_drive_version_must_be_int(self):
        data = _minimal_registry(file_entries=[{
            "file_id": "file1",
            "tracking_status": "active",
            "drive_version": "not-an-int",
        }])
        with pytest.raises(ValueError, match="drive_version"):
            validate_drive_registry_file(data)


# ---------------------------------------------------------------------------
# validate_drive_drift_report
# ---------------------------------------------------------------------------

def _minimal_drift_report(**overrides) -> dict:
    base = {
        "version": "1",
        "generated_at": "2026-01-01T00:00:00Z",
        "registry": "raw/drive-sources/my-docs.source-registry.json",
        "has_drift": False,
        "drifted": [],
        "up_to_date": [],
        "uninitialized": [],
        "errors": [],
    }
    base.update(overrides)
    return base


class TestValidateDriveDriftReport:
    def test_valid_empty(self):
        result = validate_drive_drift_report(_minimal_drift_report())
        assert result["has_drift"] is False

    def test_missing_field(self):
        data = _minimal_drift_report()
        del data["has_drift"]
        with pytest.raises(ValueError, match="missing required field"):
            validate_drive_drift_report(data)

    def test_has_drift_must_be_bool(self):
        data = _minimal_drift_report(has_drift="yes")
        with pytest.raises(ValueError, match="has_drift.*bool"):
            validate_drive_drift_report(data)

    def test_drifted_must_be_list(self):
        data = _minimal_drift_report(drifted="not-a-list")
        with pytest.raises(ValueError, match="drifted.*list"):
            validate_drive_drift_report(data)

    def test_valid_drifted_entry(self):
        data = _minimal_drift_report(
            has_drift=True,
            drifted=[{
                "alias": "my-docs",
                "file_id": "abc123",
                "display_name": "My Doc",
                "mime_type": "application/vnd.google-apps.document",
                "event_type": "content_changed",
            }],
        )
        result = validate_drive_drift_report(data)
        assert result["has_drift"] is True
        assert result["drifted"][0]["event_type"] == "content_changed"

    def test_invalid_event_type(self):
        data = _minimal_drift_report(
            has_drift=True,
            drifted=[{
                "alias": "my-docs",
                "file_id": "abc123",
                "display_name": "My Doc",
                "mime_type": "application/vnd.google-apps.document",
                "event_type": "unknown_event",
            }],
        )
        with pytest.raises(ValueError, match="event_type"):
            validate_drive_drift_report(data)

    def test_invalid_file_id_in_drifted(self):
        data = _minimal_drift_report(
            has_drift=True,
            drifted=[{
                "alias": "my-docs",
                "file_id": "../../../etc/passwd",
                "display_name": "My Doc",
                "mime_type": "application/pdf",
                "event_type": "content_changed",
            }],
        )
        with pytest.raises(ValueError, match="file_id.*unsafe"):
            validate_drive_drift_report(data)


# ---------------------------------------------------------------------------
# MIME constants
# ---------------------------------------------------------------------------

class TestMimeConstants:
    def test_allowlist_not_empty(self):
        assert len(DRIVE_MIME_ALLOWLIST) > 0

    def test_google_doc_in_allowlist(self):
        assert "application/vnd.google-apps.document" in DRIVE_MIME_ALLOWLIST

    def test_pdf_in_allowlist(self):
        assert "application/pdf" in DRIVE_MIME_ALLOWLIST

    def test_google_doc_in_export_map(self):
        assert MIME_EXPORT_MAP["application/vnd.google-apps.document"] == "text/markdown"

    def test_sheets_not_in_allowlist(self):
        assert "application/vnd.google-apps.spreadsheet" not in DRIVE_MIME_ALLOWLIST

    def test_export_map_subset_of_allowlist(self):
        for mime in MIME_EXPORT_MAP:
            assert mime in DRIVE_MIME_ALLOWLIST
