"""Tests for scripts.maintenance.audit_pr_body_vs_diff."""

from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess

import scripts.maintenance.audit_pr_body_vs_diff as audit
from scripts.maintenance.audit_pr_body_vs_diff import run_pr_body_vs_diff_audit


def _write_fixture(repo_root: Path, payload: dict[str, object]) -> str:
    fixture_path = repo_root / "pr-fixture.json"
    fixture_path.write_text(json.dumps(payload), encoding="utf-8")
    return fixture_path.name


def _pr_payload(*, body: str, files: list[str], additions: int = 1, deletions: int = 1) -> dict[str, object]:
    return {
        "pull_requests": [
            {
                "number": 327,
                "title": "Fixture PR",
                "url": "https://github.com/wryenmeek/knowledgebase/pull/327",
                "body": body,
                "files": files,
                "additions": additions,
                "deletions": deletions,
                "changedFiles": len(files),
            }
        ]
    }


def _run_fixture(tmp_path: Path, payload: dict[str, object]):
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    fixture_name = _write_fixture(tmp_path, payload)
    return run_pr_body_vs_diff_audit(
        repo_root=tmp_path,
        mode="audit",
        pr_number=327,
        repo=None,
        no_comment=False,
        issues_json_path=fixture_name,
    )


def test_audit_passes_when_body_claims_match_diff_exactly(tmp_path) -> None:
    result = _run_fixture(
        tmp_path,
        _pr_payload(
            body="Changed `scripts/foo.py` and `docs/bar.md`.",
            files=["docs/bar.md", "scripts/foo.py"],
        ),
    )

    assert result.status == "pass"
    assert result.reason_code == "ok"
    assert result.summary["total_claims"] == 2
    assert result.summary["unmet_claims"] == []
    assert result.summary["extra_diff_files"] == []
    assert result.summary["comments_posted_count"] == 0


def test_audit_flags_type_c_full_hallucination_when_all_claims_are_unmet(tmp_path) -> None:
    result = _run_fixture(
        tmp_path,
        _pr_payload(
            body="Claims `scripts/foo.py` and `scripts/bar.py` were changed.",
            files=["scripts/baz.py"],
        ),
    )

    assert result.status == "fail"
    assert result.reason_code == "body_diff_drift_detected"
    assert result.summary["unmet_claims"] == ["scripts/bar.py", "scripts/foo.py"]
    assert result.summary["extra_diff_files"] == ["scripts/baz.py"]
    assert result.summary["is_type_c_full"] is True
    assert result.summary["is_type_b_drift"] is False
    assert result.summary["would_post_comment_count"] == 1


def test_audit_flags_type_b_drift_when_claims_and_diff_partially_overlap(tmp_path) -> None:
    result = _run_fixture(
        tmp_path,
        _pr_payload(
            body="Implemented `scripts/foo.py` and `scripts/bar.py`.",
            files=["scripts/foo.py", "scripts/baz.py"],
        ),
    )

    assert result.status == "fail"
    assert result.reason_code == "body_diff_drift_detected"
    assert result.summary["matched_claims"] == ["scripts/foo.py"]
    assert result.summary["unmet_claims"] == ["scripts/bar.py"]
    assert result.summary["extra_diff_files"] == ["scripts/baz.py"]
    assert result.summary["is_type_b_drift"] is True
    assert result.summary["is_type_c_full"] is False


def test_audit_flags_zero_zero_zero_type_c_as_severity_one_warning(tmp_path) -> None:
    result = _run_fixture(
        tmp_path,
        _pr_payload(
            body="The PR says `scripts/foo.py` changed.",
            files=[],
            additions=0,
            deletions=0,
        ),
    )

    assert result.status == "fail"
    assert result.summary["is_type_c"] is True
    assert result.summary["diff_signature"] == "0 added, 0 deleted, 0 files"
    severity_one_items = [item for item in result.items if item.get("severity") == 1]
    assert len(severity_one_items) == 1
    assert severity_one_items[0]["reason_code"] == "severity_1_empty_diff_type_c"
    assert "0 added, 0 deleted, 0 files" in severity_one_items[0]["message"]
    assert result.summary["would_post_comment_count"] == 2


def test_audit_passes_with_note_when_body_contains_no_file_claims(tmp_path) -> None:
    result = _run_fixture(
        tmp_path,
        _pr_payload(
            body="This PR improves the automation narrative without naming files.",
            files=["scripts/foo.py"],
        ),
    )

    assert result.status == "pass"
    assert result.reason_code == "ok"
    assert result.message == "PR body contains no file-mention claims to audit"
    assert result.summary["total_claims"] == 0
    assert result.summary["extra_diff_files"] == ["scripts/foo.py"]


def test_cli_exits_zero_when_gh_cli_fails_but_marks_surface_failed(tmp_path, monkeypatch) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=1, stdout="", stderr="gh exploded\n")

    monkeypatch.setattr(audit.subprocess, "run", fake_run)
    output = io.StringIO()

    exit_code = audit.run_cli(
        argv=["--repo-root", str(tmp_path), "--pr", "327", "--no-comment"],
        output_stream=output,
    )

    payload = json.loads(output.getvalue())
    assert exit_code == 0
    assert payload["status"] == "fail"
    assert payload["reason_code"] == "gh_cli_failed"
    assert "gh command failed" in payload["message"]


