"""Unit tests for scripts/drive_monitor/fetch_content.py."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from scripts.drive_monitor.fetch_content import fetch_content


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NORMALIZED_BYTES = b"# My Document\n\nContent.\n"
MD5 = hashlib.md5(b"raw-pdf-content").hexdigest()
SHA256 = hashlib.sha256(NORMALIZED_BYTES).hexdigest()


def _drifted_entry(
    event_type="content_changed",
    file_id="file1",
    alias="my-docs",
    display_name="doc.md",
    mime_type="application/vnd.google-apps.document",
    current_drive_version=5,
    md5_checksum=None,
    **extra,
) -> dict:
    entry = {
        "alias": alias,
        "file_id": file_id,
        "display_name": display_name,
        "mime_type": mime_type,
        "event_type": event_type,
        "current_drive_version": current_drive_version,
        "current_md5_checksum": md5_checksum,
        **extra,
    }
    return entry


def _make_drift_report(
    drifted: list[dict],
    alias: str = "my-docs",
    new_page_token: str = "tok_new",
) -> dict:
    return {
        "version": "1",
        "generated_at": "2026-01-01T00:00:00Z",
        "registry": f"raw/drive-sources/{alias}.source-registry.json",
        "new_page_token": new_page_token,
        "has_drift": bool(drifted),
        "drifted": drifted,
        "up_to_date": [],
        "uninitialized": [],
        "errors": [],
    }


def _write_registry(tmp_path: Path, alias: str = "my-docs") -> Path:
    drive_dir = tmp_path / "raw" / "drive-sources"
    drive_dir.mkdir(parents=True, exist_ok=True)
    registry = {
        "version": "1",
        "alias": alias,
        "credential_secret_name": "GDRIVE_SA_KEY",
        "changes_page_token": "tok_abc",
        "last_full_scan_at": None,
        "folder_entries": [{
            "folder_id": "FOLDER1",
            "folder_name": "Test",
            "wiki_namespace": "cms/",
            "tracking_status": "active",
        }],
        "file_entries": [{
            "file_id": "file1",
            "tracking_status": "active",
            "display_name": "doc.md",
            "mime_type": "application/vnd.google-apps.document",
        }],
    }
    p = drive_dir / f"{alias}.source-registry.json"
    p.write_text(json.dumps(registry))
    (tmp_path / "AGENTS.md").touch()
    (tmp_path / "AGENTS.md").touch()

    (tmp_path / "wiki").mkdir(exist_ok=True)
    return p


def _write_drift_report(tmp_path: Path, report: dict) -> Path:
    p = tmp_path / "drift-report.json"
    p.write_text(json.dumps(report))
    return p


# ---------------------------------------------------------------------------
# Approval gate
# ---------------------------------------------------------------------------

class TestFetchContentApprovalGate:
    def test_missing_approval_fails_closed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GDRIVE_SA_KEY", "{}")
        reg_path = _write_registry(tmp_path)
        report = _make_drift_report([_drifted_entry()])
        report_path = _write_drift_report(tmp_path, report)

        result = fetch_content(
            repo_root=tmp_path,
            drift_report_path=report_path,
            approval="pending",
        )
        assert result.status == "fail"
        assert "approval" in result.reason_code

    def test_approved_proceeds(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GDRIVE_SA_KEY", json.dumps({"type": "service_account"}))
        reg_path = _write_registry(tmp_path)
        report = _make_drift_report([_drifted_entry(event_type="content_changed")])
        report_path = _write_drift_report(tmp_path, report)

        with (
            patch("scripts.drive_monitor.fetch_content.build_drive_client"),
            patch(
                "scripts.drive_monitor.fetch_content.export_file_as_markdown",
                return_value=b"# Doc\r\n\r\nContent.  \r\n",
            ),
            patch("scripts.drive_monitor.fetch_content.update_last_fetched"),
        ):
            # Should not raise
            fetch_content(
                repo_root=tmp_path,
                drift_report_path=report_path,
                approval="approved",
            )


# ---------------------------------------------------------------------------
# Native Docs export + normalization
# ---------------------------------------------------------------------------

class TestFetchContentNativeDoc:
    def test_google_doc_is_normalized_before_write(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GDRIVE_SA_KEY", json.dumps({"type": "service_account"}))
        _write_registry(tmp_path)
        entry = _drifted_entry(
            mime_type="application/vnd.google-apps.document",
            current_drive_version=5,
        )
        report_path = _write_drift_report(tmp_path, _make_drift_report([entry]))

        raw_export = b"# Doc\r\n\r\nContent.  \r\n\r\n"
        expected_normalized = b"# Doc\n\nContent.\n"

        written_files = {}

        def fake_exclusive_write(path: Path, content: bytes):
            written_files[str(path)] = content

        with (
            patch("scripts.drive_monitor.fetch_content.build_drive_client"),
            patch(
                "scripts.drive_monitor.fetch_content.export_file_as_markdown",
                return_value=raw_export,
            ),
            patch(
                "scripts.drive_monitor.fetch_content.exclusive_create_write_once",
                side_effect=fake_exclusive_write,
            ),
            patch("scripts.drive_monitor.fetch_content.update_last_fetched"),
        ):
            fetch_content(
                repo_root=tmp_path,
                drift_report_path=report_path,
                approval="approved",
            )

        # Exactly one file should be written
        assert len(written_files) == 1
        (written_path, written_content) = next(iter(written_files.items()))
        assert written_content == expected_normalized

    def test_asset_path_uses_drive_version_for_native(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GDRIVE_SA_KEY", json.dumps({"type": "service_account"}))
        _write_registry(tmp_path)
        entry = _drifted_entry(current_drive_version=42)
        report_path = _write_drift_report(tmp_path, _make_drift_report([entry]))

        written_paths = []

        def capture_path(path: Path, content: bytes):
            written_paths.append(path)

        with (
            patch("scripts.drive_monitor.fetch_content.build_drive_client"),
            patch(
                "scripts.drive_monitor.fetch_content.export_file_as_markdown",
                return_value=b"content\n",
            ),
            patch(
                "scripts.drive_monitor.fetch_content.exclusive_create_write_once",
                side_effect=capture_path,
            ),
            patch("scripts.drive_monitor.fetch_content.update_last_fetched"),
        ):
            fetch_content(
                repo_root=tmp_path,
                drift_report_path=report_path,
                approval="approved",
            )

        assert len(written_paths) == 1
        # The path should contain the drive version "42"
        assert "42" in str(written_paths[0])

    def test_sha256_written_to_registry(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GDRIVE_SA_KEY", json.dumps({"type": "service_account"}))
        _write_registry(tmp_path)
        entry = _drifted_entry()
        report_path = _write_drift_report(tmp_path, _make_drift_report([entry]))

        exported_bytes = b"# Doc\n\nContent.\n"
        expected_sha = hashlib.sha256(exported_bytes).hexdigest()

        captured_calls = {}

        def capture_registry(repo_root, alias, file_id, **kwargs):
            captured_calls["kwargs"] = kwargs

        with (
            patch("scripts.drive_monitor.fetch_content.build_drive_client"),
            patch(
                "scripts.drive_monitor.fetch_content.export_file_as_markdown",
                return_value=exported_bytes,
            ),
            patch("scripts.drive_monitor.fetch_content.exclusive_create_write_once"),
            patch(
                "scripts.drive_monitor.fetch_content.update_last_fetched",
                side_effect=capture_registry,
            ),
        ):
            fetch_content(
                repo_root=tmp_path,
                drift_report_path=report_path,
                approval="approved",
            )

        assert captured_calls["kwargs"].get("sha256") == expected_sha


# ---------------------------------------------------------------------------
# Non-native files (PDF, DOCX, text/plain)
# ---------------------------------------------------------------------------

class TestFetchContentNonNative:
    def test_pdf_uses_md5_in_asset_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GDRIVE_SA_KEY", json.dumps({"type": "service_account"}))
        drive_dir = tmp_path / "raw" / "drive-sources"
        drive_dir.mkdir(parents=True, exist_ok=True)
        registry = {
            "version": "1",
            "alias": "my-docs",
            "credential_secret_name": "GDRIVE_SA_KEY",
            "changes_page_token": "tok",
            "last_full_scan_at": None,
            "folder_entries": [],
            "file_entries": [{
                "file_id": "file1",
                "tracking_status": "active",
                "display_name": "report.pdf",
                "mime_type": "application/pdf",
            }],
        }
        (drive_dir / "my-docs.source-registry.json").write_text(json.dumps(registry))
        (tmp_path / "AGENTS.md").touch()

        (tmp_path / "wiki").mkdir(exist_ok=True)

        entry = _drifted_entry(
            mime_type="application/pdf",
            display_name="report.pdf",
            md5_checksum="d41d8cd98f00b204e9800998ecf8427e",
            current_drive_version=None,
        )
        report_path = _write_drift_report(tmp_path, _make_drift_report([entry]))

        written_paths = []

        def capture_path(path: Path, content: bytes):
            written_paths.append(path)

        with (
            patch("scripts.drive_monitor.fetch_content.build_drive_client"),
            patch(
                "scripts.drive_monitor.fetch_content.download_file",
                return_value=b"%PDF-content",
            ),
            patch(
                "scripts.drive_monitor.fetch_content.exclusive_create_write_once",
                side_effect=capture_path,
            ),
            patch("scripts.drive_monitor.fetch_content.update_last_fetched"),
        ):
            fetch_content(
                repo_root=tmp_path,
                drift_report_path=report_path,
                approval="approved",
            )

        assert len(written_paths) == 1
        # MD5 checksum in the path
        assert "d41d8cd98f00b204e9800998ecf8427e" in str(written_paths[0])

    def test_non_native_not_normalized(self, tmp_path, monkeypatch):
        """Non-native files must not be passed through normalize_markdown_export."""
        monkeypatch.setenv("GDRIVE_SA_KEY", json.dumps({"type": "service_account"}))
        drive_dir = tmp_path / "raw" / "drive-sources"
        drive_dir.mkdir(parents=True, exist_ok=True)
        registry = {
            "version": "1",
            "alias": "my-docs",
            "credential_secret_name": "GDRIVE_SA_KEY",
            "changes_page_token": "tok",
            "last_full_scan_at": None,
            "folder_entries": [],
            "file_entries": [{
                "file_id": "file1",
                "tracking_status": "active",
                "display_name": "doc.docx",
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }],
        }
        (drive_dir / "my-docs.source-registry.json").write_text(json.dumps(registry))
        (tmp_path / "AGENTS.md").touch()

        (tmp_path / "wiki").mkdir(exist_ok=True)

        entry = _drifted_entry(
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            display_name="doc.docx",
            md5_checksum="d41d8cd98f00b204e9800998ecf8427e",
            current_drive_version=None,
        )
        report_path = _write_drift_report(tmp_path, _make_drift_report([entry]))

        with (
            patch("scripts.drive_monitor.fetch_content.build_drive_client"),
            patch(
                "scripts.drive_monitor.fetch_content.download_file",
                return_value=b"docx-bytes",
            ),
            patch("scripts.drive_monitor.fetch_content.exclusive_create_write_once"),
            patch("scripts.drive_monitor.fetch_content.update_last_fetched"),
            patch(
                "scripts.drive_monitor.fetch_content.normalize_markdown_export"
            ) as mock_norm,
        ):
            fetch_content(
                repo_root=tmp_path,
                drift_report_path=report_path,
                approval="approved",
            )
        # normalize_markdown_export must NOT be called for non-native files
        mock_norm.assert_not_called()


# ---------------------------------------------------------------------------
# Lock acquisition
# ---------------------------------------------------------------------------

class TestFetchContentLockAcquisition:
    def test_only_drive_sources_lock_acquired(self, tmp_path, monkeypatch):
        """fetch_content acquires only raw/.drive-sources.lock, not wiki/.kb_write.lock."""
        monkeypatch.setenv("GDRIVE_SA_KEY", json.dumps({"type": "service_account"}))
        _write_registry(tmp_path)
        entry = _drifted_entry()
        report_path = _write_drift_report(tmp_path, _make_drift_report([entry]))

        acquired_locks = []

        @contextmanager
        def fake_exclusive_write_lock(repo_root, lock_path):
            acquired_locks.append(Path(lock_path).name)
            yield

        with (
            patch("scripts.drive_monitor.fetch_content.build_drive_client"),
            patch(
                "scripts.drive_monitor.fetch_content.export_file_as_markdown",
                return_value=b"content\n",
            ),
            patch("scripts.drive_monitor.fetch_content.exclusive_create_write_once"),
            patch(
                "scripts.drive_monitor._registry.write_utils.exclusive_write_lock",
                side_effect=fake_exclusive_write_lock,
            ),
        ):
            fetch_content(
                repo_root=tmp_path,
                drift_report_path=report_path,
                approval="approved",
            )

        assert ".drive-sources.lock" in acquired_locks
        assert ".kb_write.lock" not in acquired_locks
