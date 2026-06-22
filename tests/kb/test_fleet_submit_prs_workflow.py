"""Structural contract checks for .github/workflows/fleet-submit-prs.yml.

Asserts the following properties defined in the issue acceptance criteria:
- Both triggers present: ``schedule`` (cron ``0 4 * * *``) and ``workflow_dispatch``.
- ``permissions`` block is exactly ``contents: read`` + ``issues: write``.
- ``JULES_API_KEY`` is declared step-scoped (not at the job level).
- Concurrency block present with ``group: fleet-submit-prs``.
- No ``${{ inputs.* }}`` direct interpolation in ``run:`` blocks (shell injection guard).
"""

from __future__ import annotations

from pathlib import Path
import re

import yaml


WORKFLOW_PATH = Path(".github/workflows/fleet-submit-prs.yml")

PINNED_CRON = "0 4 * * *"


def _load_workflow() -> tuple[str, dict]:
    """Return (raw text, parsed YAML) for the workflow file."""
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return text, data


def _collect_job_level_env(workflow: dict) -> dict[str, dict]:
    """Return a mapping of job_id -> job-level env dict."""
    result: dict[str, dict] = {}
    for job_id, job in workflow.get("jobs", {}).items():
        env = job.get("env", {}) or {}
        result[job_id] = env
    return result


def _collect_run_blocks(workflow: dict) -> list[str]:
    """Return all ``run:`` string values from every step in every job."""
    runs: list[str] = []
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            run_val = step.get("run")
            if run_val:
                runs.append(str(run_val))
    return runs


# ---------------------------------------------------------------------------
# Existence
# ---------------------------------------------------------------------------


def test_workflow_file_exists() -> None:
    assert WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}"


# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------


def test_schedule_trigger_present() -> None:
    _text, data = _load_workflow()
    on_block = data.get(True, data.get("on", {}))
    assert "schedule" in on_block, "workflow must have a 'schedule' trigger"


def test_workflow_dispatch_trigger_present() -> None:
    _text, data = _load_workflow()
    on_block = data.get(True, data.get("on", {}))
    assert "workflow_dispatch" in on_block, "workflow must have a 'workflow_dispatch' trigger"


def test_cron_string_is_pinned() -> None:
    """The raw cron string '0 4 * * *' must appear verbatim (runbook sync test depends on this)."""
    text, data = _load_workflow()
    on_block = data.get(True, data.get("on", {}))
    schedule = on_block.get("schedule", []) or []
    crons = [str(item["cron"]) for item in schedule if isinstance(item, dict) and "cron" in item]
    assert PINNED_CRON in crons, (
        f"schedule must contain cron '{PINNED_CRON}'; found: {crons}"
    )
    # Also verify verbatim string appears in raw text (enforced by test_workflow_schedule_docs_sync.py)
    assert PINNED_CRON in text, f"cron '{PINNED_CRON}' must appear verbatim in workflow text"


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


def test_permissions_contents_read() -> None:
    _text, data = _load_workflow()
    perms = data.get("permissions", {}) or {}
    assert perms.get("contents") == "read", (
        f"permissions.contents must be 'read'; got: {perms.get('contents')!r}"
    )


def test_permissions_issues_write() -> None:
    _text, data = _load_workflow()
    perms = data.get("permissions", {}) or {}
    assert perms.get("issues") == "write", (
        f"permissions.issues must be 'write'; got: {perms.get('issues')!r}"
    )


def test_permissions_no_extra_entries() -> None:
    """Permissions block must be exactly contents: read + issues: write."""
    _text, data = _load_workflow()
    perms = data.get("permissions", {}) or {}
    expected_keys = {"contents", "issues"}
    extra = set(perms.keys()) - expected_keys
    assert not extra, (
        f"permissions block has unexpected entries: {extra}. "
        f"Must be exactly 'contents: read' + 'issues: write'."
    )


# ---------------------------------------------------------------------------
# Secret scoping
# ---------------------------------------------------------------------------


def test_jules_api_key_not_at_job_level() -> None:
    """JULES_API_KEY must be step-scoped, not declared at the job-level env block."""
    _text, data = _load_workflow()
    job_envs = _collect_job_level_env(data)
    for job_id, env in job_envs.items():
        assert "JULES_API_KEY" not in env, (
            f"JULES_API_KEY must not appear in job-level env for job '{job_id}'. "
            f"Declare it at the step level only (per AGENTS.md step-scoped secret rule)."
        )


def test_jules_api_key_present_in_a_step() -> None:
    """JULES_API_KEY must appear in at least one step-level env block."""
    _text, data = _load_workflow()
    found = False
    for job in data.get("jobs", {}).values():
        for step in job.get("steps", []):
            step_env = step.get("env", {}) or {}
            if "JULES_API_KEY" in step_env:
                found = True
                break
        if found:
            break
    assert found, (
        "JULES_API_KEY must be declared in at least one step-level env block. "
        "Per AGENTS.md, high-value secrets must be step-scoped."
    )


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def test_concurrency_block_present() -> None:
    _text, data = _load_workflow()
    assert "concurrency" in data, "workflow must have a top-level concurrency block"


def test_concurrency_group_is_fleet_submit_prs() -> None:
    _text, data = _load_workflow()
    concurrency = data.get("concurrency", {}) or {}
    assert concurrency.get("group") == "fleet-submit-prs", (
        f"concurrency.group must be 'fleet-submit-prs'; got: {concurrency.get('group')!r}"
    )


def test_concurrency_cancel_in_progress_false() -> None:
    _text, data = _load_workflow()
    concurrency = data.get("concurrency", {}) or {}
    assert concurrency.get("cancel-in-progress") is False, (
        "concurrency.cancel-in-progress must be false"
    )


# ---------------------------------------------------------------------------
# Shell injection guard
# ---------------------------------------------------------------------------


def test_no_inputs_direct_interpolation_in_run_blocks() -> None:
    """No ``${{ inputs.* }}`` must appear directly inside any run: block.

    Workflow inputs must be passed through env: blocks to avoid shell injection.
    This workflow has no workflow_dispatch inputs, so this is a forward-looking guard.
    """
    _text, data = _load_workflow()
    runs = _collect_run_blocks(data)
    pattern = re.compile(r"\$\{\{\s*inputs\.")
    for run_block in runs:
        assert not pattern.search(run_block), (
            f"run: block contains direct ${{{{ inputs.* }}}} interpolation (shell injection risk): "
            f"{run_block[:120]!r}"
        )
