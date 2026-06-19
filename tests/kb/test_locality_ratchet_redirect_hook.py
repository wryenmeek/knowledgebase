from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/hooks/locality_ratchet_redirect_hook.py"


def _run_hook(payload: object | str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    run_env = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        env=run_env,
    )


def test_user_prompt_submit_emits_context_block() -> None:
    result = _run_hook({"hookEventName": "UserPromptSubmit", "prompt": "/chronicle improve"})

    assert result.returncode == 0
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    hook_output = payload["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "UserPromptSubmit"
    context = str(hook_output["additionalContext"])
    assert "Slash-Command Override: /chronicle improve" in context
    assert "audit-knowledgebase-workspace" in context
    assert "deny-by-default for Locality 4 writes" in context


def test_unmatched_event_exits_cleanly_without_output() -> None:
    result = _run_hook({"hookEventName": "PostToolUse"})

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_malformed_payload_exits_cleanly_without_output() -> None:
    result = _run_hook("{not json")

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_hooks_json_registers_user_prompt_submit_command() -> None:
    hooks = json.loads((REPO_ROOT / ".github/hooks/hooks.json").read_text(encoding="utf-8"))
    user_prompt_submit = hooks["hooks"]["UserPromptSubmit"]

    matching_entries = [
        entry
        for entry in user_prompt_submit
        if entry.get("command") == "python3 scripts/hooks/locality_ratchet_redirect_hook.py"
    ]
    assert len(matching_entries) == 1
    assert matching_entries[0]["type"] == "command"
