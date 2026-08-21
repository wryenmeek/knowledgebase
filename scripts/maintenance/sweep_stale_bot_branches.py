"""Scan and report (or delete) stale bot-authored branches.

Reads ``git for-each-ref`` output for refs matching a narrow include-regex,
filters to branches older than STALE_THRESHOLD_DAYS with no open PR, and
either reports what *would* be deleted (dry-run mode) or performs the deletion
(real-delete mode, gated by environment approval in the workflow).

This module is a read-only surface in the AGENTS.md write-surface matrix when
``dry_run=True``; it produces only stdout/step-summary output and never
mutates the repository.  When ``dry_run=False`` the sole external side effect
is ``git push --delete origin -- "$BRANCH"`` (argv-safe, ``--`` terminator,
double-quoted shell variable).  That path is gated by the
``sweep-real-delete-approval`` GitHub Environment and will not be enabled
until issue wryenmeek/knowledgebase#351 creates that environment.

Usage (from repo root):
    python -m scripts.maintenance.sweep_stale_bot_branches \\
        [--stale-days 14] [--dry-run | --no-dry-run] [--output-summary PATH]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts._redaction import redact_stderr

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SURFACE = "scripts/maintenance/sweep_stale_bot_branches.py"

#: Narrow allowlist regex — only branches matching this pattern are considered.
BRANCH_INCLUDE_REGEX = re.compile(r"^(jules/|google-labs-jules/|copilot/)")

#: Defense-in-depth blocklist: applied AFTER the include regex.  Even if a
#: future regex broadening accidentally matches these names, the blocklist
#: short-circuits the sweep.
BRANCH_EXCLUDE_BLOCKLIST: frozenset[str] = frozenset(
    {"main", "fleet-state", "gh-pages"}
)

#: Default staleness threshold in days.
STALE_THRESHOLD_DAYS: int = 14

#: Explicitly NOT swept: ``agents/issue-*`` branches (fleet convention, mixed
#: authorship, review can take weeks).  The include regex already excludes
#: these, but the comment makes the intent explicit.
_NOT_SWEPT_NOTE = (
    "agents/issue-* branches are deliberately excluded (see BRANCH_INCLUDE_REGEX)"
)


class BranchInfo(NamedTuple):
    """Information about a single remote branch candidate."""

    name: str
    commit_age_days: float
    has_open_pr: bool


# ---------------------------------------------------------------------------
# Filtering logic
# ---------------------------------------------------------------------------


def branch_matches_include(branch_name: str) -> bool:
    """Return True if *branch_name* matches the narrow include allowlist regex."""
    return bool(BRANCH_INCLUDE_REGEX.match(branch_name))


def branch_in_exclude_blocklist(branch_name: str) -> bool:
    """Return True if *branch_name* is in the hardcoded exclude blocklist."""
    return branch_name in BRANCH_EXCLUDE_BLOCKLIST


def is_stale(
    branch_info: BranchInfo, stale_threshold_days: int = STALE_THRESHOLD_DAYS
) -> bool:
    """Return True if the branch is older than *stale_threshold_days* AND has no open PR."""
    return (
        branch_info.commit_age_days >= stale_threshold_days
        and not branch_info.has_open_pr
    )


def filter_branches(
    candidates: Sequence[BranchInfo],
    stale_threshold_days: int = STALE_THRESHOLD_DAYS,
) -> list[BranchInfo]:
    """Return branches that should be swept.

    A branch is swept when:
    1. It matches BRANCH_INCLUDE_REGEX.
    2. It is NOT in BRANCH_EXCLUDE_BLOCKLIST.
    3. Its last commit is >= stale_threshold_days old.
    4. It has no open PR.
    """
    result: list[BranchInfo] = []
    for branch in candidates:
        if not branch_matches_include(branch.name):
            continue
        if branch_in_exclude_blocklist(branch.name):
            continue
        if is_stale(branch, stale_threshold_days):
            result.append(branch)
    return result


# ---------------------------------------------------------------------------
# Git / GitHub helpers
# ---------------------------------------------------------------------------


def _run(
    cmd: list[str], check: bool = True, capture: bool = True
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
    )


def enumerate_remote_branches() -> list[tuple[str, float]]:
    """Return (branch_short_name, commit_age_days) for each remote branch.

    Uses ``git for-each-ref`` with a format string to avoid manual parsing of
    ``git branch -r`` output.  The short name strips the ``refs/remotes/origin/``
    prefix.
    """
    try:
        result = _run(
            [
                "git",
                "for-each-ref",
                "--format=%(refname:short) %(committerdate:unix)",
                "refs/remotes/origin/",
            ]
        )
    except subprocess.CalledProcessError as exc:
        print(
            f"[{SURFACE}] ERROR: git for-each-ref failed: {redact_stderr(exc.stderr)}",
            file=sys.stderr,
        )
        return []

    now = int(time.time())
    entries: list[tuple[str, float]] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(" ", 1)
        if len(parts) != 2:
            continue
        ref_short, ts_str = parts
        # Strip "origin/" prefix to get the branch name
        branch_name = ref_short.removeprefix("origin/")
        try:
            commit_ts = int(ts_str)
        except ValueError:
            continue
        commit_age_days = (now - commit_ts) / 86400
        entries.append((branch_name, commit_age_days))
    return entries


def check_open_pr(branch_name: str) -> bool:
    """Return True if there is at least one open PR targeting *branch_name* as head.

    Uses ``gh pr list --head <branch> --state open --json number``.
    SECURITY: branch_name is passed as a positional argument (not interpolated
    into a shell string) so no shell injection is possible.
    """
    try:
        result = _run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch_name,
                "--state",
                "open",
                "--json",
                "number",
            ]
        )
        import json as _json

        items = _json.loads(result.stdout or "[]")
        return len(items) > 0
    except (subprocess.CalledProcessError, ValueError):
        # Fail-safe: assume there IS an open PR so we don't delete something active
        return True


def delete_branch(branch_name: str) -> bool:
    """Delete *branch_name* from origin.  Returns True on success.

    SECURITY: uses ``git push --delete origin -- "$branch_name"``  pattern
    (double-dashes terminate option parsing; branch_name is a list element,
    not a shell string interpolation).
    """
    try:
        _run(["git", "push", "--delete", "origin", "--", branch_name])
        return True
    except subprocess.CalledProcessError as exc:
        print(
            f"[{SURFACE}] ERROR deleting {branch_name}: {redact_stderr(exc.stderr)}",
            file=sys.stderr,
        )
        return False


# ---------------------------------------------------------------------------
# Main sweep logic
# ---------------------------------------------------------------------------


def build_branch_info_list(
    stale_threshold_days: int = STALE_THRESHOLD_DAYS,
) -> list[BranchInfo]:
    """Build the full list of BranchInfo for all matching remote branches."""
    raw = enumerate_remote_branches()
    result: list[BranchInfo] = []
    for branch_name, age_days in raw:
        if not branch_matches_include(branch_name):
            continue
        if branch_in_exclude_blocklist(branch_name):
            continue
        has_pr = check_open_pr(branch_name)
        result.append(
            BranchInfo(name=branch_name, commit_age_days=age_days, has_open_pr=has_pr)
        )
    return result


def run_sweep(
    dry_run: bool = True,
    stale_threshold_days: int = STALE_THRESHOLD_DAYS,
    output_summary_path: str | None = None,
) -> int:
    """Run the sweep.  Returns an exit code (0 = success, 1 = error)."""
    branch_infos = build_branch_info_list(stale_threshold_days)
    to_sweep = [b for b in branch_infos if is_stale(b, stale_threshold_days)]

    if dry_run:
        _print_dry_run_summary(to_sweep, stale_threshold_days, output_summary_path)
        return 0

    # Real-delete path — only reached when dry_run=False AND the
    # sweep-real-delete-approval GitHub Environment approved the run.
    errors = 0
    for branch in to_sweep:
        success = delete_branch(branch.name)
        if success:
            print(
                f"[{SURFACE}] Deleted: {branch.name} (age={branch.commit_age_days:.1f}d)"
            )
        else:
            errors += 1
    print(
        f"[{SURFACE}] Real-delete sweep complete: {len(to_sweep) - errors} deleted, {errors} errors"
    )
    return 0 if errors == 0 else 1


def _print_dry_run_summary(
    to_sweep: list[BranchInfo],
    stale_threshold_days: int,
    output_summary_path: str | None,
) -> None:
    lines: list[str] = [
        f"## Dry-run: stale bot-branch sweep (threshold={stale_threshold_days}d)",
        "",
        f"Found **{len(to_sweep)}** branch(es) that *would* be deleted:",
        "",
    ]
    if to_sweep:
        lines.append("| Branch | Age (days) | Open PR |")
        lines.append("|---|---|---|")
        for b in to_sweep:
            lines.append(
                f"| `{b.name}` | {b.commit_age_days:.1f} | {'yes' if b.has_open_pr else 'no'} |"
            )
    else:
        lines.append("*(none)*")

    lines.append("")
    lines.append(
        f"> Include regex: `{BRANCH_INCLUDE_REGEX.pattern}` · "
        f"Exclude blocklist: `{', '.join(sorted(BRANCH_EXCLUDE_BLOCKLIST))}`"
    )

    summary = "\n".join(lines)
    print(summary)

    # Write to GitHub step summary if GITHUB_STEP_SUMMARY is set
    import os

    step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary_path:
        Path(step_summary_path).write_text(summary + "\n", encoding="utf-8")

    if output_summary_path:
        Path(output_summary_path).write_text(summary + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Scan remote branches for stale bot-authored branches and report "
            "(dry-run) or delete (real-delete, gated) them."
        )
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=STALE_THRESHOLD_DAYS,
        help=f"Staleness threshold in days (default: {STALE_THRESHOLD_DAYS})",
    )
    dry_group = parser.add_mutually_exclusive_group()
    dry_group.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Dry-run mode: report what would be deleted without deleting (default).",
    )
    dry_group.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="Real-delete mode: actually delete stale branches.",
    )
    parser.add_argument(
        "--output-summary",
        dest="output_summary_path",
        default=None,
        help="Optional path to write the Markdown step summary.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return run_sweep(
        dry_run=args.dry_run,
        stale_threshold_days=args.stale_days,
        output_summary_path=args.output_summary_path,
    )


if __name__ == "__main__":
    sys.exit(main())
