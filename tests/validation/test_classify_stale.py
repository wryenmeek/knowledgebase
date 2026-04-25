"""Tests for scripts.validation.classify_stale."""
from __future__ import annotations

import json

import pytest

from scripts.validation.classify_stale import (
    DEFAULT_AFK_THRESHOLD_DAYS,
    DEFAULT_MISSING_DATA_DAYS,
    classify_stale_pages,
)


def _write_report(path, files):
    path.write_text(json.dumps({"files": files}))


def test_empty_files_list(tmp_path):
    report = tmp_path / "report.json"
    output = tmp_path / "routing.json"
    _write_report(report, [])

    summary = classify_stale_pages(str(report), str(output))

    assert summary == {"total": 0, "afk_candidate": 0, "hitl": 0}
    result = json.loads(output.read_text())
    assert result == {"stale_pages": []}


def test_afk_candidate_and_hitl_classification(tmp_path):
    report = tmp_path / "report.json"
    output = tmp_path / "routing.json"
    _write_report(
        report,
        [
            {"path": "wiki/young.md", "days_stale": 100, "last_updated": "2024-01-01"},
            {"path": "wiki/old.md", "days_stale": 200, "last_updated": "2023-06-01"},
        ],
    )

    summary = classify_stale_pages(str(report), str(output))

    assert summary == {"total": 2, "afk_candidate": 1, "hitl": 1}
    pages = json.loads(output.read_text())["stale_pages"]
    assert pages[0]["classification"] == "afk-candidate"
    assert pages[0]["days_stale"] == 100
    assert pages[1]["classification"] == "hitl"
    assert pages[1]["days_stale"] == 200


def test_missing_days_stale_defaults_to_hitl(tmp_path):
    report = tmp_path / "report.json"
    output = tmp_path / "routing.json"
    _write_report(report, [{"path": "wiki/no-days.md"}])

    summary = classify_stale_pages(str(report), str(output))

    assert summary == {"total": 1, "afk_candidate": 0, "hitl": 1}
    pages = json.loads(output.read_text())["stale_pages"]
    assert pages[0]["days_stale"] == DEFAULT_MISSING_DATA_DAYS
    assert pages[0]["classification"] == "hitl"


def test_custom_threshold(tmp_path):
    report = tmp_path / "report.json"
    output = tmp_path / "routing.json"
    _write_report(
        report,
        [
            {"path": "wiki/a.md", "days_stale": 85},
            {"path": "wiki/b.md", "days_stale": 95},
        ],
    )

    summary = classify_stale_pages(str(report), str(output), afk_threshold_days=90)

    assert summary == {"total": 2, "afk_candidate": 1, "hitl": 1}
    pages = json.loads(output.read_text())["stale_pages"]
    assert pages[0]["classification"] == "afk-candidate"
    assert pages[1]["classification"] == "hitl"


def test_missing_input_file_raises(tmp_path):
    output = tmp_path / "routing.json"
    with pytest.raises(FileNotFoundError):
        classify_stale_pages(str(tmp_path / "nonexistent.json"), str(output))


def test_default_threshold_constant():
    assert DEFAULT_AFK_THRESHOLD_DAYS == 180


def test_default_missing_data_constant():
    assert DEFAULT_MISSING_DATA_DAYS == 999
