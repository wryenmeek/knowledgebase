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
    _is_afk_eligible,
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


def _drifted_entry(
    path: str = "docs/guide.md",
    idx: int = 0,
    lines_added: int | None = None,
    lines_removed: int | None = None,
    is_binary: bool | None = None,
    file_size_bytes: int | None = None,
) -> dict:
    return {
        "owner": "test-org",
        "repo": "test-repo",
        "path": path,
        "current_commit_sha": f"{'b' * 39}{idx}",
        "current_blob_sha": f"{'d' * 39}{idx}",
        "last_applied_commit_sha": f"{'a' * 39}{idx}",
        "last_applied_blob_sha": f"{'c' * 39}{idx}",
        "compare_url": None,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "is_binary": is_binary,
        "file_size_bytes": file_size_bytes,
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


class TestAfkThresholdZero:
    """Default threshold 0 → all entries classify as HITL."""

    def test_zero_threshold_all_hitl(self, tmp_path: Path) -> None:
        entries = [_drifted_entry("docs/a.md", 0, lines_added=1, lines_removed=0)]
        report_path = tmp_path / "drift-report.json"
        report_path.write_text(json.dumps(_make_drift_report(entries)))

        result = classify_drift(report_path, tmp_path, afk_max_lines=0)

        assert result.summary["afk_count"] == 0
        assert result.summary["hitl_count"] == 1


class TestAfkThresholdPositive:
    """Positive threshold → small changes classify as AFK."""

    def test_small_change_afk(self, tmp_path: Path) -> None:
        entries = [_drifted_entry("docs/a.md", 0, lines_added=2, lines_removed=1, is_binary=False)]
        report_path = tmp_path / "drift-report.json"
        report_path.write_text(json.dumps(_make_drift_report(entries)))

        result = classify_drift(report_path, tmp_path, afk_max_lines=5)

        assert result.summary["afk_count"] == 1
        assert result.summary["hitl_count"] == 0

    def test_large_change_hitl(self, tmp_path: Path) -> None:
        entries = [_drifted_entry("docs/a.md", 0, lines_added=50, lines_removed=20, is_binary=False)]
        report_path = tmp_path / "drift-report.json"
        report_path.write_text(json.dumps(_make_drift_report(entries)))

        result = classify_drift(report_path, tmp_path, afk_max_lines=5)

        assert result.summary["afk_count"] == 0
        assert result.summary["hitl_count"] == 1

    def test_binary_always_hitl(self, tmp_path: Path) -> None:
        entries = [_drifted_entry("img.png", 0, lines_added=0, lines_removed=0, is_binary=True)]
        report_path = tmp_path / "drift-report.json"
        report_path.write_text(json.dumps(_make_drift_report(entries)))

        result = classify_drift(report_path, tmp_path, afk_max_lines=100)

        assert result.summary["afk_count"] == 0
        assert result.summary["hitl_count"] == 1

    def test_null_metrics_hitl(self, tmp_path: Path) -> None:
        entries = [_drifted_entry("docs/a.md", 0, lines_added=None, lines_removed=None)]
        report_path = tmp_path / "drift-report.json"
        report_path.write_text(json.dumps(_make_drift_report(entries)))

        result = classify_drift(report_path, tmp_path, afk_max_lines=100)

        assert result.summary["afk_count"] == 0
        assert result.summary["hitl_count"] == 1

    def test_partial_null_metrics_hitl(self, tmp_path: Path) -> None:
        entries = [_drifted_entry("docs/a.md", 0, lines_added=2, lines_removed=None)]
        report_path = tmp_path / "drift-report.json"
        report_path.write_text(json.dumps(_make_drift_report(entries)))

        result = classify_drift(report_path, tmp_path, afk_max_lines=100)

        assert result.summary["afk_count"] == 0
        assert result.summary["hitl_count"] == 1

    def test_mixed_entries(self, tmp_path: Path) -> None:
        entries = [
            _drifted_entry("docs/small.md", 0, lines_added=1, lines_removed=0, is_binary=False),
            _drifted_entry("docs/big.md", 1, lines_added=100, lines_removed=50, is_binary=False),
            _drifted_entry("img.png", 2, is_binary=True),
        ]
        report_path = tmp_path / "drift-report.json"
        report_path.write_text(json.dumps(_make_drift_report(entries)))

        result = classify_drift(report_path, tmp_path, afk_max_lines=5)

        assert result.summary["afk_count"] == 1
        assert result.summary["hitl_count"] == 2


class TestIsAfkEligible:
    """Unit tests for the _is_afk_eligible helper."""

    def test_zero_threshold_never_eligible(self) -> None:
        entry = {"lines_added": 0, "lines_removed": 0, "is_binary": False}
        assert _is_afk_eligible(entry, 0) is False

    def test_negative_threshold_never_eligible(self) -> None:
        entry = {"lines_added": 0, "lines_removed": 0, "is_binary": False}
        assert _is_afk_eligible(entry, -1) is False

    def test_exact_threshold_eligible(self) -> None:
        entry = {"lines_added": 3, "lines_removed": 2, "is_binary": False}
        assert _is_afk_eligible(entry, 5) is True

    def test_over_threshold_not_eligible(self) -> None:
        entry = {"lines_added": 3, "lines_removed": 3, "is_binary": False}
        assert _is_afk_eligible(entry, 5) is False


class TestCheckDriftMetrics:
    """Test _compute_line_metrics and _is_binary from check_drift.py."""

    def test_is_binary_detects_null_bytes(self) -> None:
        from scripts.github_monitor.check_drift import _is_binary
        assert _is_binary(b"hello\x00world") is True
        assert _is_binary(b"hello world") is False
        assert _is_binary(b"") is False

    def test_compute_line_metrics_text_diff(self, tmp_path: Path) -> None:
        from scripts.github_monitor.check_drift import _compute_line_metrics

        commit_sha = "a" * 40
        # Create prior asset
        asset_dir = tmp_path / "raw" / "assets" / "org" / "repo" / commit_sha / "docs"
        asset_dir.mkdir(parents=True)
        (asset_dir / "file.md").write_text("line1\nline2\nline3\n")

        metrics = _compute_line_metrics(
            tmp_path, "org", "repo", "docs/file.md", commit_sha,
            b"line1\nline2\nline3\nline4\n",
        )

        assert metrics["lines_added"] == 1
        assert metrics["lines_removed"] == 0
        assert metrics["is_binary"] is False
        assert metrics["file_size_bytes"] == len(b"line1\nline2\nline3\nline4\n")

    def test_compute_line_metrics_missing_prior(self, tmp_path: Path) -> None:
        from scripts.github_monitor.check_drift import _compute_line_metrics

        metrics = _compute_line_metrics(
            tmp_path, "org", "repo", "docs/file.md", "b" * 40,
            b"hello\n",
        )

        assert metrics["lines_added"] is None
        assert metrics["lines_removed"] is None
        assert metrics["is_binary"] is False

    def test_compute_line_metrics_binary_current(self, tmp_path: Path) -> None:
        from scripts.github_monitor.check_drift import _compute_line_metrics

        metrics = _compute_line_metrics(
            tmp_path, "org", "repo", "img.png", None,
            b"\x89PNG\x00\x00",
        )

        assert metrics["is_binary"] is True
        assert metrics["lines_added"] is None

    def test_compute_line_metrics_none_current(self, tmp_path: Path) -> None:
        from scripts.github_monitor.check_drift import _compute_line_metrics

        metrics = _compute_line_metrics(
            tmp_path, "org", "repo", "file.md", None, None,
        )

        assert all(v is None for v in metrics.values())

    def test_compute_line_metrics_no_prior_commit_sha(self, tmp_path: Path) -> None:
        from scripts.github_monitor.check_drift import _compute_line_metrics

        metrics = _compute_line_metrics(
            tmp_path, "org", "repo", "file.md", None,
            b"some content\n",
        )

        assert metrics["lines_added"] is None
        assert metrics["is_binary"] is False
        assert metrics["file_size_bytes"] is not None
