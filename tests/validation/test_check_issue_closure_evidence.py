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

GOOD_EXEMPTION_COMMENT = """### Closure evidence exemption
- Exemption rationale: Closed as part of a documentation-only sweep where no code, tests, or workflow files were changed.
"""

EXEMPTION_APPROVAL_LABEL = "closure-evidence-exemption-approved"


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


def test_evaluate_closure_evidence_comment_accepts_exemption_rationale() -> None:
    result = evaluate_closure_evidence_comment(
        GOOD_EXEMPTION_COMMENT,
        issue_labels=(EXEMPTION_APPROVAL_LABEL,),
    )
    assert result["is_compliant"] is True
    assert result["missing_fields"] == ()
    assert result["matched_template"] == "closure_evidence_exemption"


def test_evaluate_closure_evidence_comment_rejects_exemption_without_approval_label() -> None:
    result = evaluate_closure_evidence_comment(GOOD_EXEMPTION_COMMENT)
    assert result["is_compliant"] is False
    assert "closure_evidence_exemption_approval_label" in result["missing_fields"]


def test_evaluate_closure_evidence_comment_rejects_exemption_without_rationale() -> None:
    comment = GOOD_EXEMPTION_COMMENT.replace(
        "- Exemption rationale: Closed as part of a documentation-only sweep where no code, tests, or workflow files were changed.\n",
        "",
    )
    result = evaluate_closure_evidence_comment(comment)
    assert result["is_compliant"] is False
    assert "exemption_rationale" in result["missing_fields"]


def test_evaluate_closure_evidence_comment_rejects_exemption_without_heading() -> None:
    comment = GOOD_EXEMPTION_COMMENT.replace("### Closure evidence exemption\n", "")
    result = evaluate_closure_evidence_comment(
        comment,
        issue_labels=(EXEMPTION_APPROVAL_LABEL,),
    )
    assert result["is_compliant"] is False
    assert result["matched_template"] == "closure_evidence"
    assert "implementation_reference" in result["missing_fields"]


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


def test_run_closure_evidence_report_passes_when_exemption_comment_exists(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
        issues_payload=[
            _issue(
                number=154,
                labels=("security", EXEMPTION_APPROVAL_LABEL),
                closed_at="2026-05-22T12:00:00Z",
                comments=("placeholder comment", GOOD_EXEMPTION_COMMENT),
            )
        ],
    )
    assert result.status == "pass"
    assert result.reason_code == "ok"
    assert result.summary["flagged_issue_count"] == 0
    assert result.items[0]["matched_comment_index"] == 1


def test_run_closure_evidence_report_requires_exemption_approval_label(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        target_labels=("security",),
        issues_payload=[
            _issue(
                number=155,
                labels=("security",),
                closed_at="2026-05-22T12:00:00Z",
                comments=(GOOD_EXEMPTION_COMMENT,),
            )
        ],
    )
    assert result.status == "fail"
    assert result.reason_code == "missing_closure_evidence"
    assert result.items[0]["missing_fields"] == ["closure_evidence_exemption_approval_label"]


def test_run_closure_evidence_report_passes_when_exemption_label_is_present(tmp_path) -> None:
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
                labels=("security", EXEMPTION_APPROVAL_LABEL),
                closed_at="2026-05-22T12:00:00Z",
                comments=(GOOD_EXEMPTION_COMMENT,),
            )
        ],
    )
    assert result.status == "pass"
    assert result.reason_code == "ok"
    assert result.summary["flagged_issue_count"] == 0


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


def test_run_closure_evidence_report_lookback_zero_includes_only_as_of_timestamp(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=0,
        target_labels=("security",),
        issues_payload=[
            _issue(
                number=165,
                labels=("security",),
                closed_at="2026-05-24T23:59:59Z",
                comments=(GOOD_EVIDENCE_COMMENT,),
            ),
            _issue(
                number=166,
                labels=("security",),
                closed_at="2026-05-25T00:00:00Z",
                comments=(GOOD_EVIDENCE_COMMENT,),
            ),
        ],
    )
    assert result.status == "pass"
    assert result.summary["checked_issue_count"] == 1


