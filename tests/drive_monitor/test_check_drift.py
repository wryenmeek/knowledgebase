"""Unit tests for scripts/drive_monitor/check_drift.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.drive_monitor.check_drift import check_drift, _resolve_parent_folder


def _make_registry(
    alias: str = "my-docs",
    changes_page_token: str | None = "token_abc",
    folder_entries=None,
    file_entries=None,
) -> dict:
    return {
        "version": "1",
        "alias": alias,
        "credential_secret_name": "GDRIVE_SA_KEY",
        "changes_page_token": changes_page_token,
        "last_full_scan_at": None,
        "folder_entries": folder_entries or [
            {
                "folder_id": "FOLDER1",
                "folder_name": "Test Folder",
                "wiki_namespace": "cms/",
                "tracking_status": "active",
            }
        ],
        "file_entries": file_entries or [],
    }


def _write_registry(tmp_path: Path, registry: dict) -> Path:
    drive_dir = tmp_path / "raw" / "drive-sources"
    drive_dir.mkdir(parents=True, exist_ok=True)
    p = drive_dir / f"{registry['alias']}.source-registry.json"
    p.write_text(json.dumps(registry), encoding="utf-8")
    # looks_like_repo_root() requires AGENTS.md
    (tmp_path / "AGENTS.md").touch()
    (tmp_path / "wiki").mkdir(exist_ok=True)
    (tmp_path / "raw" / "assets" / "gdrive").mkdir(parents=True, exist_ok=True)
    return p


def _make_mock_drive(changes: list[dict] | None = None, new_token: str = "token_xyz"):
    """Return a mock Drive client that returns specified changes."""
    drive = MagicMock()
    return drive, changes or [], new_token


class TestCheckDriftNoRegistries:
    def test_no_registries_returns_pass(self, tmp_path):
        (tmp_path / "AGENTS.md").touch()
        (tmp_path / "wiki").mkdir()
        (tmp_path / "raw" / "drive-sources").mkdir(parents=True)
        output = tmp_path / "drift-report.json"
        result = check_drift(
            repo_root=tmp_path,
            registry_paths=[],
            output_path=output,
        )
        assert result.status == "pass"
        assert output.exists()
        data = json.loads(output.read_text())
        assert data["has_drift"] is False
        assert data["drifted"] == []


class TestCheckDriftUninitializedCursor:
    def test_uninitialized_cursor_returns_uninitialized_entries(self, tmp_path):
        registry = _make_registry(changes_page_token=None, file_entries=[
            {"file_id": "file1", "tracking_status": "active", "display_name": "Doc1"},
        ])
        reg_path = _write_registry(tmp_path, registry)
        output = tmp_path / "drift-report.json"

        with (
            patch("scripts.drive_monitor.check_drift.build_drive_client"),
            patch(
                "scripts.drive_monitor.check_drift.get_changes_start_page_token",
                return_value="new_token_123",
            ),
        ):
            result = check_drift(
                repo_root=tmp_path,
                registry_paths=[reg_path],
                output_path=output,
            )

        assert result.status == "pass"
        data = json.loads(output.read_text())
        assert data["has_drift"] is False
        assert len(data["uninitialized"]) == 1
        assert data["uninitialized"][0]["file_id"] == "file1"


class TestCheckDriftContentChanged:
    def test_native_doc_version_change_detected(self, tmp_path):
        registry = _make_registry(
            changes_page_token="token_abc",
            file_entries=[{
                "file_id": "file1",
                "tracking_status": "active",
                "display_name": "My Doc",
                "mime_type": "application/vnd.google-apps.document",
                "last_applied_drive_version": 10,
                "sha256_at_last_applied": None,
                "wiki_page": "wiki/cms/my-doc.md",
            }],
        )
        reg_path = _write_registry(tmp_path, registry)
        output = tmp_path / "drift-report.json"

        mock_changes = [
            {
                "fileId": "file1",
                "removed": False,
                "file": {
                    "id": "file1",
                    "name": "My Doc",
                    "mimeType": "application/vnd.google-apps.document",
                    "version": 15,
                    "trashed": False,
                    "explicitlyTrashed": False,
                    "parents": ["FOLDER1"],
                },
            }
        ]

        with (
            patch("scripts.drive_monitor.check_drift.build_drive_client"),
            patch(
                "scripts.drive_monitor.check_drift.list_changes",
                return_value=(mock_changes, "token_xyz"),
            ),
        ):
            result = check_drift(
                repo_root=tmp_path,
                registry_paths=[reg_path],
                output_path=output,
            )

        data = json.loads(output.read_text())
        assert data["has_drift"] is True
        assert len(data["drifted"]) == 1
        drifted = data["drifted"][0]
        assert drifted["event_type"] == "content_changed"
        assert drifted["current_drive_version"] == 15
        assert drifted["last_applied_drive_version"] == 10

    def test_native_doc_same_version_not_drifted(self, tmp_path):
        registry = _make_registry(
            changes_page_token="token_abc",
            file_entries=[{
                "file_id": "file1",
                "tracking_status": "active",
                "display_name": "My Doc",
                "mime_type": "application/vnd.google-apps.document",
                "last_applied_drive_version": 10,
                "wiki_page": "wiki/cms/my-doc.md",
            }],
        )
        reg_path = _write_registry(tmp_path, registry)
        output = tmp_path / "drift-report.json"

        mock_changes = [
            {
                "fileId": "file1",
                "removed": False,
                "file": {
                    "id": "file1",
                    "name": "My Doc",
                    "mimeType": "application/vnd.google-apps.document",
                    "version": 10,  # same version
                    "trashed": False,
                    "explicitlyTrashed": False,
                },
            }
        ]

        with (
            patch("scripts.drive_monitor.check_drift.build_drive_client"),
            patch(
                "scripts.drive_monitor.check_drift.list_changes",
                return_value=(mock_changes, "token_xyz"),
            ),
        ):
            result = check_drift(
                repo_root=tmp_path,
                registry_paths=[reg_path],
                output_path=output,
            )

        data = json.loads(output.read_text())
        assert data["has_drift"] is False
        assert data["up_to_date"][0]["file_id"] == "file1"


class TestCheckDriftDeletion:
    def test_trashed_file_detected(self, tmp_path):
        registry = _make_registry(
            changes_page_token="token_abc",
            file_entries=[{
                "file_id": "file1",
                "tracking_status": "active",
                "display_name": "My Doc",
                "mime_type": "application/vnd.google-apps.document",
                "last_applied_drive_version": 5,
                "wiki_page": "wiki/cms/my-doc.md",
            }],
        )
        reg_path = _write_registry(tmp_path, registry)
        output = tmp_path / "drift-report.json"

        mock_changes = [
            {
                "fileId": "file1",
                "removed": False,
                "file": {
                    "id": "file1",
                    "name": "My Doc",
                    "mimeType": "application/vnd.google-apps.document",
                    "version": 6,
                    "trashed": True,
                },
            }
        ]

        with (
            patch("scripts.drive_monitor.check_drift.build_drive_client"),
            patch(
                "scripts.drive_monitor.check_drift.list_changes",
                return_value=(mock_changes, "token_xyz"),
            ),
        ):
            check_drift(
                repo_root=tmp_path,
                registry_paths=[reg_path],
                output_path=output,
            )

        data = json.loads(output.read_text())
        assert data["has_drift"] is True
        assert data["drifted"][0]["event_type"] == "trashed"

    def test_removed_file_detected(self, tmp_path):
        registry = _make_registry(
            changes_page_token="token_abc",
            file_entries=[{
                "file_id": "file1",
                "tracking_status": "active",
                "display_name": "My Doc",
                "mime_type": "application/vnd.google-apps.document",
                "wiki_page": "wiki/cms/my-doc.md",
            }],
        )
        reg_path = _write_registry(tmp_path, registry)
        output = tmp_path / "drift-report.json"

        mock_changes = [{"fileId": "file1", "removed": True}]

        with (
            patch("scripts.drive_monitor.check_drift.build_drive_client"),
            patch(
                "scripts.drive_monitor.check_drift.list_changes",
                return_value=(mock_changes, "token_xyz"),
            ),
        ):
            check_drift(
                repo_root=tmp_path,
                registry_paths=[reg_path],
                output_path=output,
            )

        data = json.loads(output.read_text())
        assert data["drifted"][0]["event_type"] == "deleted"


class TestCheckDriftNewFile:
    def test_new_file_under_registered_folder_detected(self, tmp_path):
        registry = _make_registry(
            changes_page_token="token_abc",
            folder_entries=[{
                "folder_id": "FOLDER1",
                "folder_name": "Test Folder",
                "wiki_namespace": "cms/",
                "tracking_status": "active",
            }],
            file_entries=[],  # No existing file entries
        )
        reg_path = _write_registry(tmp_path, registry)
        output = tmp_path / "drift-report.json"

        mock_changes = [
            {
                "fileId": "newfile1",
                "removed": False,
                "file": {
                    "id": "newfile1",
                    "name": "New Document",
                    "mimeType": "application/vnd.google-apps.document",
                    "version": 1,
                    "trashed": False,
                    "parents": ["FOLDER1"],
                },
            }
        ]

        with (
            patch("scripts.drive_monitor.check_drift.build_drive_client"),
            patch(
                "scripts.drive_monitor.check_drift.list_changes",
                return_value=(mock_changes, "token_xyz"),
            ),
            patch(
                "scripts.drive_monitor.check_drift.get_file_parents",
                return_value=["FOLDER1"],
            ),
        ):
            check_drift(
                repo_root=tmp_path,
                registry_paths=[reg_path],
                output_path=output,
            )

        data = json.loads(output.read_text())
        assert data["has_drift"] is True
        assert data["drifted"][0]["event_type"] == "new_file"
        assert data["drifted"][0]["file_id"] == "newfile1"
        assert data["drifted"][0]["parent_folder_id"] == "FOLDER1"


class TestCheckDriftOutOfScope:
    def test_unsupported_mime_type_detected(self, tmp_path):
        registry = _make_registry(
            changes_page_token="token_abc",
            file_entries=[{
                "file_id": "file1",
                "tracking_status": "active",
                "display_name": "Spreadsheet",
                "mime_type": "application/vnd.google-apps.document",
                "wiki_page": "wiki/cms/spreadsheet.md",
            }],
        )
        reg_path = _write_registry(tmp_path, registry)
        output = tmp_path / "drift-report.json"

        mock_changes = [
            {
                "fileId": "file1",
                "removed": False,
                "file": {
                    "id": "file1",
                    "name": "Spreadsheet",
                    "mimeType": "application/vnd.google-apps.spreadsheet",  # not allowed
                    "version": 2,
                    "trashed": False,
                },
            }
        ]

        with (
            patch("scripts.drive_monitor.check_drift.build_drive_client"),
            patch(
                "scripts.drive_monitor.check_drift.list_changes",
                return_value=(mock_changes, "token_xyz"),
            ),
        ):
            check_drift(
                repo_root=tmp_path,
                registry_paths=[reg_path],
                output_path=output,
            )

        data = json.loads(output.read_text())
        assert data["drifted"][0]["event_type"] == "out_of_scope"


class TestResolveParentFolder:
    def test_finds_registered_folder(self):
        mock_drive = MagicMock()
        with patch(
            "scripts.drive_monitor.check_drift.get_file_parents",
            side_effect=[["FOLDER1"]],
        ):
            result = _resolve_parent_folder(mock_drive, "file1", {"FOLDER1"})
        assert result == "FOLDER1"

    def test_returns_none_when_not_found(self):
        mock_drive = MagicMock()
        with patch(
            "scripts.drive_monitor.check_drift.get_file_parents",
            return_value=[],
        ):
            result = _resolve_parent_folder(mock_drive, "file1", {"FOLDER1"})
        assert result is None

    def test_walks_multiple_levels(self):
        mock_drive = MagicMock()
        # file1 → SUBFOLDER → FOLDER1 (registered)
        with patch(
            "scripts.drive_monitor.check_drift.get_file_parents",
            side_effect=[["SUBFOLDER"], ["FOLDER1"]],
        ):
            result = _resolve_parent_folder(mock_drive, "file1", {"FOLDER1"})
        assert result == "FOLDER1"
