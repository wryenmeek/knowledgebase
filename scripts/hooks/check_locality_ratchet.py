#!/usr/bin/env python3
"""Git hook: enforce the Locality 4 paired-deletion ratchet.

ADR-028 requires net-positive additions to each always-loaded instruction file
to either pair a substantive deletion in that file or carry a
``Locality-4-Justification:`` trailer. This hook computes non-exempt line
deltas for ``.github/copilot-instructions.md`` and ``AGENTS.md`` against either
the staged index or, for CI/all-files reruns with a clean index, ``HEAD``. The
pre-commit framework stage cannot see finalized commit-message trailers, so
trailer-only decisions are deferred there and enforced by the commit-msg stage.
When invoked with a commit message, it also enforces ADR-028's per-file 1-in-10
rolling soft budget for trailer escapes.
For GitHub Actions ``pull_request`` events, the trailer is read from the PR
head SHA (resolved via ``GITHUB_PR_HEAD_SHA`` or
``refs/remotes/origin/<GITHUB_HEAD_REF>``), not the auto-generated merge
commit. See ``_resolve_trailer_commit`` for the security gate (resolved SHA
must match the merge commit's second parent).
"""

from __future__ import annotations

from functools import lru_cache
import json
import os
import re
import select
import subprocess
import sys
from pathlib import Path

COPILOT_INSTRUCTIONS_PATH = ".github/copilot-instructions.md"
AGENTS_PATH = "AGENTS.md"
GATED_PATHS = frozenset({COPILOT_INSTRUCTIONS_PATH, AGENTS_PATH})
TRAILER = "Locality-4-Justification"
TRAILER_SOFT_BUDGET = 1
TRAILER_WINDOW_COMMITS = 10

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
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
    except (OSError, ValueError, AttributeError):
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
        for key in (
            "commit_msg_file",
            "commitMessageFile",
            "message_file",
            "messageFile",
        ):
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
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def _justification_trailer_value(message: str | None) -> str | None:
    if not message:
        return None

    rc, out, _ = _run_git("interpret-trailers", "--parse", input_text=message)
    trailer_lines = out.splitlines() if rc == 0 else message.splitlines()
    for line in trailer_lines:
        key, separator, value = line.partition(":")
        if separator and key.lower() == TRAILER.lower() and value.strip():
            return value.strip()
    return None


def _has_justification_trailer(message: str | None) -> bool:
    return _justification_trailer_value(message) is not None


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


@lru_cache(maxsize=4)
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


def _is_substantive_deleted_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("<!--")


def _html_comment_lines(content: str) -> set[int]:
    comment_lines: set[int] = set()
    # OPTIMIZATION: Fast-path literal check to avoid O(N) splitlines allocation
    if "<!--" not in content and "-->" not in content:
        return comment_lines
    in_comment = False
    for line_number, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if in_comment:
            comment_lines.add(line_number)
            if "-->" in stripped:
                in_comment = False
            continue
        if stripped.startswith("<!--"):
            comment_lines.add(line_number)
            if "-->" not in stripped:
                in_comment = True
    return comment_lines


def _line_delta_from_diff(
    path: str, diff: str, old_content: str, new_content: str
) -> tuple[int, int] | str:
    if (
        path == COPILOT_INSTRUCTIONS_PATH
        and new_content
        and len(_copilot_h2_lines(new_content)) < 2
    ):
        return f"{path}: missing expected second H2 boundary for gated-region detection"

    old_gated_lines = _gated_lines(path, old_content)
    new_gated_lines = _gated_lines(path, new_content)
    old_comment_lines = _html_comment_lines(old_content)

    additions = 0
    deletions = 0
    old_line: int | None = None
    new_line: int | None = None

    for line in diff.splitlines():
        hunk_match = _HUNK_RE.match(line)
        if hunk_match is not None:
            old_line = int(hunk_match.group(1))
            new_line = int(hunk_match.group(2))
            continue

        if old_line is None or new_line is None:
            continue

        if line.startswith("+") and not line.startswith("+++"):
            if new_line in new_gated_lines:
                additions += 1
            new_line += 1
            continue

        if line.startswith("-") and not line.startswith("---"):
            if (
                old_line in old_gated_lines
                and old_line not in old_comment_lines
                and _is_substantive_deleted_line(line[1:])
            ):
                deletions += 1
            old_line += 1
            continue

        if line.startswith(" "):
            old_line += 1
            new_line += 1

    return additions, deletions


