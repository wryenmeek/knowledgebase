"""Structural contract checks for .github/workflows/commit-scope-check.yml."""

from __future__ import annotations

from pathlib import Path
import re

WORKFLOW_PATH = Path(".github/workflows/commit-scope-check.yml")


def _workflow_text() -> str:
    assert WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}"
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_workflow_triggers_on_correct_pr_events() -> None:
    """Workflow must trigger on opened, synchronize, and edited PR events."""
    wf = _workflow_text()
    assert "pull_request:" in wf, "Missing pull_request trigger"
    assert "opened" in wf, "Missing 'opened' event type"
    assert "synchronize" in wf, "Missing 'synchronize' event type"
    # 'edited' re-fires on title edits, closing the rename-after-draft loophole.
    assert "edited" in wf, "Missing 'edited' event type"


def test_workflow_targets_main_branch() -> None:
    """Workflow must target the main branch only."""
    wf = _workflow_text()
    assert "branches: [main]" in wf or "branches:\n    - main" in wf or "- main" in wf


def test_workflow_permissions_are_read_only() -> None:
    """Workflow must declare exactly pull-requests: read and contents: read."""
    wf = _workflow_text()
    assert "pull-requests: read" in wf, "Missing pull-requests: read permission"
    assert "contents: read" in wf, "Missing contents: read permission"
    # Ensure no write permissions are present.
    assert "pull-requests: write" not in wf, "pull-requests: write must not be present"
    assert "contents: write" not in wf, "contents: write must not be present"
    assert "issues: write" not in wf, "issues: write must not be present"


def test_workflow_has_concurrency_block() -> None:
    """Workflow must have a concurrency block to cancel superseded runs."""
    wf = _workflow_text()
    assert "concurrency:" in wf, "Missing concurrency block"


def test_summary_step_has_always_condition() -> None:
    """The summary/reporting step must run with ``if: always()`` so it fires
    even when the check step fails."""
    wf = _workflow_text()
    assert "if: always()" in wf, "Missing 'if: always()' on summary step"


def test_no_direct_expression_interpolation_in_run_blocks() -> None:
    """No ``${{ ... }}`` expressions may appear inside ``run:`` block content.

    All PR metadata (title, body, number) must be routed through ``env:``
    blocks and referenced as shell variables to prevent script-injection.
    """
    lines = _workflow_text().splitlines()
    in_run = False
    run_indent = 0

    for lineno, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if re.match(r"run:\s*[|>]?\s*$", stripped) or stripped.startswith("run: "):
            in_run = True
            run_indent = indent
            # Check the inline run value too (single-line ``run: cmd``).
            inline = stripped[len("run:"):].strip()
            assert "${{" not in inline, (
                f"Line {lineno}: direct ${{{{...}}}} interpolation on inline run: {line!r}"
            )
            continue

        if in_run:
            if stripped == "" or (stripped and indent <= run_indent):
                in_run = False
            else:
                assert "${{" not in line, (
                    f"Line {lineno}: direct ${{{{...}}}} interpolation inside run block: {line!r}"
                )


def test_pr_metadata_routed_through_env_vars() -> None:
    """PR number, title, and body must be routed via env: blocks, not inline."""
    wf = _workflow_text()
    assert "PR_NUMBER:" in wf, "PR_NUMBER must be declared in an env: block"
    assert "PR_TITLE:" in wf, "PR_TITLE must be declared in an env: block"
    assert "PR_BODY:" in wf, "PR_BODY must be declared in an env: block"


def test_workflow_uses_continue_on_error_for_gate_step() -> None:
    """The gate check step must use continue-on-error so the summary step always runs."""
    wf = _workflow_text()
    assert "continue-on-error: true" in wf, (
        "Missing continue-on-error: true on the gate check step"
    )
