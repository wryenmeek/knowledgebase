"""Tests for scripts.validation.check_issue_closure_evidence."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest
import scripts.validation.check_issue_closure_evidence as closure_evidence
from scripts.validation.check_issue_closure_evidence import (
    DEFAULT_TARGET_LABELS,
    evaluate_closure_evidence_comment,
    run_closure_evidence_report,
)

GOOD_EVIDENCE_COMMENT = """### Closure evidence
- Implementation reference: https://github.com/wryenmeek/knowledgebase/pull/151
- Key files/surfaces changed:
  - scripts/validation/check_issue_closure_evidence.py
  - docs/mvp-runbook.md
- Validation commands:
  - `python3 -m pytest tests/validation/test_check_issue_closure_evidence.py -q`
- Pass/fail summary: PASS (all targeted tests passed)
"""


def _issue(
    *,
    number: int,
    labels: tuple[str, ...],
    closed_at: str,
    comments: tuple[str, ...],
) -> dict[str, object]:
    return {
        "number": number,
        "title": f"Issue {number}",
        "url": f"https://github.com/wryenmeek/knowledgebase/issues/{number}",
        "closedAt": closed_at,
        "labels": [{"name": label} for label in labels],
        "comments": [{"body": body} for body in comments],
    }


def test_evaluate_closure_evidence_comment_passes_with_required_sections() -> None:
    result = evaluate_closure_evidence_comment(GOOD_EVIDENCE_COMMENT)
    assert result["is_compliant"] is True
    assert result["missing_fields"] == ()


def test_evaluate_closure_evidence_comment_fails_when_validation_commands_missing() -> None:
    comment = GOOD_EVIDENCE_COMMENT.replace(
        "- Validation commands:\n  - `python3 -m pytest tests/validation/test_check_issue_closure_evidence.py -q`\n",
        "- Validation commands:\n",
    )
    result = evaluate_closure_evidence_comment(comment)
    assert result["is_compliant"] is False
    assert "validation_commands" in result["missing_fields"]


def test_evaluate_closure_evidence_comment_requires_template_heading() -> None:
    comment_without_heading = GOOD_EVIDENCE_COMMENT.replace("### Closure evidence\n", "")
    result = evaluate_closure_evidence_comment(comment_without_heading)
    assert result["is_compliant"] is False
    assert "closure_evidence_heading" in result["missing_fields"]


def test_evaluate_closure_evidence_comment_rejects_non_command_backticks() -> None:
    comment = GOOD_EVIDENCE_COMMENT.replace(
        "`python3 -m pytest tests/validation/test_check_issue_closure_evidence.py -q`",
        "`this is not a command`",
    )
    result = evaluate_closure_evidence_comment(comment)
    assert result["is_compliant"] is False
    assert "validation_commands" in result["missing_fields"]


@pytest.mark.parametrize(
    "prose_line",
    (
        "ran tests locally",
        "`ran tests locally`",
        "verified everything manually",
        "`verified everything manually`",
    ),
)
def test_evaluate_closure_evidence_comment_rejects_narrative_validation_prose(
    prose_line: str,
) -> None:
    comment = GOOD_EVIDENCE_COMMENT.replace(
        "`python3 -m pytest tests/validation/test_check_issue_closure_evidence.py -q`",
        prose_line,
    )
    result = evaluate_closure_evidence_comment(comment)
    assert result["is_compliant"] is False
    assert "validation_commands" in result["missing_fields"]


@pytest.mark.parametrize(
    "validation_command",
    (
        "ruff check scripts/validation",
        "mypy scripts/validation",
        "go test ./...",
        "cargo test --workspace",
    ),
)
def test_evaluate_closure_evidence_comment_accepts_non_whitelisted_commands(
    validation_command: str,
) -> None:
    comment = GOOD_EVIDENCE_COMMENT.replace(
        "`python3 -m pytest tests/validation/test_check_issue_closure_evidence.py -q`",
        f"`{validation_command}`",
    )
    result = evaluate_closure_evidence_comment(comment)
    assert result["is_compliant"] is True
    assert result["missing_fields"] == ()


@pytest.mark.parametrize(
    "validation_command",
    (
        "go test",
        "cargo check",
        "npm test",
        "bun run lint",
        "make build",
    ),
)
def test_evaluate_closure_evidence_comment_accepts_allowlisted_short_commands(
    validation_command: str,
) -> None:
    comment = GOOD_EVIDENCE_COMMENT.replace(
        "`python3 -m pytest tests/validation/test_check_issue_closure_evidence.py -q`",
        f"`{validation_command}`",
    )
    result = evaluate_closure_evidence_comment(comment)
    assert result["is_compliant"] is True
    assert result["missing_fields"] == ()


def test_evaluate_closure_evidence_comment_requires_implementation_reference() -> None:
    comment = GOOD_EVIDENCE_COMMENT.replace(
        "https://github.com/wryenmeek/knowledgebase/pull/151",
        "implementation shipped",
    )
    result = evaluate_closure_evidence_comment(comment)
    assert result["is_compliant"] is False
    assert "implementation_reference" in result["missing_fields"]


def test_evaluate_closure_evidence_comment_requires_key_files_section_content() -> None:
    comment = GOOD_EVIDENCE_COMMENT.replace(
        "- Key files/surfaces changed:\n  - scripts/validation/check_issue_closure_evidence.py\n  - docs/mvp-runbook.md\n",
        "- Key files/surfaces changed:\n",
    )
    result = evaluate_closure_evidence_comment(comment)
    assert result["is_compliant"] is False
    assert "key_files_surfaces_changed" in result["missing_fields"]


def test_evaluate_closure_evidence_comment_requires_pass_fail_summary_keyword() -> None:
    comment = GOOD_EVIDENCE_COMMENT.replace(
        "PASS (all targeted tests passed)",
        "all targeted tests completed",
    )
    result = evaluate_closure_evidence_comment(comment)
    assert result["is_compliant"] is False
    assert "pass_fail_summary" in result["missing_fields"]


def test_run_closure_evidence_report_flags_recent_target_issue_without_evidence(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
        issues_payload=[
            _issue(
                number=151,
                labels=("security",),
                closed_at="2026-05-20T00:00:00Z",
                comments=(),
            )
        ],
    )
    assert result.status == "fail"
    assert result.reason_code == "missing_closure_evidence"
    assert result.summary["checked_issue_count"] == 1
    assert result.summary["flagged_issue_count"] == 1
    assert result.items[0]["missing_fields"] == [
        "closure_evidence_heading",
        "implementation_reference",
        "key_files_surfaces_changed",
        "validation_commands",
        "pass_fail_summary",
    ]


def test_run_closure_evidence_report_passes_when_compliant_comment_exists(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
        issues_payload=[
            _issue(
                number=152,
                labels=("security",),
                closed_at="2026-05-22T12:00:00Z",
                comments=("placeholder comment", GOOD_EVIDENCE_COMMENT),
            )
        ],
    )
    assert result.status == "pass"
    assert result.reason_code == "ok"
    assert result.summary["flagged_issue_count"] == 0
    assert result.items[0]["matched_comment_index"] == 1


def test_run_closure_evidence_report_ignores_non_target_label_issue(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
        issues_payload=[
            _issue(
                number=153,
                labels=("documentation",),
                closed_at="2026-05-20T00:00:00Z",
                comments=(),
            )
        ],
    )
    assert result.status == "pass"
    assert result.summary["checked_issue_count"] == 0
    assert result.summary["flagged_issue_count"] == 0


@pytest.mark.parametrize(
    ("target_labels", "expected_target_labels", "expected_checked_issue_count"),
    (
        (None, list(DEFAULT_TARGET_LABELS), 2),
        ((), list(DEFAULT_TARGET_LABELS), 2),
        ((" ", "\t", "\n"), list(DEFAULT_TARGET_LABELS), 2),
        (
            (" Security ", "security", "TESTING", "testing ", "  "),
            ["security", "testing"],
            2,
        ),
    ),
)
def test_run_closure_evidence_report_normalizes_target_labels_and_defaults(
    tmp_path, target_labels, expected_target_labels, expected_checked_issue_count
) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    kwargs = {"target_labels": target_labels} if target_labels is not None else {}
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        issues_payload=[
            _issue(
                number=160,
                labels=("security",),
                closed_at="2026-05-20T00:00:00Z",
                comments=(GOOD_EVIDENCE_COMMENT,),
            ),
            _issue(
                number=161,
                labels=("testing",),
                closed_at="2026-05-20T00:00:00Z",
                comments=(GOOD_EVIDENCE_COMMENT,),
            ),
            _issue(
                number=162,
                labels=("documentation",),
                closed_at="2026-05-20T00:00:00Z",
                comments=(GOOD_EVIDENCE_COMMENT,),
            ),
        ],
        **kwargs,
    )
    assert result.status == "pass"
    assert result.summary["target_labels"] == expected_target_labels
    assert result.summary["checked_issue_count"] == expected_checked_issue_count
    assert result.summary["flagged_issue_count"] == 0


def test_run_closure_evidence_report_uses_best_missing_fields_when_no_comment_complies(
    tmp_path,
) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    missing_multiple_fields = GOOD_EVIDENCE_COMMENT.replace(
        "https://github.com/wryenmeek/knowledgebase/pull/151",
        "implementation shipped",
    ).replace(
        "PASS (all targeted tests passed)",
        "all targeted tests completed",
    )
    missing_single_field = GOOD_EVIDENCE_COMMENT.replace(
        "PASS (all targeted tests passed)",
        "all targeted tests completed",
    )
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
        issues_payload=[
            _issue(
                number=163,
                labels=("security",),
                closed_at="2026-05-20T00:00:00Z",
                comments=(missing_multiple_fields, missing_single_field),
            )
        ],
    )
    assert result.status == "fail"
    assert result.reason_code == "missing_closure_evidence"
    assert result.summary["flagged_issue_count"] == 1
    assert result.items[0]["missing_fields"] == ["pass_fail_summary"]


def test_run_closure_evidence_report_ignores_issue_outside_lookback_window(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=7,
        target_labels=("security",),
        issues_payload=[
            _issue(
                number=154,
                labels=("security",),
                closed_at="2026-04-10T00:00:00Z",
                comments=(GOOD_EVIDENCE_COMMENT,),
            )
        ],
    )
    assert result.status == "pass"
    assert result.summary["checked_issue_count"] == 0


def test_run_closure_evidence_report_loads_issues_json_fixture(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    fixture_path = tmp_path / "issues.json"
    fixture_path.write_text(
        json.dumps(
            {
                "issues": [
                    _issue(
                        number=155,
                        labels=("security",),
                        closed_at="2026-05-20T00:00:00Z",
                        comments=(GOOD_EVIDENCE_COMMENT,),
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        issues_json_path="issues.json",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
    )
    assert result.status == "pass"
    assert result.summary["source"] == "issues_json"
    assert result.summary["checked_issue_count"] == 1


def test_run_closure_evidence_report_fails_closed_on_invalid_payload_shape(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
        issues_payload={"not_issues": []},
    )
    assert result.status == "fail"
    assert result.reason_code == "invalid_input"


def test_run_closure_evidence_report_fails_when_repo_root_contract_missing(tmp_path) -> None:
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
        issues_payload=[],
    )
    assert result.status == "fail"
    assert result.reason_code == "prereq_missing:repo_root"


def test_run_closure_evidence_report_fails_closed_on_invalid_closed_at(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
        issues_payload=[
            _issue(
                number=156,
                labels=("security",),
                closed_at="not-a-timestamp",
                comments=(GOOD_EVIDENCE_COMMENT,),
            )
        ],
    )
    assert result.status == "fail"
    assert result.reason_code == "invalid_input"


def test_run_closure_evidence_report_rejects_issues_json_path_escape(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    outside = tmp_path.parent / "outside-issues.json"
    outside.write_text("{}", encoding="utf-8")
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        issues_json_path="../outside-issues.json",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
    )
    assert result.status == "fail"
    assert result.reason_code == "invalid_input"


def test_run_closure_evidence_report_rejects_negative_lookback(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=-1,
        target_labels=("security",),
        issues_payload=[],
    )
    assert result.status == "fail"
    assert result.reason_code == "invalid_input"


def test_run_closure_evidence_report_rejects_out_of_range_issue_limit(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
        issue_limit=999,
        issues_payload=[],
    )
    assert result.status == "fail"
    assert result.reason_code == "invalid_input"


def test_run_closure_evidence_report_fails_closed_when_gh_loader_errors(tmp_path, monkeypatch) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")

    def _raise_runtime_error(**_kwargs):
        raise RuntimeError("gh command failed: auth error")

    monkeypatch.setattr(closure_evidence, "_load_recent_closed_issues_from_gh", _raise_runtime_error)
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
    )
    assert result.status == "fail"
    assert result.reason_code == "gh_cli_failed"


def test_run_closure_evidence_report_fails_closed_on_invalid_as_of_timestamp(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="not-a-datetime",
        lookback_days=30,
        target_labels=("security",),
        issues_payload=[],
    )
    assert result.status == "fail"
    assert result.reason_code == "invalid_input"


def test_run_closure_evidence_report_fetches_and_evaluates_gh_issue_payload(tmp_path, monkeypatch) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")

    def _fake_run_gh_json(command, *, repo_root):
        assert repo_root == tmp_path.resolve()
        if command[:3] == ["gh", "issue", "list"]:
            return [
                {
                    "number": 157,
                    "title": "Issue 157",
                    "url": "https://github.com/wryenmeek/knowledgebase/issues/157",
                    "closedAt": "2026-05-20T00:00:00Z",
                    "labels": [{"name": "security"}],
                }
            ]
        if command[:3] == ["gh", "issue", "view"]:
            return {"comments": [{"body": GOOD_EVIDENCE_COMMENT}]}
        raise AssertionError(f"Unexpected gh command: {command}")

    monkeypatch.setattr(closure_evidence, "_run_gh_json", _fake_run_gh_json)
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
    )
    assert result.status == "pass"
    assert result.summary["source"] == "gh_cli"
    assert result.summary["checked_issue_count"] == 1


def test_run_closure_evidence_report_fails_closed_when_gh_issue_list_hits_issue_limit_cap(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")

    def _fake_run_gh_json(command, *, repo_root):
        assert repo_root == tmp_path.resolve()
        if command[:3] == ["gh", "issue", "list"]:
            return [
                {
                    "number": 170,
                    "title": "Issue 170",
                    "url": "https://github.com/wryenmeek/knowledgebase/issues/170",
                    "closedAt": "2026-05-20T00:00:00Z",
                    "labels": [{"name": "documentation"}],
                },
                {
                    "number": 171,
                    "title": "Issue 171",
                    "url": "https://github.com/wryenmeek/knowledgebase/issues/171",
                    "closedAt": "2026-05-19T00:00:00Z",
                    "labels": [{"name": "documentation"}],
                },
            ]
        if command[:3] == ["gh", "issue", "view"]:
            raise AssertionError("issue view should not run when issue list truncation is possible")
        raise AssertionError(f"Unexpected gh command: {command}")

    monkeypatch.setattr(closure_evidence, "_run_gh_json", _fake_run_gh_json)
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
        issue_limit=2,
    )
    assert result.status == "fail"
    assert result.reason_code == closure_evidence.REASON_CODE_INCOMPLETE_ISSUE_SCAN
    assert "issue-limit cap" in result.message


def test_run_closure_evidence_report_fails_closed_on_non_list_gh_issue_list_payload(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")

    def _fake_run_gh_json(_command, *, repo_root):
        assert repo_root == tmp_path.resolve()
        return {"unexpected": "shape"}

    monkeypatch.setattr(closure_evidence, "_run_gh_json", _fake_run_gh_json)
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
    )
    assert result.status == "fail"
    assert result.reason_code == "invalid_input"


def test_run_closure_evidence_report_fails_closed_on_missing_issue_number_in_gh_payload(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")

    def _fake_run_gh_json(command, *, repo_root):
        assert repo_root == tmp_path.resolve()
        if command[:3] == ["gh", "issue", "list"]:
            return [
                {
                    "title": "Issue",
                    "url": "https://github.com/wryenmeek/knowledgebase/issues/159",
                    "closedAt": "2026-05-20T00:00:00Z",
                    "labels": [{"name": "security"}],
                }
            ]
        raise AssertionError(f"Unexpected gh command: {command}")

    monkeypatch.setattr(closure_evidence, "_run_gh_json", _fake_run_gh_json)
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
    )
    assert result.status == "fail"
    assert result.reason_code == "invalid_input"


def test_run_closure_evidence_report_fails_closed_on_malformed_gh_comments_payload(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")

    def _fake_run_gh_json(command, *, repo_root):
        assert repo_root == tmp_path.resolve()
        if command[:3] == ["gh", "issue", "list"]:
            return [
                {
                    "number": 158,
                    "title": "Issue 158",
                    "url": "https://github.com/wryenmeek/knowledgebase/issues/158",
                    "closedAt": "2026-05-20T00:00:00Z",
                    "labels": [{"name": "security"}],
                }
            ]
        if command[:3] == ["gh", "issue", "view"]:
            return []
        raise AssertionError(f"Unexpected gh command: {command}")

    monkeypatch.setattr(closure_evidence, "_run_gh_json", _fake_run_gh_json)
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
    )
    assert result.status == "fail"
    assert result.reason_code == "invalid_input"


def test_run_closure_evidence_run_cli_rejects_invalid_mode(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    result_buffer = []

    class _Buffer:
        def write(self, value: str) -> int:
            result_buffer.append(value)
            return len(value)

    exit_code = closure_evidence.run_cli(
        argv=["--mode", "unknown-mode"],
        output_stream=_Buffer(),
    )
    payload = json.loads("".join(result_buffer))
    assert exit_code == 1
    assert payload["reason_code"] == "invalid_input"


def test_run_closure_evidence_report_executes_gh_from_repo_root_even_when_cwd_differs(
    tmp_path, monkeypatch
) -> None:
    repo_root = tmp_path / "repo-root"
    repo_root.mkdir()
    (repo_root / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    external_cwd = tmp_path / "external-cwd"
    external_cwd.mkdir()
    monkeypatch.chdir(external_cwd)

    observed_cwds: list[Path] = []

    def _fake_run(*args, **kwargs):
        command = list(args[0])
        observed_cwds.append(Path(kwargs["cwd"]).resolve())
        if command[:3] == ["gh", "issue", "list"]:
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "number": 157,
                            "title": "Issue 157",
                            "url": "https://github.com/wryenmeek/knowledgebase/issues/157",
                            "closedAt": "2026-05-20T00:00:00Z",
                            "labels": [{"name": "security"}],
                        }
                    ]
                ),
                stderr="",
            )
        if command[:3] == ["gh", "issue", "view"]:
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=json.dumps({"comments": [{"body": GOOD_EVIDENCE_COMMENT}]}),
                stderr="",
            )
        raise AssertionError(f"Unexpected gh command: {command}")

    monkeypatch.setattr(closure_evidence.subprocess, "run", _fake_run)
    result = run_closure_evidence_report(
        repo_root=repo_root,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
    )
    assert Path.cwd() == external_cwd
    assert result.status == "pass"
    assert observed_cwds
    assert set(observed_cwds) == {repo_root.resolve()}


def test_run_gh_json_fails_closed_when_gh_binary_missing(tmp_path, monkeypatch) -> None:
    def _raise_file_not_found(*_args, **_kwargs):
        raise FileNotFoundError("gh not found")

    monkeypatch.setattr(closure_evidence.subprocess, "run", _raise_file_not_found)
    with pytest.raises(RuntimeError, match="required but not installed"):
        closure_evidence._run_gh_json(["gh", "issue", "list"], repo_root=tmp_path.resolve())


def test_run_gh_json_fails_closed_on_nonzero_exit(tmp_path, monkeypatch) -> None:
    def _return_failure(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["gh", "issue", "list"],
            returncode=1,
            stdout="",
            stderr="authentication failed\n",
        )

    monkeypatch.setattr(closure_evidence.subprocess, "run", _return_failure)
    with pytest.raises(RuntimeError, match="gh command failed"):
        closure_evidence._run_gh_json(["gh", "issue", "list"], repo_root=tmp_path.resolve())


def test_run_gh_json_fails_closed_on_malformed_json(tmp_path, monkeypatch) -> None:
    def _return_bad_json(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["gh", "issue", "list"],
            returncode=0,
            stdout="{not-json}",
            stderr="",
        )

    monkeypatch.setattr(closure_evidence.subprocess, "run", _return_bad_json)
    with pytest.raises(RuntimeError, match="malformed JSON"):
        closure_evidence._run_gh_json(["gh", "issue", "list"], repo_root=tmp_path.resolve())


def test_run_gh_json_fails_closed_on_timeout(tmp_path, monkeypatch) -> None:
    def _raise_timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["gh", "issue", "list"],
            timeout=closure_evidence.GH_COMMAND_TIMEOUT_SECONDS,
        )

    monkeypatch.setattr(closure_evidence.subprocess, "run", _raise_timeout)
    with pytest.raises(
        RuntimeError,
        match=(
            f"gh command timed out after {closure_evidence.GH_COMMAND_TIMEOUT_SECONDS} seconds"
        ),
    ):
        closure_evidence._run_gh_json(["gh", "issue", "list"], repo_root=tmp_path.resolve())


def test_run_closure_evidence_report_fails_closed_on_gh_timeout(tmp_path, monkeypatch) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")

    def _raise_timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["gh", "issue", "list"],
            timeout=closure_evidence.GH_COMMAND_TIMEOUT_SECONDS,
        )

    monkeypatch.setattr(closure_evidence.subprocess, "run", _raise_timeout)
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
    )
    assert result.status == "fail"
    assert result.reason_code == "gh_cli_failed"
    assert result.message == f"gh command timed out after {closure_evidence.GH_COMMAND_TIMEOUT_SECONDS} seconds"


def test_resolve_repo_json_path_rejects_absolute_path(tmp_path) -> None:
    payload = tmp_path / "issues.json"
    payload.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="repo-relative"):
        closure_evidence._resolve_repo_json_path(tmp_path, str(payload.resolve()))


def test_resolve_repo_json_path_rejects_non_json_suffix(tmp_path) -> None:
    payload = tmp_path / "issues.txt"
    payload.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="existing .json file"):
        closure_evidence._resolve_repo_json_path(tmp_path, "issues.txt")


def test_resolve_repo_json_path_rejects_missing_file(tmp_path) -> None:
    with pytest.raises(ValueError, match="existing .json file"):
        closure_evidence._resolve_repo_json_path(tmp_path, "missing.json")


def test_default_target_labels_cover_issue_policy_scope() -> None:
    assert DEFAULT_TARGET_LABELS == ("security", "refactor", "testing", "hardening")
