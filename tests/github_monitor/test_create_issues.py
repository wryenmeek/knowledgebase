"""Unit tests for create_issues.py.

Sanitization logic is tested directly. Subprocess-based ``gh`` CLI calls
use monkeypatched helpers for close_resolved_entries tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.github_monitor.create_issues import _sanitize_gh_md, close_resolved_entries


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


class TestCloseResolvedEntries:
    """Tests for close_resolved_entries using mocked subprocess calls."""

    def test_no_up_to_date_entries(self, tmp_path: Path) -> None:
        """Empty up_to_date list returns pass with no work done."""
        report = tmp_path / "report.json"
        report.write_text('{"drifted": [], "up_to_date": []}')
        result = close_resolved_entries(drift_report_path=report)
        assert result.status == "pass"
        assert "No up-to-date" in result.message

    def test_missing_report_file(self) -> None:
        """Missing file returns fail."""
        result = close_resolved_entries(drift_report_path=Path("/nonexistent.json"))
        assert result.status == "fail"
        assert result.reason_code == "invalid_input"

    def test_malformed_json(self, tmp_path: Path) -> None:
        """Malformed JSON returns fail."""
        report = tmp_path / "report.json"
        report.write_text("not json")
        result = close_resolved_entries(drift_report_path=report)
        assert result.status == "fail"
        assert result.reason_code == "invalid_input"

    def test_issue_found_and_closed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When an issue exists for a resolved entry, it gets closed."""
        report = tmp_path / "report.json"
        report.write_text(json.dumps({
            "drifted": [],
            "up_to_date": [{"owner": "org", "repo": "repo", "path": "docs/guide.md"}],
        }))
        monkeypatch.setenv("GITHUB_RUN_ID", "42")

        # Mock _search_existing_issue to return issue number
        monkeypatch.setattr(
            "scripts.github_monitor.create_issues._search_existing_issue",
            lambda key: 99,
        )
        # Mock _close_issue to succeed
        monkeypatch.setattr(
            "scripts.github_monitor.create_issues._close_issue",
            lambda num, run_id: True,
        )

        result = close_resolved_entries(drift_report_path=report)
        assert result.status == "pass"
        assert result.summary["closed"] == 1
        assert result.summary["not_found"] == 0

    def test_issue_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When no issue exists, counts as not_found (not a failure)."""
        report = tmp_path / "report.json"
        report.write_text(json.dumps({
            "drifted": [],
            "up_to_date": [{"owner": "org", "repo": "repo", "path": "docs/guide.md"}],
        }))
        monkeypatch.setattr(
            "scripts.github_monitor.create_issues._search_existing_issue",
            lambda key: None,
        )

        result = close_resolved_entries(drift_report_path=report)
        assert result.status == "pass"
        assert result.summary["not_found"] == 1
        assert result.summary["closed"] == 0

    def test_close_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When _close_issue fails, counts as failed and status is fail."""
        report = tmp_path / "report.json"
        report.write_text(json.dumps({
            "drifted": [],
            "up_to_date": [{"owner": "org", "repo": "repo", "path": "docs/guide.md"}],
        }))
        monkeypatch.setattr(
            "scripts.github_monitor.create_issues._search_existing_issue",
            lambda key: 99,
        )
        monkeypatch.setattr(
            "scripts.github_monitor.create_issues._close_issue",
            lambda num, run_id: False,
        )

        result = close_resolved_entries(drift_report_path=report)
        assert result.status == "fail"
        assert result.reason_code == "close_failed"
        assert result.summary["failed"] == 1
