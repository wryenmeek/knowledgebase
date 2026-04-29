"""Tests that CONTEXT.md files stay current relative to domain code changes.

Each CONTEXT.md has a ``last_updated`` frontmatter date.  When the domain code
it covers accumulates too many commits after that date, this test fails with an
actionable message telling the maintainer to review and refresh the file.
"""

from __future__ import annotations

import subprocess
import unittest
from datetime import date
from pathlib import Path
from typing import Sequence

from scripts.kb.page_template_utils import parse_frontmatter

REPO_ROOT = Path(__file__).resolve().parents[2]

# Maximum number of domain commits allowed since last_updated before the
# CONTEXT.md is considered stale and must be reviewed.
STALENESS_COMMIT_THRESHOLD = 10


class _DomainSpec:
    """Maps a CONTEXT.md file to the directories and pathspecs it covers."""

    __slots__ = ("context_path", "tracked_dirs", "exclude_patterns")

    def __init__(
        self,
        context_path: str,
        tracked_dirs: Sequence[str],
        exclude_patterns: Sequence[str] = (),
    ) -> None:
        self.context_path = context_path
        self.tracked_dirs = list(tracked_dirs)
        self.exclude_patterns = [
            f":(exclude){context_path}",
            *[f":(exclude){p}" for p in exclude_patterns],
        ]


# Repo-root CONTEXT.md is excluded — its domain is too broad to gate.
CONTEXT_DOMAINS: list[_DomainSpec] = [
    _DomainSpec(
        "scripts/kb/CONTEXT.md",
        tracked_dirs=["scripts/kb/"],
    ),
    _DomainSpec(
        "scripts/github_monitor/CONTEXT.md",
        tracked_dirs=["scripts/github_monitor/"],
    ),
    _DomainSpec(
        "scripts/drive_monitor/CONTEXT.md",
        tracked_dirs=["scripts/drive_monitor/"],
    ),
    _DomainSpec(
        "schema/CONTEXT.md",
        tracked_dirs=["schema/"],
    ),
    _DomainSpec(
        ".github/skills/CONTEXT.md",
        tracked_dirs=[".github/skills/", ".github/agents/", ".github/hooks/"],
        exclude_patterns=[".github/skills/references/"],
    ),
]


def _is_git_repo(root: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        cwd=root,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _commits_since(root: Path, spec: _DomainSpec, since: date) -> int:
    """Count domain commits after *since* (exclusive), excluding the CONTEXT.md itself."""
    cmd = [
        "git", "log", "--oneline", f"--since={since.isoformat()}",
        "--", *spec.tracked_dirs, *spec.exclude_patterns,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=root)
    if result.returncode != 0:
        return 0
    return len([ln for ln in result.stdout.splitlines() if ln.strip()])


class TestContextMdFreshness(unittest.TestCase):
    """Ensure CONTEXT.md files are refreshed when their domain code changes."""

    @classmethod
    def setUpClass(cls) -> None:
        if not _is_git_repo(REPO_ROOT):
            raise unittest.SkipTest("Not a git repository — skipping freshness check")

    def test_context_md_not_stale(self) -> None:
        for spec in CONTEXT_DOMAINS:
            with self.subTest(context_md=spec.context_path):
                ctx_path = REPO_ROOT / spec.context_path
                self.assertTrue(
                    ctx_path.exists(),
                    f"{spec.context_path} does not exist",
                )

                text = ctx_path.read_text(encoding="utf-8")
                fm = parse_frontmatter(text) or {}
                raw = fm.get("last_updated")
                self.assertIsNotNone(
                    raw,
                    f"{spec.context_path}: missing last_updated frontmatter field",
                )
                last_updated = date.fromisoformat(str(raw).strip())

                commits = _commits_since(REPO_ROOT, spec, last_updated)
                self.assertLess(
                    commits,
                    STALENESS_COMMIT_THRESHOLD,
                    f"\n{spec.context_path} is stale.\n"
                    f"  last_updated:       {last_updated}\n"
                    f"  commits since then: {commits}\n"
                    f"  threshold:          {STALENESS_COMMIT_THRESHOLD}\n"
                    f"  tracked dirs:       {', '.join(spec.tracked_dirs)}\n\n"
                    f"ACTION: Review {spec.context_path} — update Terms, "
                    f"Invariants, and File Roles to reflect current code, "
                    f"then bump last_updated.",
                )
