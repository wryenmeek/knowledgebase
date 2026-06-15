#!/usr/bin/env python3
"""Pre-commit hook: enforce the Locality 4 paired-deletion ratchet.

ADR-028 requires net-positive additions to each always-loaded instruction
file to either pair a deletion in that file in the same staged commit or carry a
``Locality-4-Justification:`` trailer. This hook computes the staged
non-exempt line delta for ``.github/copilot-instructions.md`` and ``AGENTS.md``
against ``HEAD`` and fails closed when either file's gated delta is positive
without a trailer supplied by the invoking hook wrapper.
"""

from __future__ import annotations

import json
import re
import select
import subprocess
import sys
from pathlib import Path

COPILOT_INSTRUCTIONS_PATH = ".github/copilot-instructions.md"
AGENTS_PATH = "AGENTS.md"
GATED_PATHS = frozenset({COPILOT_INSTRUCTIONS_PATH, AGENTS_PATH})
TRAILER = "Locality-4-Justification"

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_MARKDOWN_TABLE_SEPARATOR_RE = re.compile(r"^\|[\s:|-]+\|$")


def _run_git(*args: str, input_text: str | None = None) -> tuple[int, str, str]:
    result = subprocess.run(
        ["git", *args],
        input=input_text,
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


def _has_invalid_path_components(path: str) -> bool:
    parts = path.split("/")
    return path.startswith("/") or "\\" in path or ".." in parts or "" in parts


def _extract_string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _read_available_stdin() -> tuple[list[str], str | None]:
    try:
        if sys.stdin.isatty():
            return [], None
        readable, _, _ = select.select([sys.stdin], [], [], 0)
        if not readable:
            return [], None
        stdin_text = sys.stdin.read()
    except (OSError, ValueError):
        return [], None

    stripped = stdin_text.strip()
    if not stripped:
        return [], None

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return [_normalize_path(line) for line in stdin_text.splitlines()], None

    if not isinstance(payload, dict):
        return [], None

    paths: list[str] = []
    for key in (
        "paths",
        "files",
        "staged_files",
        "stagedFiles",
        "changed_files",
        "changedFiles",
    ):
        paths.extend(_extract_string_list(payload.get(key)))

    commit_message: str | None = None
    for key in ("commit_message", "commitMessage", "message"):
        value = payload.get(key)
        if isinstance(value, str):
            commit_message = value
            break

    if commit_message is None:
        for key in ("commit_msg_file", "commitMessageFile", "message_file", "messageFile"):
            value = payload.get(key)
            if isinstance(value, str):
                commit_message = _read_commit_message_file(value)
                break

    return [_normalize_path(path) for path in paths], commit_message


def _split_cli_args(argv: list[str]) -> tuple[list[str], str | None]:
    paths: list[str] = []
    commit_message: str | None = None
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--":
            paths.extend(argv[index + 1 :])
            break
        if arg == "--commit-message" and index + 1 < len(argv):
            commit_message = argv[index + 1]
            index += 2
            continue
        if arg == "--commit-msg-file" and index + 1 < len(argv):
            commit_message = _read_commit_message_file(argv[index + 1])
            index += 2
            continue
        paths.append(arg)
        index += 1
    return paths, commit_message


def _read_commit_message_file(path: str) -> str | None:
    normalized = _normalize_path(path)
    if _has_invalid_path_components(normalized):
        return None
    try:
        return Path(normalized).read_text(encoding="utf-8")
    except OSError:
        return None


def _has_justification_trailer(message: str | None) -> bool:
    if not message:
        return False

    rc, out, _ = _run_git("interpret-trailers", "--parse", input_text=message)
    trailer_lines = out.splitlines() if rc == 0 else message.splitlines()
    prefix = f"{TRAILER}:"
    return any(
        line.startswith(prefix) and bool(line[len(prefix) :].strip())
        for line in trailer_lines
    )


def _get_staged_paths() -> tuple[set[str], str | None]:
    rc, out, _ = _run_git("diff", "--cached", "--name-only")
    if rc != 0:
        return set(), "cannot enumerate staged paths via git diff --cached --name-only"
    return (
        {
            normalized
            for path in out.splitlines()
            if (normalized := _normalize_path(path)) and normalized in GATED_PATHS
        },
        None,
    )


def _get_staged_content(path: str) -> str:
    rc, out, _ = _run_git("show", f":{path}")
    return out if rc == 0 else ""


def _get_head_content(path: str) -> str:
    rc, out, _ = _run_git("show", f"HEAD:{path}")
    return out if rc == 0 else ""


def _copilot_h2_lines(content: str) -> list[int]:
    lines = content.splitlines()
    return [
        line_number
        for line_number, line in enumerate(lines, start=1)
        if line.startswith("## ")
    ]


def _copilot_gated_lines(content: str) -> set[int]:
    lines = content.splitlines()
    h2_lines = _copilot_h2_lines(content)
    if len(h2_lines) < 2:
        return set(range(1, len(lines) + 1))
    return set(range(h2_lines[1], len(lines) + 1))


def _agents_matrix_body_lines(content: str) -> set[int]:
    lines = content.splitlines()
    in_matrix_section = False
    body_started = False
    exempt_lines: set[int] = set()

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped == "## Write-surface matrix":
            in_matrix_section = True
            continue
        if in_matrix_section and line.startswith("## "):
            break
        if not in_matrix_section:
            continue

        if not body_started:
            if _MARKDOWN_TABLE_SEPARATOR_RE.fullmatch(stripped):
                body_started = True
            continue

        if stripped.startswith("|"):
            exempt_lines.add(line_number)
        else:
            break

    return exempt_lines


def _gated_lines(path: str, content: str) -> set[int]:
    line_count = len(content.splitlines())
    if path == COPILOT_INSTRUCTIONS_PATH:
        return _copilot_gated_lines(content)
    if path == AGENTS_PATH:
        return set(range(1, line_count + 1)) - _agents_matrix_body_lines(content)
    return set()


def _staged_diff(path: str) -> str | None:
    rc, out, _ = _run_git("diff", "--cached", "--unified=0", "--", path)
    return out if rc == 0 else None


def _line_delta_for_path(path: str) -> tuple[int, int] | str | None:
    diff = _staged_diff(path)
    if diff is None:
        return None

    old_content = _get_head_content(path)
    new_content = _get_staged_content(path)
    if (
        path == COPILOT_INSTRUCTIONS_PATH
        and new_content
        and len(_copilot_h2_lines(new_content)) < 2
    ):
        return f"{path}: missing expected second H2 boundary for gated-region detection"

    old_gated_lines = _gated_lines(path, old_content)
    new_gated_lines = _gated_lines(path, new_content)

    additions = 0
    deletions = 0
    old_line: int | None = None
    new_line: int | None = None

    for line in diff.splitlines():
        hunk_match = _HUNK_RE.match(line)
        if hunk_match is not None:
            old_line = int(hunk_match.group(1))
            new_line = int(hunk_match.group(3))
            continue

        if old_line is None or new_line is None:
            continue

        if line.startswith("+") and not line.startswith("+++"):
            if new_line in new_gated_lines:
                additions += 1
            new_line += 1
            continue

        if line.startswith("-") and not line.startswith("---"):
            if old_line in old_gated_lines:
                deletions += 1
            old_line += 1
            continue

        if line.startswith(" "):
            old_line += 1
            new_line += 1

    return additions, deletions


def _candidate_paths(paths: list[str]) -> tuple[set[str], list[str]]:
    failures: list[str] = []
    normalized_paths: set[str] = set()

    for path in paths:
        normalized = _normalize_path(path)
        if not normalized:
            continue
        if normalized in GATED_PATHS and _has_invalid_path_components(normalized):
            failures.append(f"{path}: invalid Locality 4 path")
            continue
        if normalized in GATED_PATHS:
            normalized_paths.add(normalized)

    staged_paths, staged_path_error = _get_staged_paths()
    if staged_path_error is not None:
        failures.append(staged_path_error)

    return normalized_paths | staged_paths, failures


def main(argv: list[str] | None = None) -> int:
    raw_args = sys.argv[1:] if argv is None else argv
    arg_paths, cli_commit_message = _split_cli_args(raw_args)
    stdin_paths, stdin_commit_message = _read_available_stdin()
    all_paths = arg_paths + stdin_paths
    gated_paths, failures = _candidate_paths(all_paths)

    deltas: dict[str, tuple[int, int]] = {}
    for path in sorted(gated_paths):
        delta = _line_delta_for_path(path)
        if delta is None:
            failures.append(f"{path}: cannot read staged diff via git diff --cached")
            continue
        if isinstance(delta, str):
            failures.append(delta)
            continue
        deltas[path] = delta

    positive_deltas = {
        path: (additions, deletions)
        for path, (additions, deletions) in deltas.items()
        if additions - deletions > 0
    }

    commit_message = cli_commit_message if cli_commit_message is not None else stdin_commit_message
    trailer_present = _has_justification_trailer(commit_message)

    if failures or (positive_deltas and not trailer_present):
        print(
            "ERROR: Locality 4 ratchet violation for always-loaded instruction files.",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        if positive_deltas and not trailer_present:
            print(
                "\nStaged gated-region line delta is net-positive outside exempt regions:",
                file=sys.stderr,
            )
            for path, (additions, deletions) in positive_deltas.items():
                print(
                    f"  {path}: +{additions}/-{deletions} "
                    f"(net {additions - deletions:+d})",
                    file=sys.stderr,
                )
            print(
                "\nFix: stage a paired deletion in each net-positive file so its "
                "gated delta is <= 0, or commit with "
                "a trailer such as:\n"
                "  Locality-4-Justification: <why this rule must remain Locality 4>",
                file=sys.stderr,
            )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