def _line_delta_for_path(path: str) -> tuple[int, int] | str | None:
    diff = _staged_diff(path)
    if diff is None:
        return None

    return _line_delta_from_diff(
        path, diff, _get_head_content(path), _get_staged_content(path)
    )


def _commit_parents(commit: str) -> list[str] | None:
    rc, out, _ = _run_git("rev-list", "--parents", "-n", "1", commit)
    if rc != 0:
        return None
    parts = out.split()
    return parts[1:]


def _first_parent(commit: str) -> str | None:
    parents = _commit_parents(commit)
    return parents[0] if parents else None


def _second_parent(commit: str) -> str | None:
    parents = _commit_parents(commit)
    return parents[1] if parents is not None and len(parents) > 1 else None


def _content_at_revision(revision: str, path: str) -> str:
    rc, out, _ = _run_git("show", f"{revision}:{path}")
    return out if rc == 0 else ""


def _commit_message(commit: str) -> str | None:
    rc, out, _ = _run_git("log", "-1", "--format=%B", commit)
    return out if rc == 0 else None


def _resolve_commit_revision(revision: str) -> str | None:
    rc, out, _ = _run_git(
        "rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}"
    )
    return out.strip() if rc == 0 and out.strip() else None


def _resolve_trailer_commit(default_commit: str) -> str:
    """Return the commit whose message should be checked for the trailer.

    On GitHub Actions ``pull_request`` events, ``actions/checkout`` leaves HEAD
    at the synthetic merge commit. That commit's generated message lacks the PR
    author's ``Locality-4-Justification`` trailer, so trailer reads should use
    the PR head commit when checkout made it available. Diff inspection still
    uses HEAD and its first parent; this helper only selects the message source.

    Environment-derived refs are trusted only when they resolve to the merge
    commit's second parent. That keeps a colliding or stale remote branch from
    supplying an unrelated trailer for the checked-out merge commit.
    """
    if os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return default_commit

    expected_pr_head = _second_parent(default_commit)
    if expected_pr_head is None:
        return default_commit

    head_sha = os.environ.get("GITHUB_PR_HEAD_SHA")
    if head_sha:
        resolved_sha = _resolve_commit_revision(head_sha)
        if resolved_sha == expected_pr_head:
            return resolved_sha

    head_ref = os.environ.get("GITHUB_HEAD_REF")
    if head_ref:
        resolved_ref = _resolve_commit_revision(f"refs/remotes/origin/{head_ref}")
        if resolved_ref == expected_pr_head:
            return resolved_ref

    return default_commit


def _historical_line_delta_for_commit(
    path: str, commit: str
) -> tuple[int, int] | str | None:
    parent = _first_parent(commit)
    if parent is None:
        rc, diff, _ = _run_git("show", "--format=", "--unified=0", commit, "--", path)
        old_content = ""
    else:
        rc, diff, _ = _run_git("diff", "--unified=0", parent, commit, "--", path)
        old_content = _content_at_revision(parent, path)
    if rc != 0:
        return None

    new_content = _content_at_revision(commit, path)
    return _line_delta_from_diff(path, diff, old_content, new_content)


def _head_commit() -> str | None:
    rc, out, _ = _run_git("rev-parse", "--verify", "HEAD")
    return out.strip() if rc == 0 else None


def _recent_gated_commit_deltas(
    path: str,
    *,
    skip_commit: str | None = None,
    skip_commits: set[str] | None = None,
) -> tuple[list[tuple[str, tuple[int, int]]], str | None]:
    rc, out, _ = _run_git(
        "log",
        "--format=%H",
        "--",
        path,
    )
    if rc != 0:
        return [], f"{path}: cannot read recent commit history via git log"

    commits_to_skip = set(skip_commits or set())
    if skip_commit is not None:
        commits_to_skip.add(skip_commit)

    commits: list[tuple[str, tuple[int, int]]] = []
    for commit in out.splitlines():
        if commit in commits_to_skip:
            continue
        delta = _historical_line_delta_for_commit(path, commit)
        if delta is None:
            return [], f"{path}: cannot inspect historical gated delta for {commit}"
        if isinstance(delta, str):
            return [], delta
        additions, deletions = delta
        if additions == 0 and deletions == 0:
            continue
        commits.append((commit, delta))
        if len(commits) >= TRAILER_WINDOW_COMMITS:
            break

    return commits, None