def test_audit_resolves_unique_basename_claim_against_diff_path(tmp_path) -> None:
    result = _run_fixture(
        tmp_path,
        _pr_payload(
            body="Updated `test_approval_migration_ratchet.py`.",
            files=["tests/kb/test_approval_migration_ratchet.py"],
        ),
    )

    assert result.status == "pass"
    assert result.summary["matched_claims"] == ["test_approval_migration_ratchet.py"]
    assert result.summary["resolved_claim_matches"] == {
        "test_approval_migration_ratchet.py": "tests/kb/test_approval_migration_ratchet.py"
    }
    assert result.summary["unmet_claims"] == []
    assert result.summary["extra_diff_files"] == []


def test_audit_flags_zero_zero_zero_type_c_even_without_body_claims(tmp_path) -> None:
    result = _run_fixture(
        tmp_path,
        _pr_payload(
            body="Merged housekeeping with no explicit file list.",
            files=[],
            additions=0,
            deletions=0,
        ),
    )

    assert result.status == "fail"
    assert result.summary["total_claims"] == 0
    assert result.summary["is_type_c"] is True
    assert result.summary["would_post_comment_count"] == 1
    assert result.items[0]["reason_code"] == "severity_1_empty_diff_type_c"


def test_fixture_mode_avoids_gh_calls_and_skips_comments(tmp_path, monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("fixture mode must not invoke gh")

    monkeypatch.setattr(audit.subprocess, "run", fail_if_called)
    result = _run_fixture(
        tmp_path,
        _pr_payload(
            body="Claims `scripts/foo.py` changed.",
            files=["scripts/bar.py"],
        ),
    )

    assert result.status == "fail"
    assert result.summary["source"] == "issues_json"
    assert result.summary["comments_skipped"] is True
    assert result.summary["comments_posted_count"] == 0


def test_cli_exits_zero_when_comment_post_fails_but_marks_comment_failure(tmp_path, monkeypatch) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")

    def fake_run(command, **kwargs):
        if command[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=json.dumps(
                    {
                        "number": 327,
                        "title": "Fixture PR",
                        "url": "https://github.com/wryenmeek/knowledgebase/pull/327",
                        "body": "Claims `scripts/foo.py` changed.",
                        "additions": 1,
                        "deletions": 0,
                        "changedFiles": 1,
                    }
                ),
                stderr="",
            )
        if command[:3] == ["gh", "pr", "diff"]:
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="scripts/bar.py\n", stderr="")
        if command[:3] == ["gh", "issue", "comment"]:
            return subprocess.CompletedProcess(args=command, returncode=1, stdout="", stderr="comment denied\n")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(audit.subprocess, "run", fake_run)
    output = io.StringIO()

    exit_code = audit.run_cli(argv=["--repo-root", str(tmp_path), "--pr", "327"], output_stream=output)

    payload = json.loads(output.getvalue())
    assert exit_code == 0
    assert payload["status"] == "fail"
    assert payload["summary"]["comment_errors"] == ["gh command failed: comment denied"]
    assert any(item["reason_code"] == "comment_post_failed" for item in payload["items"])


def test_audit_preserves_dot_prefixed_path_claims(tmp_path) -> None:
    result = _run_fixture(
        tmp_path,
        _pr_payload(
            body="Changed `.github/workflows/post-merge-body-audit.yml` and `.fleet/2026_06_20/issue_tasks.json`.",
            files=[
                ".github/workflows/post-merge-body-audit.yml",
                ".fleet/2026_06_20/issue_tasks.json",
            ],
        ),
    )

    assert result.status == "pass"
    assert result.summary["claims"] == [
        ".fleet/2026_06_20/issue_tasks.json",
        ".github/workflows/post-merge-body-audit.yml",
    ]
    assert result.summary["unmet_claims"] == []


def test_audit_extracts_common_repo_config_path_extensions(tmp_path) -> None:
    result = _run_fixture(
        tmp_path,
        _pr_payload(
            body="Updated `pyproject.toml` and `requirements-pages.txt`.",
            files=["pyproject.toml", "requirements-pages.txt"],
        ),
    )

    assert result.status == "pass"
    assert result.summary["claims"] == ["pyproject.toml", "requirements-pages.txt"]
    assert result.summary["unmet_claims"] == []


def test_issues_json_fixture_path_must_be_repo_relative_json_file(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    repo_fixture = tmp_path / "fixture.json"
    repo_fixture.write_text("{}", encoding="utf-8")
    (tmp_path / "fixture.txt").write_text("{}", encoding="utf-8")
    outside_fixture = tmp_path.parent / f"outside-{tmp_path.name}.json"
    outside_fixture.write_text("{}", encoding="utf-8")

    invalid_fixture_paths = (
        (str(repo_fixture), "--issues-json must be repo-relative"),
        (f"../{outside_fixture.name}", "--issues-json escapes repository root"),
        ("fixture.txt", "--issues-json must reference an existing .json file"),
        ("missing.json", "--issues-json must reference an existing .json file"),
    )

    for invalid_path, expected_message in invalid_fixture_paths:
        result = run_pr_body_vs_diff_audit(
            repo_root=tmp_path,
            mode="audit",
            pr_number=327,
            issues_json_path=invalid_path,
        )
        assert result.status == "fail"
        assert result.reason_code == "invalid_input"
        assert expected_message in result.message
