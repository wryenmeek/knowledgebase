"""Unit tests for scripts/drive_monitor/advance_cursor.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.drive_monitor.advance_cursor import advance_cursor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_registry(tmp_path: Path, alias: str = "my-docs", token: str = "old_tok") -> Path:
    drive_dir = tmp_path / "raw" / "drive-sources"
    drive_dir.mkdir(parents=True, exist_ok=True)
    registry = {
        "version": "1",
        "alias": alias,
        "credential_secret_name": "GDRIVE_SA_KEY",
        "changes_page_token": token,
        "last_full_scan_at": None,
        "folder_entries": [],
        "file_entries": [],
    }
    p = drive_dir / f"{alias}.source-registry.json"
    p.write_text(json.dumps(registry))
    (tmp_path / "AGENTS.md").touch()
    (tmp_path / "wiki").mkdir(exist_ok=True)
    return p


def _write_drift_report(
    tmp_path: Path,
    cursors: dict[str, str] | None = None,
    errors: list[dict] | None = None,
) -> Path:
    report = {
        "version": "1",
        "generated_at": "2024-01-01T00:00:00+00:00",
        "registry": "raw/drive-sources/",
        "has_drift": False,
        "drifted": [],
        "up_to_date": [],
        "uninitialized": [],
        "errors": errors or [],
        "cursors": cursors or {},
    }
    p = tmp_path / "drift-report.json"
    p.write_text(json.dumps(report))
    return p


# ---------------------------------------------------------------------------
# Approval gate
# ---------------------------------------------------------------------------

class TestAdvanceCursorApproval:
    def test_missing_approval_fails_closed(self, tmp_path):
        report_path = _write_drift_report(tmp_path)
        result = advance_cursor(
            repo_root=tmp_path,
            drift_report_path=report_path,
            approval="pending",
        )
        assert result.status == "fail"


# ---------------------------------------------------------------------------
# Cursor advanced on full success
# ---------------------------------------------------------------------------

class TestAdvanceCursorSuccess:
    def test_cursor_advanced_on_no_errors(self, tmp_path):
        """Cursor advances when no errors exist for the alias."""
        reg_path = _write_registry(tmp_path, alias="my-docs", token="old_tok")
        report_path = _write_drift_report(
            tmp_path,
            cursors={"my-docs": "new_tok_abc"},
        )

        result = advance_cursor(
            repo_root=tmp_path,
            drift_report_path=report_path,
            approval="approved",
        )

        assert result.status == "pass"
        assert result.summary["advanced"] == 1

        # Verify the registry was actually updated
        updated = json.loads(reg_path.read_text())
        assert updated["changes_page_token"] == "new_tok_abc"

    def test_cursor_advanced_for_alias_with_no_drifted_entries(self, tmp_path):
        """Cursor must advance even when drifted=[] for the alias."""
        _write_registry(tmp_path, alias="my-docs", token="old_tok")
        report_path = _write_drift_report(
            tmp_path,
            cursors={"my-docs": "new_tok_no_drift"},
        )

        result = advance_cursor(
            repo_root=tmp_path,
            drift_report_path=report_path,
            approval="approved",
        )

        assert result.status == "pass"
        assert result.summary["advanced"] == 1


# ---------------------------------------------------------------------------
# Cursor NOT advanced on error
# ---------------------------------------------------------------------------

class TestAdvanceCursorErrors:
    def test_cursor_not_advanced_on_alias_error(self, tmp_path):
        """Cursor must NOT advance when the alias had errors."""
        reg_path = _write_registry(tmp_path, alias="my-docs", token="old_tok")
        report_path = _write_drift_report(
            tmp_path,
            cursors={"my-docs": "new_tok_abc"},
            errors=[{
                "alias": "my-docs",
                "file_id": "f1",
                "reason_code": "fetch_failed",
                "message": "API timeout",
            }],
        )

        result = advance_cursor(
            repo_root=tmp_path,
            drift_report_path=report_path,
            approval="approved",
        )

        assert result.status == "pass"
        assert result.summary["skipped"] == 1
        assert result.summary["advanced"] == 0

        # Registry must retain the old token
        updated = json.loads(reg_path.read_text())
        assert updated["changes_page_token"] == "old_tok"

    def test_mixed_aliases_partial_advance(self, tmp_path):
        """Only error-free aliases get cursors advanced."""
        _write_registry(tmp_path, alias="good-alias", token="old_good")
        _write_registry(tmp_path, alias="bad-alias", token="old_bad")

        report_path = _write_drift_report(
            tmp_path,
            cursors={
                "good-alias": "new_good_tok",
                "bad-alias": "new_bad_tok",
            },
            errors=[{
                "alias": "bad-alias",
                "file_id": "f1",
                "reason_code": "fetch_failed",
                "message": "Oops",
            }],
        )

        result = advance_cursor(
            repo_root=tmp_path,
            drift_report_path=report_path,
            approval="approved",
        )

        assert result.summary["advanced"] == 1
        assert result.summary["skipped"] == 1

        good_reg = json.loads(
            (tmp_path / "raw" / "drive-sources" / "good-alias.source-registry.json")
            .read_text()
        )
        bad_reg = json.loads(
            (tmp_path / "raw" / "drive-sources" / "bad-alias.source-registry.json")
            .read_text()
        )
        assert good_reg["changes_page_token"] == "new_good_tok"
        assert bad_reg["changes_page_token"] == "old_bad"


# ---------------------------------------------------------------------------
# No cursors
# ---------------------------------------------------------------------------

class TestAdvanceCursorNoCursors:
    def test_no_cursors_returns_pass(self, tmp_path):
        (tmp_path / "AGENTS.md").touch()
        (tmp_path / "wiki").mkdir(exist_ok=True)
        report_path = _write_drift_report(tmp_path, cursors={})

        result = advance_cursor(
            repo_root=tmp_path,
            drift_report_path=report_path,
            approval="approved",
        )

        assert result.status == "pass"
        assert "No cursors" in result.message
