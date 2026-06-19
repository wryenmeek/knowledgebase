#!/usr/bin/env python3
"""Git hook: ratchet scripts away from legacy approval-flag spelling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ADR_REFERENCE = "ADR-030"
_APPROVAL_TOKEN = "--" + "approval"
_APPROVAL_EQUALS_TOKEN = f"{_APPROVAL_TOKEN}="
APPROVAL_EQUALS_REJECTION_DEADLINE = date(2026, 12, 31)
PAYLOAD_ENV_VARS = (
    "COPILOT_HOOK_EVENT_PAYLOAD",
    "CLAUDE_HOOK_INPUT",
    "HOOK_EVENT_PAYLOAD",
)
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
PATH_KEYS = {
    "path",
    "file",
    "files",
    "file_path",
    "file_paths",
    "filePath",
    "filePaths",
    "paths",
    "edited_file",
    "edited_files",
    "changed_file",
    "changed_files",
}
PATH_CONTAINER_KEYS = {"args", "arguments", "input", "parameters", "tool_arguments", "tool_input", "toolInput"}

# Transitional exemptions:
# - scripts/_optional_surface_common.py owns compatibility alias handling.
# - scripts/kb/checkpoint_registry.py already uses --apply for bootstrap semantics.
_EXEMPT_PATHS = frozenset({
    "scripts/_optional_surface_common.py",
    "scripts/kb/checkpoint_registry.py",
})


@dataclass(frozen=True, slots=True)
class StagedScriptPath:
    status: str
    path: str
    old_path: str | None = None


def _run_git(*args: str) -> tuple[int, str, str]:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _normalize_path(path: str) -> str:
    normalized = path.strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _is_scripts_python_path(path: str) -> bool:
    parts = path.split("/")
    return (
        path.startswith("scripts/")
        and path.endswith(".py")
        and "__pycache__" not in parts
        and ".." not in parts
        and "" not in parts
    )


def _staged_script_paths() -> tuple[list[StagedScriptPath], str | None]:
    rc, out, err = _run_git(
        "diff",
        "--cached",
        "--name-status",
        "--find-renames",
        "--find-copies",
        "--",
        "scripts",
    )
    if rc != 0:
        return [], f"cannot enumerate staged script paths: {err.strip() or out.strip()}"

    staged: list[StagedScriptPath] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            return [], f"unexpected git name-status line: {line!r}"
        status = parts[0]
        status_code = status[:1]
        path = _normalize_path(parts[-1])
        old_path = (
            _normalize_path(parts[1])
            if status_code in {"C", "R"} and len(parts) >= 3
            else None
        )
        if status_code in {"A", "C", "M", "R"} and _is_scripts_python_path(path):
            staged.append(StagedScriptPath(status=status, path=path, old_path=old_path))
    return staged, None


def _get_staged_content(path: str) -> tuple[str, str | None]:
    rc, out, err = _run_git("show", f":{path}")
    if rc != 0:
        return "", f"{path}: cannot read staged content: {err.strip() or out.strip()}"
    return out, None


def _contains_approval_flag(text: str) -> bool:
    return _APPROVAL_TOKEN in text


def _contains_approval_equals(text: str) -> bool:
    return _APPROVAL_EQUALS_TOKEN in text


def _migration_deadline_passed(today: date | None = None) -> bool:
    observed = today or date.today()
    return observed > APPROVAL_EQUALS_REJECTION_DEADLINE


def _read_hook_payload_text() -> str:
    for env_var in PAYLOAD_ENV_VARS:
        value = os.environ.get(env_var)
        if value:
            return value
    if not sys.stdin.isatty():
        try:
            return sys.stdin.read()
        except OSError:
            return ""
    return ""


def _parse_hook_payload() -> dict[str, Any]:
    payload_text = _read_hook_payload_text().strip()
    if not payload_text:
        return {}
    payload = json.loads(payload_text)
    return payload if isinstance(payload, dict) else {}


def _collect_paths(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        collected_from_list: list[str] = []
        for item in value:
            collected_from_list.extend(_collect_paths(item))
        return collected_from_list
    if isinstance(value, dict):
        collected_from_dict: list[str] = []
        for key, nested in value.items():
            if key in PATH_KEYS:
                collected_from_dict.extend(_collect_paths(nested))
            elif key in PATH_CONTAINER_KEYS:
                collected_from_dict.extend(_collect_paths(nested))
        return collected_from_dict
    return []


def _normalize_payload_path(path: str, cwd: str) -> str:
    normalized = path.strip().replace("\\", "/")
    if normalized.startswith("file://"):
        normalized = normalized.removeprefix("file://")
    if cwd and (normalized == cwd or normalized.startswith(f"{cwd}/")):
        normalized = normalized[len(cwd):].lstrip("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return _normalize_path(normalized)


def _payload_script_paths() -> tuple[list[StagedScriptPath], str | None]:
    try:
        payload = _parse_hook_payload()
    except json.JSONDecodeError as exc:
        return [], f"invalid PostToolUse payload: {exc.msg}"

    if not payload:
        return [], None

    event_name = payload.get("hookEventName") or payload.get("hook_event_name")
    if isinstance(event_name, str) and event_name != "PostToolUse":
        return [], None

    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str) or tool_name.strip().lower() not in WRITE_TOOL_NAMES:
        return [], None

    tool_result = payload.get("tool_result")
    if isinstance(tool_result, dict):
        if tool_result.get("success") is False:
            return [], None
        if isinstance(tool_result.get("returncode"), int) and tool_result["returncode"] != 0:
            return [], None
    elif isinstance(tool_result, bool) and not tool_result:
        return [], None

    cwd = payload.get("cwd")
    normalized_cwd = cwd.strip().replace("\\", "/").rstrip("/") if isinstance(cwd, str) else ""

    payload_paths = []
    for raw_path in _collect_paths(payload):
        normalized = _normalize_payload_path(raw_path, normalized_cwd)
        if _is_scripts_python_path(normalized):
            payload_paths.append(normalized)

    deduped = list(dict.fromkeys(payload_paths))
    return [StagedScriptPath(status="M", path=path) for path in deduped], None


def main(argv: list[str] | None = None) -> int:
    _ = argv
    staged_paths, staged_error = _payload_script_paths()
    if staged_error is not None:
        print(f"ERROR: {staged_error}", file=sys.stderr)
        return 1
    use_worktree_content = bool(staged_paths)
    if not staged_paths:
        staged_paths, staged_error = _staged_script_paths()
    if staged_error is not None:
        print(f"ERROR: {staged_error}", file=sys.stderr)
        return 1

    failures: list[str] = []
    for staged_path in staged_paths:
        if use_worktree_content:
            file_path = Path(staged_path.path)
            if file_path.exists():
                staged_text = file_path.read_text(encoding="utf-8")
                read_error = None
            else:
                staged_text, read_error = "", f"{staged_path.path}: cannot read worktree content"
        else:
            staged_text, read_error = _get_staged_content(staged_path.path)
        if read_error is not None:
            failures.append(read_error)
            continue
        if (
            _contains_approval_equals(staged_text)
            and _migration_deadline_passed()
        ):
            failures.append(
                f"{staged_path.path}: {_APPROVAL_EQUALS_TOKEN}<value> is forbidden after "
                f"{APPROVAL_EQUALS_REJECTION_DEADLINE.isoformat()}; use --apply"
            )
            continue
        if staged_path.path in _EXEMPT_PATHS:
            continue
        if not _contains_approval_flag(staged_text):
            continue
        status_code = staged_path.status[:1]
        if status_code == "A":
            failures.append(
                f"{staged_path.path}: new scripts may not introduce legacy {_APPROVAL_TOKEN}; "
                "use --apply"
            )
        else:
            failures.append(
                f"{staged_path.path}: modified legacy script still uses {_APPROVAL_TOKEN}; "
                "migrate to --apply in the same change"
            )

    if failures:
        print(
            "ERROR: approval-flag migration ratchet (ADR-030)",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
