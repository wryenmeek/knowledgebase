"""Unit tests for scripts/drive_monitor/create_issues.py (CR-3)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.drive_monitor.create_issues import (
    _build_issue_for_entry,
    _redact_stderr,
    _sanitize_gh_md,
    _search_existing_issue,
    create_issues,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    event_type: str = "content_changed",
    alias: str = "my-docs",
    file_id: str = "FILE_ABC123",
    display_name: str = "Document A.md",
    mime_type: str = "application/vnd.google-apps.document",
    wiki_page: str = "wiki/cms/document-a.md",
    current_drive_version: int | None = 10,
    **extra,
) -> dict:
    entry: dict = {
        "alias": alias,
        "file_id": file_id,
        "display_name": display_name,
        "mime_type": mime_type,
        "event_type": event_type,
        "wiki_page": wiki_page,
    }
    if current_drive_version is not None:
        entry["current_drive_version"] = current_drive_version
    entry.update(extra)
    return entry


def _write_hitl_entries(tmp_path: Path, entries: list[dict]) -> Path:
    p = tmp_path / "hitl-entries.json"
    p.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Spec scenario tests (success criterion #5)
# ---------------------------------------------------------------------------


class TestSpecScenarios:
    """Tests matching the three spec scenarios: deletion, out-of-scope, bulk."""

    @patch("scripts.drive_monitor.create_issues._create_issue", return_value=True)
    @patch("scripts.drive_monitor.create_issues._search_existing_issue", return_value=None)
    def test_deleted_entry_creates_issue(self, mock_search, mock_create, tmp_path):
        """Spec: single deletion → HITL Issue with 'deleted' label."""
        entry = _make_entry(event_type="deleted", current_drive_version=None)
        path = _write_hitl_entries(tmp_path, [entry])

        result = create_issues(path)

        assert result.status == "pass"
        assert result.summary["created"] == 1
        _, body, labels = mock_create.call_args[0]
        assert "deleted" in labels
        assert "lifecycle event" in body

    @patch("scripts.drive_monitor.create_issues._create_issue", return_value=True)
    @patch("scripts.drive_monitor.create_issues._search_existing_issue", return_value=None)
    def test_out_of_scope_entry_creates_issue(self, mock_search, mock_create, tmp_path):
        """Spec: out-of-scope MIME change → HITL Issue with 'out_of_scope' label."""
        entry = _make_entry(event_type="out_of_scope", current_drive_version=None)
        path = _write_hitl_entries(tmp_path, [entry])

        result = create_issues(path)

        assert result.status == "pass"
        assert result.summary["created"] == 1
        _, body, labels = mock_create.call_args[0]
        assert "out_of_scope" in labels
        assert "MIME type changed" in body

    @patch("scripts.drive_monitor.create_issues._create_issue", return_value=True)
    @patch("scripts.drive_monitor.create_issues._search_existing_issue", return_value=None)
    def test_content_changed_creates_issue(self, mock_search, mock_create, tmp_path):
        """Spec: content_changed → HITL Issue for human review."""
        entry = _make_entry(event_type="content_changed")
        path = _write_hitl_entries(tmp_path, [entry])

        result = create_issues(path)

        assert result.status == "pass"
        assert result.summary["created"] == 1
        title, body, labels = mock_create.call_args[0]
        assert "content_changed" in title
        assert "Drive source change detected" in body
        assert "drive-monitor" in labels


# ---------------------------------------------------------------------------
# Deduplication tests
# ---------------------------------------------------------------------------


class TestDeduplication:
    """Dedup via _search_existing_issue body-embedded key."""

    @patch("scripts.drive_monitor.create_issues._update_issue", return_value=True)
    @patch("scripts.drive_monitor.create_issues._search_existing_issue", return_value=42)
    def test_existing_issue_gets_comment_not_new_issue(self, mock_search, mock_update, tmp_path):
        entry = _make_entry(event_type="content_changed")
        path = _write_hitl_entries(tmp_path, [entry])

        result = create_issues(path)

        assert result.status == "pass"
        assert result.summary["updated"] == 1
        assert result.summary["created"] == 0
        mock_update.assert_called_once()
        assert mock_update.call_args[0][0] == 42

    @patch("scripts.drive_monitor.create_issues._create_issue", return_value=True)
    @patch("scripts.drive_monitor.create_issues._search_existing_issue", return_value=None)
    def test_no_existing_issue_creates_new(self, mock_search, mock_create, tmp_path):
        entry = _make_entry(event_type="trashed", current_drive_version=None)
        path = _write_hitl_entries(tmp_path, [entry])

        result = create_issues(path)

        assert result.status == "pass"
        assert result.summary["created"] == 1
        mock_create.assert_called_once()

    @patch("subprocess.run")
    def test_search_existing_issue_parses_gh_output(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([{"number": 99}]),
            stderr="",
        )
        assert _search_existing_issue("gdrive-monitor-dedupe:a:b:c") == 99

    @patch("subprocess.run")
    def test_search_existing_issue_returns_none_on_empty(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="[]", stderr=""
        )
        assert _search_existing_issue("gdrive-monitor-dedupe:a:b:c") is None


# ---------------------------------------------------------------------------
# gh CLI failure handling
# ---------------------------------------------------------------------------


class TestGhCliFailure:
    @patch("scripts.drive_monitor.create_issues._search_existing_issue", return_value=None)
    @patch("subprocess.run")
    def test_gh_create_failure_counts_error(self, mock_run, mock_search, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="some error"
        )
        entry = _make_entry(event_type="new_file")
        path = _write_hitl_entries(tmp_path, [entry])

        result = create_issues(path)

        assert result.status == "fail"
        assert result.summary["errors"] == 1

    @patch("subprocess.run")
    def test_search_existing_issue_returns_none_on_gh_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="gh: not logged in"
        )
        assert _search_existing_issue("key") is None


# ---------------------------------------------------------------------------
# _redact_stderr tests (ME-7 hardening)
# ---------------------------------------------------------------------------


class TestRedactStderr:
    def test_redacts_ghp_token(self):
        assert "[REDACTED]" in _redact_stderr("token: ghp_abc123XYZ")

    def test_redacts_github_pat_token(self):
        assert "[REDACTED]" in _redact_stderr("github_pat_ABCDEF1234_extra")

    def test_redacts_gho_token(self):
        assert "[REDACTED]" in _redact_stderr("gho_AbCdEf12345")

    def test_redacts_authorization_header(self):
        result = _redact_stderr("Authorization: Bearer sometoken123")
        assert "Bearer" not in result
        assert "[REDACTED]" in result

    def test_redacts_long_hex(self):
        hex_string = "a" * 40
        result = _redact_stderr(f"sha={hex_string}")
        assert hex_string not in result

    def test_redacts_base64_blob(self):
        b64 = "U29tZVNlY3JldEtleVRoYXRJc0xvbmdFbm91Z2g="
        result = _redact_stderr(f"key: {b64}")
        assert b64 not in result

    def test_truncates_long_stderr(self):
        long_msg = "x" * 500
        result = _redact_stderr(long_msg)
        assert len(result) <= 200


# ---------------------------------------------------------------------------
# _sanitize_gh_md tests (ME-10 hardening)
# ---------------------------------------------------------------------------


class TestSanitizeGhMd:
    def test_strips_actions_expression(self):
        result = _sanitize_gh_md("Hello ${{ secrets.TOKEN }} world")
        assert "${{" not in result
        assert "}}" not in result
        assert "[expr]" in result

    def test_strips_backticks(self):
        assert "`" not in _sanitize_gh_md("run `rm -rf /`")

    def test_strips_at_mentions(self):
        assert "@admin" not in _sanitize_gh_md("cc @admin please")

    def test_strips_image_markdown(self):
        result = _sanitize_gh_md("![alt](http://evil.com/img.png)")
        assert "![" not in result

    def test_strips_issue_closing_keywords(self):
        result = _sanitize_gh_md("fixes #42")
        assert "#42" not in result

    def test_strips_angle_brackets(self):
        result = _sanitize_gh_md("<script>alert(1)</script>")
        assert "<" not in result
        assert ">" not in result

    def test_truncates_to_max_len(self):
        result = _sanitize_gh_md("a" * 500, max_len=50)
        assert len(result) <= 50


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_entries_returns_pass(self, tmp_path):
        path = _write_hitl_entries(tmp_path, [])

        result = create_issues(path)

        assert result.status == "pass"
        assert result.reason_code == "no_hitl_entries"

    def test_missing_file_returns_fail(self, tmp_path):
        result = create_issues(tmp_path / "nonexistent.json")

        assert result.status == "fail"
        assert result.reason_code == "invalid_input"

    def test_malformed_json_returns_fail(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json at all", encoding="utf-8")

        result = create_issues(p)

        assert result.status == "fail"
        assert result.reason_code == "invalid_input"

    @patch("scripts.drive_monitor.create_issues._create_issue", return_value=True)
    @patch("scripts.drive_monitor.create_issues._search_existing_issue", return_value=None)
    def test_unknown_event_type_skipped(self, mock_search, mock_create, tmp_path):
        entry = _make_entry(event_type="unknown_event")
        path = _write_hitl_entries(tmp_path, [entry])

        result = create_issues(path)

        assert result.summary["skipped"] == 1
        mock_create.assert_not_called()

    @patch("scripts.drive_monitor.create_issues._create_issue", return_value=True)
    @patch("scripts.drive_monitor.create_issues._search_existing_issue", return_value=None)
    def test_entry_with_missing_fields_uses_defaults(self, mock_search, mock_create, tmp_path):
        entry = {"event_type": "content_changed"}
        path = _write_hitl_entries(tmp_path, [entry])

        result = create_issues(path)

        assert result.status == "pass"
        assert result.summary["created"] == 1

    @patch("scripts.drive_monitor.create_issues._create_issue", return_value=True)
    @patch("scripts.drive_monitor.create_issues._search_existing_issue", return_value=None)
    def test_bulk_aggregation_creates_bulk_issue(self, mock_search, mock_create, tmp_path):
        entry = _make_entry(
            event_type="trashed",
            is_bulk_aggregation=True,
            bulk_count=4,
            parent_folder_id="FOLDER_XYZ",
            bulk_file_ids=["f1", "f2", "f3", "f4"],
            current_drive_version=None,
        )
        path = _write_hitl_entries(tmp_path, [entry])

        result = create_issues(path)

        assert result.status == "pass"
        assert result.summary["created"] == 1
        title, body, labels = mock_create.call_args[0]
        assert "Bulk" in title
        assert "bulk-event" in labels
        assert "4 files" in body


# ---------------------------------------------------------------------------
# _build_issue_for_entry unit tests
# ---------------------------------------------------------------------------


class TestBuildIssueForEntry:
    def test_returns_none_for_unknown_event(self):
        assert _build_issue_for_entry({"event_type": "bizarre"}) is None

    def test_new_file_uses_content_changed_body(self):
        entry = _make_entry(event_type="new_file")
        title, body, labels = _build_issue_for_entry(entry)
        assert "new_file" in title
        assert "Drive source change detected" in body
        assert labels == ["drive-monitor", "hitl"]

    def test_trashed_uses_deletion_body(self):
        entry = _make_entry(event_type="trashed", current_drive_version=None)
        title, body, labels = _build_issue_for_entry(entry)
        assert "trashed" in title
        assert "moved to Trash" in body
        assert "trashed" in labels

    def test_dedupe_key_in_body(self):
        entry = _make_entry(event_type="deleted", alias="a", file_id="f1")
        _, body, _ = _build_issue_for_entry(entry)
        assert "gdrive-monitor-dedupe:a:f1:deleted" in body