def test_run_closure_evidence_report_filters_issues_before_closed_after_cutover(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=365,
        closed_after="2026-05-20T12:00:00Z",
        target_labels=("security",),
        issues_payload=[
            _issue(
                number=157,
                labels=("security",),
                closed_at="2026-05-20T11:59:59Z",
                comments=(),
            ),
            _issue(
                number=158,
                labels=("security",),
                closed_at="2026-05-20T12:00:00Z",
                comments=(GOOD_EVIDENCE_COMMENT,),
            ),
        ],
    )
    assert result.status == "pass"
    assert result.summary["checked_issue_count"] == 1
    assert result.summary["closed_after"] == "2026-05-20T12:00:00Z"


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


def test_run_closure_evidence_report_rejects_closed_after_newer_than_as_of(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        closed_after="2026-05-26T00:00:00Z",
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


def test_run_closure_evidence_report_fails_closed_on_invalid_closed_after_timestamp(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-05-25T00:00:00Z",
        lookback_days=30,
        closed_after="not-a-datetime",
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


def test_run_closure_evidence_run_cli_applies_closed_after_filter_from_args(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    fixture_path = tmp_path / "issues.json"
    fixture_path.write_text(
        json.dumps(
            {
                "issues": [
                    _issue(
                        number=180,
                        labels=("security",),
                        closed_at="2026-05-20T11:59:59Z",
                        comments=(),
                    ),
                    _issue(
                        number=181,
                        labels=("security",),
                        closed_at="2026-05-20T12:00:00Z",
                        comments=(GOOD_EVIDENCE_COMMENT,),
                    ),
                ]
            }
        ),
        encoding="utf-8",
    )

    result_buffer = []

    class _Buffer:
        def write(self, value: str) -> int:
            result_buffer.append(value)
            return len(value)

    exit_code = closure_evidence.run_cli(
        argv=[
            "--repo-root",
            str(tmp_path),
            "--mode",
            "report",
            "--issues-json",
            "issues.json",
            "--as-of",
            "2026-05-25T00:00:00Z",
            "--lookback-days",
            "365",
            "--closed-after",
            "2026-05-20T12:00:00Z",
            "--target-label",
            "security",
        ],
        output_stream=_Buffer(),
    )
    payload = json.loads("".join(result_buffer))
    assert exit_code == 0
    assert payload["summary"]["checked_issue_count"] == 1
    assert payload["summary"]["closed_after"] == "2026-05-20T12:00:00Z"


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


def test_run_gh_json_redacts_token_shaped_stderr_at_callsite(tmp_path, monkeypatch) -> None:
    """Integration-level regression: `_run_gh_json` must redact token-shaped
    stderr via the real `scripts._redaction.redact_stderr` helper, not a
    mocked/stubbed version. This guards the actual call site wiring added in
    PR #434 (import + invocation of `redact_stderr` inside `_run_gh_json`),
    complementing the helper's own unit tests in `tests/test_redaction.py`.
    """
    leaked_token = "ghp_" + "A" * 36

    def _return_failure_with_token(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["gh", "issue", "list"],
            returncode=1,
            stdout="",
            stderr=f"error: Authorization: Bearer {leaked_token} rejected\n",
        )

    monkeypatch.setattr(closure_evidence.subprocess, "run", _return_failure_with_token)
    with pytest.raises(RuntimeError, match="gh command failed") as excinfo:
        closure_evidence._run_gh_json(["gh", "issue", "list"], repo_root=tmp_path.resolve())

    assert leaked_token not in str(excinfo.value)
    assert "[REDACTED]" in str(excinfo.value)


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


# ---------------------------------------------------------------------------
# Regression tests: closure evidence comment formats for issues flagged in
# CI-2 run on PR #333 (wryenmeek/knowledgebase#335).  Each test verifies that
# the comment posted on the corresponding GitHub issue is accepted as
# compliant, guarding against future checker logic changes that would silently
# invalidate these real-world comment formats.
# ---------------------------------------------------------------------------

_EVIDENCE_COMMENT_301 = """\
### Closure evidence
- Implementation reference: PR #315 (`Fix truthiness bypass bug in fleet archive-stale-sessions.ts`)
- Key files/surfaces changed:
  - `scripts/fleet/archive-stale-sessions.ts` (parseCliArgs:121-127 — explicit non-empty + non-whitespace check)
  - `scripts/fleet/archive-stale-sessions.test.ts` (lines 146-156 — `--apply` with whitespace-only and empty `--source-filter` both denied)
- Validation commands:
  - `grep -nE "source-filter|sourceFilter|parseCliArgs" scripts/fleet/archive-stale-sessions.ts`
  - `grep -nE "whitespace|empty|source-filter" scripts/fleet/archive-stale-sessions.test.ts`
  - `cd scripts/fleet && bun test archive-stale-sessions.test.ts`
- Pass/fail summary: PASS — whitespace-only and empty --source-filter both denied; trimmed-value case accepted. Acceptance checklist fully covered.
"""

_EVIDENCE_COMMENT_302 = """\
### Closure evidence
- Implementation reference: commit `83295a3` (`feat: address #311 (Layer 9 issues:write) + #324 (LockUnavailableError kwarg)`)
- Key files/surfaces changed:
  - `scripts/kb/write_utils.py` (lines 407-409 — meta-lock LockUnavailableError raised with lock_file_path=repo_root / contracts.GOVERNANCE_META_LOCK_PATH)
  - `tests/kb/test_write_utils.py` (lines 262-303 — sibling-contention tests assert holder_alive == True and holder_context_hash matches hex pattern)
- Validation commands:
  - `grep -nE "GOVERNANCE_META_LOCK_PATH|_acquire_sibling_governance_lock|LockUnavailableError" scripts/kb/write_utils.py`
  - `grep -nE "holder_alive|holder_context_hash" tests/kb/test_write_utils.py`
  - `python3 -m pytest tests/kb/test_write_utils.py -k "sibling_governance or customizations_lock" -v`
- Pass/fail summary: PASS — meta-lock LockUnavailableError carries valid holder_alive and holder_context_hash metadata regardless of caller cwd; both sibling-contention tests propagate holder fields.
"""

_EVIDENCE_COMMENT_306 = """\
### Closure evidence
- Implementation reference: commit `4e7679b` / PR #312 (`ci: add environment and concurrency to jules-archive-stale workflow`)
- Key files/surfaces changed:
  - `.github/workflows/jules-archive-stale.yml` — environment: jules-archive-approval added to the archive job; concurrency block added partitioned by inputs.apply with cancel-in-progress: false
- Validation commands:
  - `grep -nE "environment:|concurrency:" .github/workflows/jules-archive-stale.yml`
  - `python3 -m pytest tests/kb/test_jules_archive_stale_workflow.py -v`
- Pass/fail summary: PASS — environment gate matches CI-4 pattern; destructive apply runs blocked behind reviewer approval; concurrency races eliminated.
"""

_EVIDENCE_COMMENT_318 = """\
### Closure evidence
- Implementation reference: commit `7fa5ab8` (`feat(tests): shell-execution harness for Phase 2b workflow steps (#318)`)
- Key files/surfaces changed:
  - `tests/kb/fleet_dispatch_harness.py` (~250 LOC) — primitives build_fixture_repo and extract_step_script
  - `tests/kb/test_fleet_dispatch_after_merge_integration.py` — scenarios driving the harness against fleet-dispatch-after-merge.yml steps
  - `AGENTS.md` write-surface matrix row added for tests/kb/fleet_dispatch_harness.py
- Validation commands:
  - `python3 -m pytest tests/kb/test_fleet_dispatch_after_merge_integration.py -v`
  - `python3 -m pytest tests/kb/test_framework_write_surface_matrix.py -v`
- Pass/fail summary: PASS — harness reproduces Layer-7 and Layer-8 trap classes locally; integration tests green; matrix row enforced.
"""

_EVIDENCE_COMMENT_320 = """\
### Closure evidence
- Implementation reference: commit `6c274c6` (`feat: address #320 (jules-archive-stale contract test) + #321 (extract_frontmatter BOM)`)
- Key files/surfaces changed:
  - `tests/kb/test_jules_archive_stale_workflow.py` (new file, 7 contract tests pinning forbidden inputs.apply string-comparison, required boolean-truthy form, destructive branch jules-archive-approval, concurrency partitioned by inputs.apply, cancel-in-progress false)
- Validation commands:
  - `python3 -m pytest tests/kb/test_jules_archive_stale_workflow.py -v`
  - `python3 -m pytest tests/kb/test_jules_archive_stale_workflow.py`
- Pass/fail summary: PASS — 7 contract tests pass; would have caught the HIGH-severity environment-gate string-comparison bug found post-merge in PR #312.
"""


@pytest.mark.parametrize(
    ("issue_number", "labels", "comment"),
    (
        (301, ("bug", "security", "testing"), _EVIDENCE_COMMENT_301),
        (302, ("bug", "testing"), _EVIDENCE_COMMENT_302),
        (306, ("security",), _EVIDENCE_COMMENT_306),
        (318, ("testing",), _EVIDENCE_COMMENT_318),
        (320, ("testing",), _EVIDENCE_COMMENT_320),
    ),
)
def test_evaluate_closure_evidence_comment_accepts_ci2_335_remediation_formats(
    issue_number: int,
    labels: tuple[str, ...],
    comment: str,
) -> None:
    """Verify each closure evidence comment posted to fix CI-2 failure on PR #333
    is accepted as compliant by the checker (regression guard for issue #335)."""
    result = evaluate_closure_evidence_comment(comment, issue_labels=labels)
    assert result["is_compliant"] is True, (
        f"Issue #{issue_number} closure evidence comment was rejected; "
        f"missing fields: {result['missing_fields']}"
    )
    assert result["missing_fields"] == ()


def test_run_closure_evidence_report_passes_for_all_ci2_335_remediated_issues(
    tmp_path,
) -> None:
    """All 5 issues flagged in CI-2 run on PR #333 now have compliant closure
    evidence comments; this integration test verifies all pass together."""
    (tmp_path / "AGENTS.md").write_text("matrix placeholder\n", encoding="utf-8")
    result = run_closure_evidence_report(
        repo_root=tmp_path,
        mode="report",
        as_of="2026-06-22T00:00:00Z",
        lookback_days=365,
        closed_after="2026-05-25T00:00:00Z",
        target_labels=("security", "testing", "bug"),
        issues_payload=[
            _issue(
                number=301,
                labels=("bug", "security", "testing"),
                closed_at="2026-06-21T06:18:46Z",
                comments=(_EVIDENCE_COMMENT_301,),
            ),
            _issue(
                number=302,
                labels=("bug", "testing"),
                closed_at="2026-06-21T06:21:18Z",
                comments=(_EVIDENCE_COMMENT_302,),
            ),
            _issue(
                number=306,
                labels=("security",),
                closed_at="2026-06-20T22:05:33Z",
                comments=(_EVIDENCE_COMMENT_306,),
            ),
            _issue(
                number=318,
                labels=("testing",),
                closed_at="2026-06-21T05:33:07Z",
                comments=(_EVIDENCE_COMMENT_318,),
            ),
            _issue(
                number=320,
                labels=("testing",),
                closed_at="2026-06-21T05:12:08Z",
                comments=(_EVIDENCE_COMMENT_320,),
            ),
        ],
    )
    assert result.status == "pass", (
        f"Expected pass but got {result.status}; items: {result.items}"
    )
    assert result.summary["checked_issue_count"] == 5
    assert result.summary["flagged_issue_count"] == 0
