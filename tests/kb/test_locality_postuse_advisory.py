from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/hooks/locality_postuse_advisory.py")


def _run_hook(payload: object | str) -> subprocess.CompletedProcess[str]:
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_hook_from_env(payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "COPILOT_HOOK_EVENT_PAYLOAD": json.dumps(payload)}
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="",
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _warning_json(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(result.stdout)


def _successful_edit_payload(path: str) -> dict[str, object]:
    return {
        "hookEventName": "PostToolUse",
        "tool_name": "edit",
        "tool_arguments": {"path": path},
        "tool_result": {"success": True},
    }


def test_copilot_instructions_edit_emits_warning_to_stdout() -> None:
    result = _run_hook(_successful_edit_payload(".github/copilot-instructions.md"))

    assert result.returncode == 0
    assert result.stderr == ""
    warning = _warning_json(result)
    assert warning["level"] == "warning"
    assert warning["code"] == "locality_4_edit_advisory"
    assert warning["path"] == ".github/copilot-instructions.md"
    assert warning["locality"] == "Locality 4"
    assert warning["adr"] == "ADR-028"
    assert "Edits to this file load every turn" in str(warning["rationale"])
    assert "/chronicle improve" in str(warning["redirect"])
    assert "audit-knowledgebase-workspace" in str(warning["redirect"])
    assert "paired-deletion" in str(warning["redirect"])
    assert "trailer-escape" in str(warning["redirect"])
    assert ".github/copilot-instructions.md" in str(warning["message"])
    hook_output = warning["hookSpecificOutput"]
    assert isinstance(hook_output, dict)
    assert hook_output["hookEventName"] == "PostToolUse"
    assert str(hook_output["additionalContext"]) == warning["message"]


def test_agents_edit_emits_warning_to_stdout() -> None:
    result = _run_hook(_successful_edit_payload("AGENTS.md"))

    assert result.returncode == 0
    assert result.stderr == ""
    warning = _warning_json(result)
    assert warning["code"] == "locality_4_edit_advisory"
    assert warning["path"] == "AGENTS.md"
    assert warning["adr"] == "ADR-028"
    assert "/chronicle improve" in str(warning["redirect"])


def test_tool_input_files_match_emits_warning_to_stdout() -> None:
    payload = {
        "hookEventName": "PostToolUse",
        "tool_name": "edit",
        "tool_input": {"files": ["docs/architecture.md", "AGENTS.md"]},
        "tool_result": {"success": True},
    }

    result = _run_hook(payload)

    assert result.returncode == 0
    assert result.stderr == ""
    assert _warning_json(result)["path"] == "AGENTS.md"


def test_env_payload_with_empty_stdin_emits_warning_to_stdout() -> None:
    result = _run_hook_from_env(_successful_edit_payload("AGENTS.md"))

    assert result.returncode == 0
    assert result.stderr == ""
    assert _warning_json(result)["path"] == "AGENTS.md"


def test_unmatched_edit_exits_cleanly_without_warning() -> None:
    result = _run_hook(_successful_edit_payload("docs/architecture.md"))

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == ""


def test_unmatched_tool_input_files_exits_cleanly_without_warning() -> None:
    payload = {
        "hookEventName": "PostToolUse",
        "tool_name": "edit",
        "tool_input": {"files": ["docs/architecture.md"]},
        "tool_result": {"success": True},
    }

    result = _run_hook(payload)

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == ""


def test_nested_absolute_agents_path_exits_cleanly_without_warning() -> None:
    payload = _successful_edit_payload("/workspace/subfolder/AGENTS.md")

    result = _run_hook(payload)

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == ""


def test_failed_tool_result_exits_cleanly_without_warning() -> None:
    payload = _successful_edit_payload("AGENTS.md")
    payload["tool_result"] = {"success": False, "error": "edit failed"}

    result = _run_hook(payload)

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == ""


def test_missing_tool_result_exits_cleanly_without_warning() -> None:
    payload = _successful_edit_payload("AGENTS.md")
    del payload["tool_result"]

    result = _run_hook(payload)

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == ""


def test_hook_never_exits_nonzero_regardless_of_input() -> None:
    payloads: tuple[object | str, ...] = (
        _successful_edit_payload("AGENTS.md"),
        _successful_edit_payload("docs/architecture.md"),
        {
            "tool_name": "edit",
            "tool_arguments": {"path": "AGENTS.md"},
            "tool_result": {"success": False},
        },
        {"tool_arguments": {"paths": ["AGENTS.md", ".github/copilot-instructions.md"]}},
        "",
        "{not json",
        [],
    )

    for payload in payloads:
        result = _run_hook(payload)
        assert result.returncode == 0


def test_hooks_json_registers_posttooluse_advisory_command() -> None:
    hooks = json.loads(Path(".github/hooks/hooks.json").read_text(encoding="utf-8"))
    post_tool_use = hooks["hooks"]["PostToolUse"]

    matching_entries = [
        entry
        for entry in post_tool_use
        if entry.get("command") == "python3 scripts/hooks/locality_postuse_advisory.py"
    ]

    assert len(matching_entries) == 1
    assert matching_entries[0]["type"] == "command"
    matcher = matching_entries[0].get("matcher", "")
    assert "edit" in str(matcher).lower()
    assert "create" in str(matcher).lower()
    assert "notebookedit" in str(matcher).lower()