def _trailer_candidate_commits(path: str) -> tuple[set[str], str | None]:
    rc, out, _ = _run_git("log", "--grep", TRAILER, "--format=%H", "--", path)
    if rc != 0:
        return set(), f"{path}: cannot read trailer history via git log --grep"
    return set(out.splitlines()), None


def _is_paired_deletion_commit(additions: int, deletions: int) -> bool:
    return deletions > 0 and additions - deletions <= 0


def _trailer_count_since_latest_paired_deletion(
    path: str,
    *,
    skip_commit: str | None = None,
    skip_commits: set[str] | None = None,
) -> tuple[int, str | None]:
    commits, error = _recent_gated_commit_deltas(
        path, skip_commit=skip_commit, skip_commits=skip_commits
    )
    if error is not None:
        return 0, error
    trailer_candidates, error = _trailer_candidate_commits(path)
    if error is not None:
        return 0, error

    count = 0
    for commit, (additions, deletions) in commits:
        if _is_paired_deletion_commit(additions, deletions):
            break
        if commit not in trailer_candidates:
            continue
        message = _commit_message(commit)
        if message is None:
            return 0, f"{path}: cannot read commit message for {commit}"
        if _has_justification_trailer(message):
            count += 1

    return count, None


def _trailer_budget_failures(
    paths: set[str],
    *,
    skip_commit: str | None = None,
    skip_commits: set[str] | None = None,
) -> list[str]:
    failures: list[str] = []
    for path in sorted(paths):
        count, error = _trailer_count_since_latest_paired_deletion(
            path, skip_commit=skip_commit, skip_commits=skip_commits
        )
        if error is not None:
            failures.append(error)
            continue
        if count >= TRAILER_SOFT_BUDGET:
            failures.append(
                f"{path}: Locality-4-Justification soft budget exceeded; "
                f"the last {TRAILER_WINDOW_COMMITS} gated commits already has "
                f"{count} trailer(s) since the latest paired-deletion commit. "
                "Stage a same-file paired deletion before using another trailer."
            )
    return failures


def _head_commit_failures(paths: set[str], commit_message: str | None) -> list[str]:
    parent = _first_parent("HEAD")
    if parent is None:
        return []
    head = _head_commit()
    if head is None:
        return ["HEAD: cannot resolve current commit for Locality 4 rerun"]

    if commit_message is not None:
        trailer_commit = head
        message = commit_message
    else:
        trailer_commit = _resolve_trailer_commit(head)
        message = _commit_message(trailer_commit)
    failures: list[str] = []
    for path in sorted(paths):
        delta = _historical_line_delta_for_commit(path, head)
        if delta is None:
            failures.append(f"{path}: cannot inspect HEAD gated delta for {head}")
            continue
        if isinstance(delta, str):
            failures.append(delta)
            continue
        additions, deletions = delta
        if additions - deletions <= 0:
            continue
        if not _has_justification_trailer(message):
            failures.append(
                f"{path}: HEAD commit has net-positive gated-region delta "
                f"+{additions}/-{deletions} without {TRAILER}: trailer"
            )
            continue
        # The current trailer may be on HEAD or the PR head behind the merge;
        # skip both so it is not counted as historical.
        budget_skip_commits = {head, trailer_commit}
        failures.extend(
            _trailer_budget_failures({path}, skip_commits=budget_skip_commits)
        )
    return failures


def _is_pre_commit_framework_without_message(commit_message: str | None) -> bool:
    return commit_message is None and os.environ.get("PRE_COMMIT") == "1"


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

    commit_message = (
        cli_commit_message if cli_commit_message is not None else stdin_commit_message
    )
    trailer_present = _has_justification_trailer(commit_message)
    trailer_decision_deferred = _is_pre_commit_framework_without_message(commit_message)
    clean_index_for_gated_paths = bool(deltas) and all(
        additions == 0 and deletions == 0 for additions, deletions in deltas.values()
    )
    if clean_index_for_gated_paths:
        failures.extend(_head_commit_failures(set(deltas), commit_message))
    budget_failures = (
        _trailer_budget_failures(set(positive_deltas))
        if positive_deltas and trailer_present
        else []
    )

    missing_trailer_failures = (
        positive_deltas and not trailer_present and not trailer_decision_deferred
    )

    if failures or missing_trailer_failures or budget_failures:
        print(
            "ERROR: Locality 4 ratchet violation for always-loaded instruction files.",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        for failure in budget_failures:
            print(f"  {failure}", file=sys.stderr)
        if missing_trailer_failures:
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
