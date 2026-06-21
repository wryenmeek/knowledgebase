"""Workflow contract checks for the post-merge body-vs-diff audit."""

from __future__ import annotations

from pathlib import Path


WORKFLOW_PATH = Path(".github/workflows/post-merge-body-audit.yml")


def _workflow_text() -> str:
    assert WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}"
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_workflow_runs_only_after_pr_merge() -> None:
    workflow_text = _workflow_text()
    assert "name: Post-Merge Body-vs-Diff Audit" in workflow_text
    assert "pull_request:" in workflow_text
    assert "types: [closed]" in workflow_text
    assert "if: github.event.pull_request.merged == true" in workflow_text


def test_permissions_and_checkout_are_minimal_for_advisory_comments() -> None:
    workflow_text = _workflow_text()
    assert "contents: read" in workflow_text
    assert "pull-requests: write" in workflow_text
    assert "issues: read" in workflow_text
    assert "uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd" in workflow_text
    assert "persist-credentials: false" in workflow_text
    assert "uses: actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405" in workflow_text


def test_audit_command_uses_env_bound_pr_number() -> None:
    workflow_text = _workflow_text()
    assert "GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}" in workflow_text
    assert "PR_NUMBER: ${{ github.event.pull_request.number }}" in workflow_text
    assert 'python3 scripts/maintenance/audit_pr_body_vs_diff.py --pr "${PR_NUMBER}"' in workflow_text
    assert "--pr ${{ github.event.pull_request.number }}" not in workflow_text
