"""Tests for deterministic document freshness analysis."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from scripts.validation.github_actions_annotations import (
    escape_message,
    escape_property,
    load_report_entries,
)
from tests.kb.harnesses import REPO_ROOT, load_module


FRESHNESS_SCRIPT_PATH = REPO_ROOT / "scripts" / "validation" / "check_doc_freshness.py"


@pytest.fixture
def freshness_module():
    return load_module("check_doc_freshness_pytest", FRESHNESS_SCRIPT_PATH)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "wiki").mkdir()
    (tmp_path / "AGENTS.md").write_text("# Test repo\n", encoding="utf-8")
    return tmp_path


def build_page(title: str, updated_at: str) -> str:
    return "\n".join(
        [
            "---",
            "type: process",
            f'title: "{title}"',
            "status: active",
            "sources: []",
            "open_questions: []",
            "confidence: 3",
            "sensitivity: internal",
            f'updated_at: "{updated_at}"',
            "tags:",
            "  - test",
            "---",
            "",
            f"# {title}",
            "",
        ]
    )


def test_run_freshness_emits_stable_json_shape(freshness_module, workspace: Path) -> None:
    (workspace / "wiki/reference.md").write_text(
        build_page("Reference", "2024-01-01T00:00:00Z"), encoding="utf-8"
    )

    report = freshness_module.run_freshness(
        repo_root=workspace,
        scope="wiki",
        as_of="2024-01-31",
        max_age_days=45,
    )

    assert report.to_dict() == {
        "status": "pass",
        "reason_code": "ok",
        "message": "all scanned documents satisfy freshness requirements",
        "scope": "wiki",
        "as_of": "2024-01-31",
        "max_age_days": 45,
        "near_expiry_days": None,
        "files": [
            {
                "age_days": 30,
                "message": "document freshness within threshold",
                "path": "wiki/reference.md",
                "reason_code": "ok",
                "status": "pass",
                "updated_at": "2024-01-01",
            }
        ],
    }


def test_near_expiry_flags_exact_boundary_and_one_day_before_passes(
    freshness_module, workspace: Path
) -> None:
    (workspace / "wiki/exact.md").write_text(
        build_page("Exact", "2024-01-01T00:00:00Z"), encoding="utf-8"
    )
    (workspace / "wiki/before.md").write_text(
        build_page("Before", "2024-01-02T00:00:00Z"), encoding="utf-8"
    )

    report = freshness_module.run_freshness(
        repo_root=workspace,
        scope="wiki",
        as_of="2024-01-31",
        max_age_days=40,
        near_expiry_days=10,
    )

    assert report.status == "fail"
    assert report.reason_code == "near_expiry"
    assert [(item.path, item.reason_code, item.status) for item in report.files] == [
        ("wiki/before.md", "ok", "pass"),
        ("wiki/exact.md", "near_expiry", "fail"),
    ]


def test_max_age_boundary_remains_stale_when_near_expiry_is_enabled(
    freshness_module, workspace: Path
) -> None:
    (workspace / "wiki/exact.md").write_text(
        build_page("Exact", "2024-01-01T00:00:00Z"), encoding="utf-8"
    )

    report = freshness_module.run_freshness(
        repo_root=workspace,
        scope="wiki",
        as_of="2024-01-31",
        max_age_days=30,
        near_expiry_days=10,
    )

    assert report.files[0].reason_code == "stale_document"
    assert report.files[0].age_days == 30
    assert "30d >= 30d" in report.files[0].message


@pytest.mark.parametrize("near_expiry_days", [-1, 0, 40, 41])
def test_near_expiry_rejects_non_positive_and_oversized_windows(
    freshness_module, workspace: Path, near_expiry_days: int
) -> None:
    (workspace / "wiki/reference.md").write_text(
        build_page("Reference", "2024-01-01T00:00:00Z"), encoding="utf-8"
    )
    report = freshness_module.run_freshness(
        repo_root=workspace,
        scope="wiki",
        as_of="2024-01-31",
        max_age_days=40,
        near_expiry_days=near_expiry_days,
    )

    assert report.status == "fail"
    assert report.reason_code == "invalid_input"
    assert "near-expiry-days" in report.message
    assert report.files == ()


def test_already_stale_document_keeps_stale_reason(freshness_module, workspace: Path) -> None:
    (workspace / "wiki/stale.md").write_text(
        build_page("Stale", "2023-01-01T00:00:00Z"), encoding="utf-8"
    )

    report = freshness_module.run_freshness(
        repo_root=workspace,
        scope="wiki",
        as_of="2024-01-31",
        max_age_days=40,
        near_expiry_days=10,
    )

    assert report.reason_code == "stale_document"
    assert report.files[0].reason_code == "stale_document"


def test_cli_near_expiry_and_failures_only(freshness_module, workspace: Path) -> None:
    (workspace / "wiki/near.md").write_text(
        build_page("Near", "2024-01-01T00:00:00Z"), encoding="utf-8"
    )
    output = StringIO()

    exit_code = freshness_module.run_cli(
        argv=[
            "--scope",
            "wiki",
            "--as-of",
            "2024-01-31",
            "--max-age-days",
            "40",
            "--near-expiry-days",
            "10",
            "--failures-only",
        ],
        output_stream=output,
        repo_root=workspace,
    )

    assert exit_code == 1
    payload = json.loads(output.getvalue())
    assert [entry["reason_code"] for entry in payload["files"]] == ["near_expiry"]


def test_failures_only_preserves_stale_and_near_expiry_results(
    freshness_module, workspace: Path
) -> None:
    (workspace / "wiki/pass.md").write_text(
        build_page("Pass", "2024-01-25T00:00:00Z"), encoding="utf-8"
    )
    (workspace / "wiki/near.md").write_text(
        build_page("Near", "2024-01-10T00:00:00Z"), encoding="utf-8"
    )
    (workspace / "wiki/stale.md").write_text(
        build_page("Stale", "2024-01-01T00:00:00Z"), encoding="utf-8"
    )
    output = StringIO()

    exit_code = freshness_module.run_cli(
        argv=[
            "--scope",
            "wiki",
            "--as-of",
            "2024-01-31",
            "--max-age-days",
            "30",
            "--near-expiry-days",
            "10",
            "--failures-only",
        ],
        output_stream=output,
        repo_root=workspace,
    )

    assert exit_code == 1
    payload = json.loads(output.getvalue())
    assert [(entry["path"], entry["reason_code"]) for entry in payload["files"]] == [
        ("wiki/near.md", "near_expiry"),
        ("wiki/stale.md", "stale_document"),
    ]


def test_cli_returns_invalid_input_for_invalid_near_expiry_window(
    freshness_module, workspace: Path
) -> None:
    output = StringIO()

    exit_code = freshness_module.run_cli(
        argv=[
            "--scope",
            "wiki",
            "--as-of",
            "2024-01-31",
            "--max-age-days",
            "40",
            "--near-expiry-days",
            "40",
        ],
        output_stream=output,
        repo_root=workspace,
    )

    assert exit_code == 1
    payload = json.loads(output.getvalue())
    assert payload["status"] == "fail"
    assert payload["reason_code"] == "invalid_input"


def test_cli_runs_from_repo_root_without_writing_workspace(workspace: Path) -> None:
    (workspace / "wiki/reference.md").write_text(
        build_page("Reference", "2024-01-01T00:00:00Z"), encoding="utf-8"
    )
    before = {
        path.relative_to(workspace).as_posix(): path.read_bytes()
        for path in workspace.rglob("*")
        if path.is_file()
    }

    completed = subprocess.run(
        [
            sys.executable,
            str(FRESHNESS_SCRIPT_PATH),
            "--scope",
            "wiki",
            "--as-of",
            "2024-01-31",
            "--max-age-days",
            "45",
            "--near-expiry-days",
            "10",
        ],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["files"][0]["path"] == "wiki/reference.md"
    assert payload["near_expiry_days"] == 10
    after = {
        path.relative_to(workspace).as_posix(): path.read_bytes()
        for path in workspace.rglob("*")
        if path.is_file()
    }
    assert before == after


def test_cli_returns_json_for_parser_level_invalid_input(workspace: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(FRESHNESS_SCRIPT_PATH),
            "--scope",
            "wiki",
            "--as-of",
            "2024-01-31",
            "--max-age-days",
            "nope",
        ],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["status"] == "fail"
    assert payload["reason_code"] == "invalid_input"
    assert payload["scope"] == "unknown"


def test_cli_fails_closed_when_requested_path_escapes_repo_root(
    freshness_module, workspace: Path
) -> None:
    output = StringIO()

    exit_code = freshness_module.run_cli(
        argv=[
            "--scope",
            "wiki",
            "--path",
            "../outside.md",
            "--as-of",
            "2024-01-31",
            "--max-age-days",
            "45",
        ],
        output_stream=output,
        repo_root=workspace,
    )

    assert exit_code == 1
    payload = json.loads(output.getvalue())
    assert payload["status"] == "fail"
    assert payload["reason_code"] == "invalid_input"
    assert "escapes repository root" in payload["message"]


def test_cli_fails_closed_on_missing_updated_at_metadata(
    freshness_module, workspace: Path
) -> None:
    (workspace / "wiki/reference.md").write_text("# Reference\n", encoding="utf-8")
    output = StringIO()

    exit_code = freshness_module.run_cli(
        argv=["--scope", "wiki", "--as-of", "2024-01-31", "--max-age-days", "45"],
        output_stream=output,
        repo_root=workspace,
    )

    assert exit_code == 1
    payload = json.loads(output.getvalue())
    assert payload["status"] == "fail"
    assert payload["reason_code"] == "missing_updated_at"
    assert payload["files"][0]["path"] == "wiki/reference.md"


def test_workflow_configures_near_expiry_as_advisory_signal() -> None:
    workflow = (REPO_ROOT / ".github/workflows/wiki-freshness.yml").read_text(
        encoding="utf-8"
    )

    parsed_workflow = yaml.safe_load(workflow)
    near_expiry_step = next(
        step
        for step in parsed_workflow["jobs"]["wiki-freshness"]["steps"]
        if step["name"] == "Run wiki near-expiry check"
    )

    assert '--max-age-days "$FRESHNESS_MAX_AGE_DAYS"' in near_expiry_step["run"]
    assert '--near-expiry-days "$FRESHNESS_NEAR_EXPIRY_DAYS"' in near_expiry_step["run"]
    assert "wiki-near-expiry.json" in near_expiry_step["run"]
    assert near_expiry_step["if"] == "always()"
    assert near_expiry_step["continue-on-error"] is True

    assert workflow.count(
        "from scripts.validation.github_actions_annotations import ("
    ) == 3
    assert workflow.count("load_report_entries(") == 3


def test_github_actions_annotation_escaping_separates_properties_and_messages() -> None:
    value = "wiki/percent%,colon:comma,\nline"

    assert escape_property(value) == "wiki/percent%25%2Ccolon%3Acomma%2C%0Aline"
    assert escape_message(value) == "wiki/percent%25,colon:comma,%0Aline"


def test_github_actions_report_loader_rejects_malformed_reports(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="files array"):
        load_report_entries(report_path, "files")


def test_github_actions_report_loader_filters_non_mapping_entries(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps({"files": [{"path": "wiki/page.md"}, "invalid", None]}),
        encoding="utf-8",
    )

    assert load_report_entries(report_path, "files") == ({"path": "wiki/page.md"},)
