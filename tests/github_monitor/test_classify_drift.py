"""Unit tests for classify_drift.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts._optional_surface_common import STATUS_PASS, STATUS_FAIL
from scripts.github_monitor.classify_drift import (
    SURFACE,
    MODE,
    classify_drift,
)


def _make_drift_report(drifted: list[dict] | None = None) -> dict:
    return {
        "version": 1,
        "generated_at": "2025-01-01T00:00:00Z",
        "registry": "raw/github-sources/test.source-registry.json",
        "has_drift": bool(drifted),
        "drifted": drifted or [],
        "up_to_date": [],
        "uninitialized": [],
        "errors": [],
    }


def _drifted_entry(path: str = "docs/guide.md", idx: int = 0) -> dict:
    return {
        "owner": "test-org",
        "repo": "test-repo",
        "path": path,
        "current_commit_sha": f"{'b' * 39}{idx}",
        "current_blob_sha": f"{'d' * 39}{idx}",
        "last_applied_commit_sha": f"{'a' * 39}{idx}",
        "last_applied_blob_sha": f"{'c' * 39}{idx}",
        "compare_url": None,
    }


class TestClassifyDriftEmptyReport:
    """Empty drift report → no AFK, no HITL."""

    def test_empty_drifted(self, tmp_path: Path) -> None:
        report_path = tmp_path / "drift-report.json"
        report_path.write_text(json.dumps(_make_drift_report([])))

        result = classify_drift(report_path, tmp_path)

        assert result.status == STATUS_PASS
        assert result.summary["has_afk"] is False
        assert result.summary["has_hitl"] is False
        assert result.summary["afk_count"] == 0
        assert result.summary["hitl_count"] == 0

        afk = json.loads((tmp_path / "afk-entries.json").read_text())
        hitl = json.loads((tmp_path / "hitl-entries.json").read_text())
        assert afk["entries"] == []
        assert hitl["entries"] == []


class TestClassifyDriftAllHITL:
    """Drifted entries → all classify as HITL (deny-by-default)."""

    def test_three_entries_all_hitl(self, tmp_path: Path) -> None:
        entries = [_drifted_entry(f"docs/page{i}.md", i) for i in range(3)]
        report_path = tmp_path / "drift-report.json"
        report_path.write_text(json.dumps(_make_drift_report(entries)))

        result = classify_drift(report_path, tmp_path)

        assert result.status == STATUS_PASS
        assert result.summary["has_afk"] is False
        assert result.summary["has_hitl"] is True
        assert result.summary["afk_count"] == 0
        assert result.summary["hitl_count"] == 3

        afk = json.loads((tmp_path / "afk-entries.json").read_text())
        hitl = json.loads((tmp_path / "hitl-entries.json").read_text())
        assert afk["entries"] == []
        assert len(hitl["entries"]) == 3


class TestClassifyDriftMissingFile:
    """Missing drift report file → error result."""

    def test_missing_file(self, tmp_path: Path) -> None:
        report_path = tmp_path / "nonexistent.json"

        result = classify_drift(report_path, tmp_path)

        assert result.status == STATUS_FAIL
        assert result.reason_code == "invalid_input"
        assert "Cannot read" in result.message


class TestClassifyDriftMalformedJSON:
    """Malformed JSON → error result."""

    def test_malformed_json(self, tmp_path: Path) -> None:
        report_path = tmp_path / "drift-report.json"
        report_path.write_text("not valid json {{{")

        result = classify_drift(report_path, tmp_path)

        assert result.status == STATUS_FAIL
        assert result.reason_code == "invalid_input"
        assert "Malformed" in result.message


class TestClassifyDriftOutputDir:
    """Output files are written to the specified output directory."""

    def test_output_dir_created(self, tmp_path: Path) -> None:
        report_path = tmp_path / "drift-report.json"
        report_path.write_text(json.dumps(_make_drift_report([])))

        out = tmp_path / "sub" / "dir"
        result = classify_drift(report_path, out)

        assert result.status == STATUS_PASS
        assert (out / "afk-entries.json").exists()
        assert (out / "hitl-entries.json").exists()
