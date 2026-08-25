"""Pre-commit hook: block mixed-scope intake/control-plane commits.

This hook enforces two guards based on CI-1 gatekeeper path policy:
1. Reject staged commits that mix ``raw/inbox/**`` with sensitive non-inbox paths.
2. Reject staged commits that would transition the current branch into mixed scope
   relative to the merge-base with the default branch.

The benign LICENSE allowlist is intentionally strict (`LICENSE`, `LICENSE.md`,
`LICENSE.txt`, `LICENSE.rst`) to avoid prefix-based bypasses like `LICENSE.py`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):  # supports direct invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts._redaction import redact_stderr

_REPO_ROOT = Path(__file__).resolve().parents[2]

_INBOX_PREFIX = "raw/inbox/"
_BENIGN_PREFIXES = ("docs/", "tests/", "wiki/pages/", "wiki/sources/")
_BENIGN_EXACT = ("README.md",)
_BENIGN_LICENSE_FILES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENSE.rst")


def _normalize_paths(paths: list[str]) -> set[str]:
    normalized: set[str] = set()
    for path in paths:
        norm = path.strip().replace("\\", "/")
        if norm:
            normalized.add(norm)
    return normalized


def _is_benign_non_inbox(path: str) -> bool:
    if path.startswith(_BENIGN_PREFIXES):
        return True
    if path in _BENIGN_EXACT:
        return True
    return path in _BENIGN_LICENSE_FILES


def _classify_paths(paths: set[str]) -> tuple[set[str], set[str], set[str]]:
    inbox: set[str] = set()
    benign_non_inbox: set[str] = set()
    sensitive_non_inbox: set[str] = set()

    for path in paths:
        if path.startswith(_INBOX_PREFIX):
            inbox.add(path)
        elif _is_benign_non_inbox(path):
            benign_non_inbox.add(path)
        else:
            sensitive_non_inbox.add(path)

    return inbox, benign_non_inbox, sensitive_non_inbox


def _is_mixed_scope(paths: set[str]) -> bool:
    inbox, _, sensitive_non_inbox = _classify_paths(paths)
    return bool(inbox and sensitive_non_inbox)


def _git_stdout(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    if result.returncode != 0:
        stderr = redact_stderr(result.stderr or "")
        cmd = " ".join(["git", *args])
        raise RuntimeError(f"{cmd} failed: {stderr or f'exit {result.returncode}'}")
    return result.stdout


def _git_lines(args: list[str]) -> set[str]:
    return _normalize_paths(_git_stdout(args).splitlines())


def _has_head_commit() -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD"],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    return result.returncode == 0


def _resolve_default_base_ref() -> str:
    result = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    ref = result.stdout.strip()
    if result.returncode == 0 and ref:
        return ref

    for candidate in ("origin/main", "origin/master", "main", "master"):
        exists = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", candidate],
            capture_output=True,
            text=True,
            cwd=_REPO_ROOT,
        )
        if exists.returncode == 0:
            return candidate

    raise RuntimeError("unable to resolve default-branch reference (origin/main or main)")


def _current_branch_paths() -> set[str]:
    if not _has_head_commit():
        return set()

    base_ref = _resolve_default_base_ref()
    merge_base = _git_stdout(["merge-base", "HEAD", base_ref]).strip()
    if not merge_base:
        raise RuntimeError(f"git merge-base returned no output for HEAD and {base_ref}")
    return _git_lines(["diff", "--name-only", merge_base, "HEAD"])


def _format_paths(paths: set[str], *, limit: int = 8) -> str:
    if not paths:
        return "(none)"
    items = sorted(paths)
    if len(items) <= limit:
        return ", ".join(items)
    shown = ", ".join(items[:limit])
    return f"{shown}, ... (+{len(items) - limit} more)"


def main(argv: list[str] | None = None) -> int:
    files = argv if argv is not None else sys.argv[1:]
    staged_paths = _normalize_paths(files)
    if not staged_paths:
        staged_paths = _git_lines(["diff", "--cached", "--name-only"])
    if not staged_paths:
        return 0

    staged_inbox, _, staged_sensitive = _classify_paths(staged_paths)
    if staged_inbox and staged_sensitive:
        print("ERROR: mixed-scope staged commit detected.", file=sys.stderr)
        print(
            f"  inbox paths: {_format_paths(staged_inbox)}",
            file=sys.stderr,
        )
        print(
            f"  sensitive non-inbox paths: {_format_paths(staged_sensitive)}",
            file=sys.stderr,
        )
        print(
            "Hint: split intake (`raw/inbox/**`) and control-plane changes into separate commits.",
            file=sys.stderr,
        )
        return 1

    # Benign-only staged changes (docs/tests/wiki pages/readme/license files)
    # cannot create mixed scope and should not depend on branch baseline lookup.
    if not staged_inbox and not staged_sensitive:
        return 0

    try:
        branch_paths = _current_branch_paths()
    except RuntimeError as exc:
        print(
            f"ERROR: could not evaluate branch mixed-scope status: {exc}",
            file=sys.stderr,
        )
        return 1

    mixed_before = _is_mixed_scope(branch_paths)
    mixed_after = _is_mixed_scope(branch_paths | staged_paths)

    if not mixed_before and mixed_after:
        after_inbox, _, after_sensitive = _classify_paths(branch_paths | staged_paths)
        print(
            "ERROR: this commit would make the branch mixed-scope relative to default-branch merge-base.",
            file=sys.stderr,
        )
        print(
            f"  branch+staged inbox paths: {_format_paths(after_inbox)}",
            file=sys.stderr,
        )
        print(
            f"  branch+staged sensitive non-inbox paths: {_format_paths(after_sensitive)}",
            file=sys.stderr,
        )
        print(
            "Hint: keep intake work on an intake-only branch/commit series, and move control-plane edits to a separate branch.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
