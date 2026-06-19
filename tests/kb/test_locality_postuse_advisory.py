from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/hooks/locality_postuse_advisory.py"


def _run_hook(
    payload: object | str, *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
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


def _warning_lines(result: subprocess.CompletedProcess[str]) -> list[dict[str, object]]:
    return [json.loads(line) for line in result.stdout.splitlines()]


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
    assert "ADR-028" in str(warning["message"])
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


def test_very_large_payload_does_not_crash_or_block() -> None:
    big_blob = "x" * (10 * 1024 * 1024)
    payload = _successful_edit_payload("AGENTS.md")
    tool_arguments = payload["tool_arguments"]
    assert isinstance(tool_arguments, dict)
    tool_arguments["noise"] = big_blob

    result = _run_hook(payload)

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


def test_tool_result_paths_do_not_trigger_recursive_false_positive() -> None:
    payload = _successful_edit_payload("docs/architecture.md")
    payload["tool_result"] = {
        "success": True,
        "path": "AGENTS.md",
    }

    result = _run_hook(payload)

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == ""


def test_pretooluse_event_exits_cleanly_without_warning() -> None:
    payload = _successful_edit_payload("AGENTS.md")
    payload["hookEventName"] = "PreToolUse"

    result = _run_hook(payload)

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == ""


def test_non_write_tool_exits_cleanly_without_warning() -> None:
    payload = _successful_edit_payload("AGENTS.md")
    payload["tool_name"] = "bash"

    result = _run_hook(payload)

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == ""


def test_multiple_matches_emit_json_line_per_matched_path() -> None:
    payload = {
        "hookEventName": "PostToolUse",
        "tool_name": "edit",
        "tool_input": {"files": ["AGENTS.md", ".github/copilot-instructions.md"]},
        "tool_result": {"success": True},
    }

    result = _run_hook(payload)

    assert result.returncode == 0
    assert result.stderr == ""
    warnings = _warning_lines(result)
    assert [warning["path"] for warning in warnings] == [
        "AGENTS.md",
        ".github/copilot-instructions.md",
    ]


def test_absolute_path_under_cwd_matches_locality4_file() -> None:
    payload = _successful_edit_payload("/workspace/repo/AGENTS.md")
    payload["cwd"] = "/workspace/repo"

    result = _run_hook(payload)

    assert result.returncode == 0
    assert result.stderr == ""
    assert _warning_json(result)["path"] == "AGENTS.md"


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


def test_success_indicator_variants_emit_warning_to_stdout() -> None:
    success_results: tuple[dict[str, object], ...] = (
        {"status": "ok"},
        {"status": "passed"},
        {"returncode": 0},
        {"ok": True},
    )

    for tool_result in success_results:
        payload = _successful_edit_payload("AGENTS.md")
        payload["tool_result"] = tool_result

        result = _run_hook(payload)

        assert result.returncode == 0
        assert result.stderr == ""
        assert _warning_json(result)["path"] == "AGENTS.md"


def test_mixed_success_and_error_result_exits_without_warning() -> None:
    payload = _successful_edit_payload("AGENTS.md")
    payload["tool_result"] = {"success": True, "error": "write failed"}

    result = _run_hook(payload)

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == ""


def test_conflicting_exit_code_aliases_treat_any_nonzero_as_failure() -> None:
    payload = _successful_edit_payload("AGENTS.md")
    payload["tool_result"] = {"returncode": 0, "exit_code": 1}

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


def test_empty_malformed_and_missing_field_payloads_emit_no_output() -> None:
    payloads: tuple[object | str, ...] = (
        "",
        "{not json",
        [],
        {"tool_arguments": {"path": "AGENTS.md"}},
    )

    for payload in payloads:
        result = _run_hook(payload)
        assert result.returncode == 0
        assert result.stdout == ""
        assert result.stderr == ""


def test_debug_env_reraises_unexpected_errors_for_local_debugging() -> None:
    result = _run_hook("{not json", env={"DEBUG_LOCALITY_HOOK": "1"})

    assert result.returncode != 0
    assert "JSONDecodeError" in result.stderr


def test_hooks_json_registers_posttooluse_advisory_command() -> None:
    hooks = json.loads(
        (REPO_ROOT / ".github/hooks/hooks.json").read_text(encoding="utf-8")
    )
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
