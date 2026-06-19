#!/usr/bin/env python3
"""Warning-only PostToolUse advisory for Locality 4 instruction edits.

This hook exists for issue #195: after a successful edit/create-style tool
action touches `.github/copilot-instructions.md` or `AGENTS.md`, it reminds the
operator that those files are always-on Locality 4 context and should be
classified against the locality ladder before commit. The warning points to
ADR-028, especially the "Deletion pairing and trailer escape" section and the
Locality 3c PostToolUse advisory tier defined by the ladder.

Invariant: this script is advisory only. In normal mode it never exits non-zero,
never blocks the edit, and never mutates repository state. Missing fields,
malformed JSON, failed tool results, unsupported tools, or unmatched paths all
return 0 without emitting a warning. `DEBUG_LOCALITY_HOOK=1` is a local
debugging escape hatch that re-raises unexpected exceptions.

Output contract: for each matched Locality 4 path, emit one JSON warning record
to stdout. Each record includes a `hookSpecificOutput` envelope with
`hookEventName: "PostToolUse"` and `additionalContext` so hook hosts can show the
operator-facing advisory.

Placement chosen as Python under `scripts/hooks/` rather than shell under
`.github/hooks/` per plan — see commit message for rationale: Python provides
safe JSON parsing without jq dependency and enables unit testing.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable, Mapping
from typing import Any


LOCALITY_4_PATHS = (".github/copilot-instructions.md", "AGENTS.md")
DEBUG_ENV_VAR = "DEBUG_LOCALITY_HOOK"
PAYLOAD_ENV_VARS = (
    "COPILOT_HOOK_EVENT_PAYLOAD",
    "CLAUDE_HOOK_INPUT",
    "HOOK_EVENT_PAYLOAD",
)
PATH_KEYS = {
    "path",
    "file",
    "files",
    "file_path",
    "file_paths",
    "filePath",
    "filePaths",
    "paths",
    "matched_path",
    "matched_paths",
    "matched_file_path",
    "matched_file_paths",
    "edited_file",
    "edited_files",
    "changed_file",
    "changed_files",
}
# Only scan tool input/argument containers; result payloads may echo paths from
# diagnostics or metadata and should not trigger Locality 4 edit advisories.
PATH_CONTAINER_KEYS = {
    "args",
    "arguments",
    "input",
    "parameters",
    "tool_arguments",
    "tool_input",
    "toolInput",
}
WRITE_TOOL_NAMES = {
    "edit",
    "write",
    "create",
    "multiedit",
    "notebookedit",
    "apply_patch",
    "create_file",
    "write_file",
    "edit_file",
    "replace_string_in_file",
    "editfiles",
}
FAILURE_STATUSES = {
    "cancelled",
    "canceled",
    "error",
    "failed",
    "failure",
    "rejected",
    "timeout",
}
SUCCESS_STATUSES = {"completed", "ok", "passed", "success", "succeeded"}
EXIT_CODE_KEYS = ("returncode", "return_code", "exit_code", "status_code")


def _read_payload_text() -> str:
    if not sys.stdin.isatty():
        stdin_text = sys.stdin.read()
        if stdin_text.strip():
            return stdin_text
    for env_var in PAYLOAD_ENV_VARS:
        value = os.environ.get(env_var)
        if value:
            return value
    return "{}"


def _parse_payload(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    data = json.loads(text)
    return data if isinstance(data, dict) else {}


def _flatten_path_value(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        yield from _collect_paths(value)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _flatten_path_value(item)


def _collect_paths_from_container(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        yield from _collect_paths(value)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _collect_paths_from_container(item)


def _collect_paths(mapping: Mapping[str, Any]) -> Iterable[str]:
    for key, value in mapping.items():
        if key in PATH_KEYS:
            yield from _flatten_path_value(value)
        elif key in PATH_CONTAINER_KEYS:
            yield from _collect_paths_from_container(value)


def _payload_paths(payload: Mapping[str, Any]) -> list[str]:
    return list(_collect_paths(payload))


def _normalize_cwd(cwd: object) -> str:
    if not isinstance(cwd, str):
        return ""
    return cwd.strip().replace("\\", "/").rstrip("/")


def _normalize_path(raw_path: str, cwd: str) -> str:
    # Keep this lexical: hook payload paths may be synthetic and need not exist.
    path = raw_path.strip().replace("\\", "/")
    if path.startswith("file://"):
        path = path.removeprefix("file://")

    effective_cwd = cwd or os.getcwd().replace("\\", "/").rstrip("/")
    if path == effective_cwd or path.startswith(f"{effective_cwd}/"):
        path = path[len(effective_cwd):].lstrip("/")

    while path.startswith("./"):
        path = path[2:]

    parts: list[str] = []
    for part in path.split("/"):
        if part in {"", "."}:
            continue
        if part == ".." and parts:
            parts.pop()
        elif part == "..":
            parts.append(part)
        else:
            parts.append(part)
    return "/".join(parts)


def _matched_locality4_paths(paths: Iterable[str], cwd: str) -> list[str]:
    matched: list[str] = []
    for raw_path in paths:
        normalized = _normalize_path(raw_path, cwd)
        if normalized in LOCALITY_4_PATHS and normalized not in matched:
            matched.append(normalized)
    return matched


def _explicit_success(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 0
    if isinstance(value, str):
        return value.strip().lower() in SUCCESS_STATUSES
    if not isinstance(value, Mapping):
        return False

    for key in ("failed", "failure", "is_error"):
        if bool(value.get(key)):
            return False
    for key in ("error", "exception", "traceback"):
        if value.get(key):
            return False
    exit_code_success = _exit_code_success(value)
    if exit_code_success is False:
        return False
    for key in ("status", "outcome", "state"):
        status = value.get(key)
        if isinstance(status, str) and status.strip().lower() in FAILURE_STATUSES:
            return False

    for key in ("success", "ok", "succeeded"):
        if key in value:
            return bool(value[key])
    if exit_code_success is not None:
        return exit_code_success
    for key in ("status", "outcome", "state"):
        status = value.get(key)
        if isinstance(status, str) and status.strip().lower() in SUCCESS_STATUSES:
            return True
    return False


def _exit_code_success(mapping: Mapping[str, Any]) -> bool | None:
    saw_exit_code = False
    for key in EXIT_CODE_KEYS:
        code = mapping.get(key)
        if isinstance(code, int):
            saw_exit_code = True
            if code != 0:
                return False
    return True if saw_exit_code else None


def _tool_result_succeeded(payload: Mapping[str, Any]) -> bool:
    for key in ("tool_result", "tool_response", "result"):
        if key in payload:
            return _explicit_success(payload.get(key))
    return False


def _is_post_tool_use(payload: Mapping[str, Any]) -> bool:
    event_name = payload.get("hookEventName") or payload.get("hook_event_name")
    # Some hook hosts omit the event name for PostToolUse payloads. Missing stays
    # lenient so this advisory never blocks otherwise-valid write events.
    return not isinstance(event_name, str) or event_name == "PostToolUse"


def _is_write_tool(payload: Mapping[str, Any]) -> bool:
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str):
        return False
    return tool_name.strip().lower() in WRITE_TOOL_NAMES


def _warning_record(path: str) -> dict[str, object]:
    rationale = "Edits to this file load every turn — see ADR-028 for locality ladder guidance."
    redirect = (
        "Use `/chronicle improve` to route through `audit-knowledgebase-workspace` "
        "skill for paired-deletion or trailer-escape."
    )
    message = f"Locality 4 edit advisory for `{path}`. {rationale} {redirect}"
    return {
        "level": "warning",
        "code": "locality_4_edit_advisory",
        "path": path,
        "locality": "Locality 4",
        "adr": "ADR-028",
        "rationale": rationale,
        "redirect": redirect,
        "message": message,
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": message,
        },
    }


def main() -> int:
    try:
        payload = _parse_payload(_read_payload_text())
        if (
            not _is_post_tool_use(payload)
            or not _is_write_tool(payload)
            or not _tool_result_succeeded(payload)
        ):
            return 0

        cwd = _normalize_cwd(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR", ""))
        for path in _matched_locality4_paths(_payload_paths(payload), cwd):
            print(json.dumps(_warning_record(path), sort_keys=True))
    except Exception:
        if os.environ.get(DEBUG_ENV_VAR) == "1":
            raise
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
