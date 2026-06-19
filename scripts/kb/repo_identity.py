"""Canonical repository identity helpers for knowledgebase tooling."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

__all__ = ["default_repo_name"]


def default_repo_name(repo_root: Path) -> str:
    """Return the canonical fallback repository name for ``repo_root``.

    The helper prefers the configured ``remote.origin.url`` and extracts its
    terminal repository segment. That makes the result stable for standard
    checkouts, linked worktrees such as
    ``knowledgebase.worktrees/issue-XYZ/``, bare clones with an origin remote,
    and detached-HEAD checkouts because the query is independent of the current
    branch name and worktree directory basename.

    Query strings and fragments are ignored when parsing remote URLs so
    credential-bearing remotes cannot leak tokens into generated SourceRefs.
    When the git config query is unavailable, fails, or has no origin remote,
    the function falls back to the supplied root directory name. A trailing
    ``.git`` suffix is removed in both cases so bare clone directory names and
    remote URLs normalize consistently. The final value is sanitized to the
    SourceRef-safe repository-name character set, and ``"repo"`` is returned if
    sanitization would otherwise produce an empty string.
    """

    remote_name = _remote_origin_repo_name(repo_root)
    fallback_name = repo_root.name
    raw_name = _strip_git_suffix(remote_name or fallback_name)
    return re.sub(r"[^A-Za-z0-9_.-]", "-", raw_name) or "repo"


def _remote_origin_repo_name(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "config", "--get", "remote.origin.url"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""

    return _remote_repo_name_from_url(completed.stdout.strip())


def _remote_repo_name_from_url(remote_url: str) -> str:
    if not remote_url:
        return ""

    parsed = urlsplit(remote_url)
    if parsed.scheme:
        remote_path = parsed.path
    else:
        remote_path = remote_url.split("#", 1)[0].split("?", 1)[0]
    return remote_path.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]


def _strip_git_suffix(repo_name: str) -> str:
    if repo_name.endswith(".git"):
        return repo_name[:-4]
    return repo_name
