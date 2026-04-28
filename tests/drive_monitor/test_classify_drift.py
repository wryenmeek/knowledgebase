"""Unit tests for scripts/drive_monitor/classify_drift.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.drive_monitor.classify_drift import classify_drift


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _drifted_entry(
    event_type: str = "content_changed",
    file_id: str = "file1",
    alias: str = "my-docs",
    mime_type: str = "application/vnd.google-apps.document",
    parent_folder_id: str = "FOLDER1",
    tracking_status: str = "active",
    lines_added: int = 5,
    lines_removed: int = 3,
    **extra,
) -> dict:
    return {
        "alias": alias,
        "file_id": file_id,
        "display_name": f"{file_id}.md",
        "mime_type": mime_type,
        "event_type": event_type,
        "parent_folder_id": parent_folder_id,
        "tracking_status": tracking_status,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        **extra,
    }


def _make_drift_report(drifted: list[dict], has_drift: bool = True) -> dict:
    return {
        "version": "1",
        "generated_at": "2026-01-01T00:00:00Z",
        "registry": "raw/drive-sources/my-docs.source-registry.json",
        "new_page_token": "tok_new",
        "has_drift": has_drift,
        "drifted": drifted,
        "up_to_date": [],
        "uninitialized": [],
        "errors": [],
    }


def _write_report(tmp_path: Path, report: dict) -> Path:
    p = tmp_path / "drift-report.json"
    p.write_text(json.dumps(report))
    return p


def _classify(
    tmp_path: Path,
    report: dict,
    afk_max_lines: int = 0,
) -> tuple[list, list]:
    """Helper: run classify_drift and return (afk_entries, hitl_entries)."""
    report_path = _write_report(tmp_path, report)
    output_dir = tmp_path / "classify-out"
    output_dir.mkdir(exist_ok=True)
    classify_drift(
        drift_report_path=report_path,
        output_dir=output_dir,
        afk_max_lines=afk_max_lines,
    )
    afk = json.loads((output_dir / "afk-entries.json").read_text())
    hitl = json.loads((output_dir / "hitl-entries.json").read_text())
    # classify_drift wraps in {"entries": [...]}
    afk_list = afk.get("entries", afk) if isinstance(afk, dict) else afk
    hitl_list = hitl.get("entries", hitl) if isinstance(hitl, dict) else hitl
    return afk_list, hitl_list


# ---------------------------------------------------------------------------
# AFK routing
# ---------------------------------------------------------------------------

class TestClassifyDriftAFKRouting:
    def test_deny_by_default_afk_max_zero(self, tmp_path):
        """afk_max_lines=0 means everything goes HITL."""
        entry = _drifted_entry(event_type="content_changed")
        afk, hitl = _classify(tmp_path, _make_drift_report([entry]), afk_max_lines=0)
        assert afk == []
        assert len(hitl) == 1

    def test_content_changed_google_doc_under_limit_is_afk(self, tmp_path):
        entry = _drifted_entry(
            event_type="content_changed",
            mime_type="application/vnd.google-apps.document",
            lines_added=2,
            lines_removed=1,
        )
        afk, hitl = _classify(tmp_path, _make_drift_report([entry]), afk_max_lines=10)
        assert len(afk) == 1
        assert afk[0]["file_id"] == "file1"

    def test_content_changed_google_doc_over_limit_is_hitl(self, tmp_path):
        entry = _drifted_entry(
            event_type="content_changed",
            mime_type="application/vnd.google-apps.document",
            lines_added=8,
            lines_removed=5,  # total 13 > 10
        )
        afk, hitl = _classify(tmp_path, _make_drift_report([entry]), afk_max_lines=10)
        assert afk == []
        assert len(hitl) == 1

    def test_content_changed_slides_is_always_hitl(self, tmp_path):
        """Google Slides are not eligible for AFK per spec."""
        entry = _drifted_entry(
            event_type="content_changed",
            mime_type="application/vnd.google-apps.presentation",
            lines_added=1,
            lines_removed=0,
        )
        afk, _ = _classify(tmp_path, _make_drift_report([entry]), afk_max_lines=100)
        assert afk == []

    def test_trashed_is_always_hitl(self, tmp_path):
        entry = _drifted_entry(event_type="trashed")
        afk, hitl = _classify(tmp_path, _make_drift_report([entry]), afk_max_lines=100)
        assert len(hitl) == 1
        assert hitl[0]["event_type"] == "trashed"

    def test_deleted_is_always_hitl(self, tmp_path):
        entry = _drifted_entry(event_type="deleted")
        _, hitl = _classify(tmp_path, _make_drift_report([entry]), afk_max_lines=100)
        assert len(hitl) == 1

    def test_new_file_is_always_hitl(self, tmp_path):
        entry = _drifted_entry(event_type="new_file")
        _, hitl = _classify(tmp_path, _make_drift_report([entry]), afk_max_lines=100)
        assert len(hitl) == 1
        assert hitl[0]["event_type"] == "new_file"

    def test_out_of_scope_is_always_hitl(self, tmp_path):
        entry = _drifted_entry(event_type="out_of_scope")
        _, hitl = _classify(tmp_path, _make_drift_report([entry]), afk_max_lines=100)
        assert len(hitl) == 1

    def test_archived_tracking_status_is_hitl(self, tmp_path):
        entry = _drifted_entry(
            event_type="content_changed",
            tracking_status="archived",
            mime_type="application/vnd.google-apps.document",
            lines_added=1,
            lines_removed=0,
        )
        _, hitl = _classify(tmp_path, _make_drift_report([entry]), afk_max_lines=100)
        assert len(hitl) == 1

    def test_no_drift_produces_empty_outputs(self, tmp_path):
        afk, hitl = _classify(tmp_path, _make_drift_report([], has_drift=False), afk_max_lines=10)
        assert afk == []
        assert hitl == []


# ---------------------------------------------------------------------------
# Bulk aggregation
# ---------------------------------------------------------------------------

class TestClassifyDriftBulkAggregation:
    def test_three_same_type_same_folder_aggregated(self, tmp_path):
        entries = [
            _drifted_entry(event_type="trashed", file_id=f"file{i}", parent_folder_id="FOLDER1")
            for i in range(3)
        ]
        _, hitl = _classify(tmp_path, _make_drift_report(entries))
        # Should aggregate into one HITL issue
        assert len(hitl) == 1
        assert hitl[0].get("is_bulk_aggregation") is True
        assert hitl[0].get("bulk_count") == 3
        assert len(hitl[0]["bulk_file_ids"]) == 3

    def test_two_same_type_same_folder_not_aggregated(self, tmp_path):
        entries = [
            _drifted_entry(event_type="trashed", file_id=f"file{i}", parent_folder_id="FOLDER1")
            for i in range(2)
        ]
        _, hitl = _classify(tmp_path, _make_drift_report(entries))
        # Below threshold — kept as individual entries
        assert len(hitl) == 2
        for h in hitl:
            assert not h.get("is_bulk_aggregation")

    def test_three_same_type_different_folders_not_aggregated(self, tmp_path):
        entries = [
            _drifted_entry(event_type="trashed", file_id=f"file{i}", parent_folder_id=f"FOLDER{i}")
            for i in range(3)
        ]
        _, hitl = _classify(tmp_path, _make_drift_report(entries))
        # Different folders — 3 separate issues
        assert len(hitl) == 3
        for h in hitl:
            assert not h.get("is_bulk_aggregation")

    def test_deleted_events_also_eligible_for_aggregation(self, tmp_path):
        entries = [
            _drifted_entry(event_type="deleted", file_id=f"file{i}", parent_folder_id="FOLDER1")
            for i in range(4)
        ]
        _, hitl = _classify(tmp_path, _make_drift_report(entries))
        assert len(hitl) == 1
        assert hitl[0]["is_bulk_aggregation"] is True
        assert hitl[0]["bulk_count"] == 4

    def test_content_changed_not_eligible_for_aggregation(self, tmp_path):
        entries = [
            _drifted_entry(event_type="content_changed", file_id=f"file{i}", parent_folder_id="FOLDER1")
            for i in range(5)
        ]
        _, hitl = _classify(tmp_path, _make_drift_report(entries))
        # content_changed not aggregated — 5 individual entries
        assert len(hitl) == 5
        for h in hitl:
            assert not h.get("is_bulk_aggregation")
