"""Create GitHub Issues for HITL-classified drift entries.

Reads ``hitl-entries.json`` and creates (or updates) a GitHub Issue for each
entry.  Deduplicates against existing issues using a body-embedded dedupe key.

Usage::

    python -m scripts.github_monitor.create_issues \\
        --hitl-entries hitl-entries.json

Environment variables:
    GH_TOKEN / GITHUB_TOKEN   — GitHub token for ``gh`` CLI authentication.
    GITHUB_REPOSITORY          — ``owner/repo`` slug (set automatically by Actions).
    GITHUB_RUN_ID              — Workflow run ID (set automatically by Actions).

This module has side effects (issue creation via the ``gh`` CLI).  It follows
the ``SurfaceResult`` pattern for structured output but exits non-zero if any
issue creation fails.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

from scripts._optional_surface_common import (
    STATUS_FAIL,
    STATUS_PASS,
    JsonArgumentParser,
    SurfaceResult,
    base_path_rules,
    run_surface_cli,
)

SURFACE = "github_monitor.create_issues"
MODE = "create"


def _path_rules() -> dict[str, Any]:
    return base_path_rules(
        allowed_roots=["raw/github-sources"],
        allowed_suffixes=[".json"],
    )


def _sanitize_gh_md(value: str, max_len: int = 200) -> str:
    """Strip characters that trigger side effects in GitHub-flavoured markdown."""
    s = value.replace("`", "").replace("\n", " ").replace("\r", "")
    s = re.sub(r"[<>]", "", s)                                     # HTML tags
    s = re.sub(r"@[\w/-]+", "", s)                                  # @mention / @org/team
    s = re.sub(r"!\[", "[", s)                                      # image embeds
    s = re.sub(
        r"\b(fix(es)?|close[sd]?|resolve[sd]?)\s+#\d+",
        "",
        s,
        flags=re.IGNORECASE,
    )
    return s[:max_len].strip()


def _search_existing_issue(dedupe_key: str) -> int | None:
    """Search for an existing issue containing *dedupe_key* in its body.

    Returns the issue number if found, or ``None``.
    """
    result = subprocess.run(
        [
            "gh", "issue", "list",
            "--search", f'"{dedupe_key}" in:body',
            "--json", "number",
            "--limit", "1",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"::warning::Dedupe search failed; creating issue anyway. "
            f"stderr: {result.stderr}",
            flush=True,
        )
        return None
    try:
        existing = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(
            "::warning::Dedupe search returned unparseable JSON; creating issue anyway.",
            flush=True,
        )
        return None
    if existing and "number" in existing[0]:
        return existing[0]["number"]
    return None


def _comment_on_issue(issue_num: int, run_id: str) -> bool:
    """Add a comment to an existing issue. Returns ``True`` on success."""
    result = subprocess.run(
        [
            "gh", "issue", "comment", str(issue_num),
            "--body", f"Updated drift detected in run {run_id}.",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"::warning::Failed to comment on issue #{issue_num}: {result.stderr}",
            flush=True,
        )
        return False
    return True


def _create_issue(title: str, body: str, labels: str) -> bool:
    """Create a new GitHub Issue. Returns ``True`` on success."""
    result = subprocess.run(
        [
            "gh", "issue", "create",
            "--title", title,
            "--body", body,
            "--label", labels,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"::error::Failed to create HITL issue: {result.stderr}",
            flush=True,
        )
        return False
    return True


def _close_issue(issue_num: int, run_id: str) -> bool:
    """Close an issue with a resolution comment. Returns ``True`` on success."""
    comment_result = subprocess.run(
        [
            "gh", "issue", "comment", str(issue_num),
            "--body", f"Resolved: applied in run {run_id}.",
        ],
        capture_output=True,
        text=True,
    )
    if comment_result.returncode != 0:
        print(
            f"::warning::Failed to comment on issue #{issue_num} before closing: "
            f"{comment_result.stderr}",
            flush=True,
        )

    close_result = subprocess.run(
        ["gh", "issue", "close", str(issue_num)],
        capture_output=True,
        text=True,
    )
    if close_result.returncode != 0:
        print(
            f"::warning::Failed to close issue #{issue_num}: {close_result.stderr}",
            flush=True,
        )
        return False
    return True


def process_hitl_entries(hitl_entries_path: Path) -> SurfaceResult:
    """Create or update GitHub Issues for every HITL entry."""
    try:
        raw = hitl_entries_path.read_text(encoding="utf-8")
    except OSError as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_FAIL,
            reason_code="invalid_input",
            message=f"Cannot read HITL entries file: {exc}",
            path_rules=_path_rules(),
        )

    try:
        hitl = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_FAIL,
            reason_code="invalid_input",
            message=f"Malformed HITL entries JSON: {exc}",
            path_rules=_path_rules(),
        )

    entries = hitl.get("entries", [])
    if not entries:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_PASS,
            reason_code="ok",
            message="No HITL entries to process.",
            path_rules=_path_rules(),
        )

    run_id = os.environ.get("GITHUB_RUN_ID", "unknown")
    created = 0
    updated = 0
    failed = 0

    for entry in entries:
        registry = f"{entry.get('owner', 'unknown')}/{entry.get('repo', 'unknown')}"
        source_key = entry.get("path", "unknown")
        dedupe_key = f"ci5-drift:{registry}:{source_key}"

        safe_dedupe_key = _sanitize_gh_md(dedupe_key.replace('"', ""))
        safe_key = _sanitize_gh_md(source_key, max_len=120).replace("[", "").replace("]", "")
        safe_registry = _sanitize_gh_md(registry)
        safe_body_source = _sanitize_gh_md(source_key)
        safe_body_dedupe = _sanitize_gh_md(dedupe_key)
        title = f"[CI-5 HITL] Drift detected: {safe_key}"

        existing_num = _search_existing_issue(safe_dedupe_key)
        if existing_num is not None:
            if _comment_on_issue(existing_num, run_id):
                print(f"Updated existing issue #{existing_num} for {source_key}")
                updated += 1
            else:
                failed += 1
        else:
            body = (
                f"## CI-5 HITL Drift Alert\n\n"
                f"**Registry:** `{safe_registry}`\n"
                f"**Source:** `{safe_body_source}`\n"
                f"**Classification:** HITL (requires human review per ADR-014)\n\n"
                f"### Recommended action\n"
                f"1. Review the fetched asset in `raw/assets/`\n"
                f"2. Assess whether the wiki page update requires editorial judgment\n"
                f"3. Run `synthesize_diff.py` manually after review\n\n"
                f"---\n"
                f"_Dedupe key: `{safe_body_dedupe}`_\n"
                f"_Auto-generated by CI-5 GitHub Source Monitor (run {run_id})_\n"
            )
            if _create_issue(title, body, "wiki-change,hitl"):
                print(f"Created new HITL issue for {source_key}")
                created += 1
            else:
                failed += 1

    message = f"Issues: {created} created, {updated} updated, {failed} failed"
    status = STATUS_FAIL if failed > 0 else STATUS_PASS

    return SurfaceResult(
        surface=SURFACE,
        mode=MODE,
        status=status,
        reason_code="ok" if failed == 0 else "issue_creation_failed",
        message=message,
        path_rules=_path_rules(),
        summary={
            "created": created,
            "updated": updated,
            "failed": failed,
        },
    )

def close_resolved_entries(drift_report_path: Path) -> SurfaceResult:
    """Close GitHub Issues for entries that are now up-to-date.

    An entry is "resolved" when it appears in the drift report's
    ``up_to_date`` list, meaning ``last_applied_blob_sha`` matches the
    current remote blob SHA.
    """
    try:
        raw = drift_report_path.read_text(encoding="utf-8")
    except OSError as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode="close",
            status=STATUS_FAIL,
            reason_code="invalid_input",
            message=f"Cannot read drift report: {exc}",
            path_rules=_path_rules(),
        )

    try:
        report = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode="close",
            status=STATUS_FAIL,
            reason_code="invalid_input",
            message=f"Malformed drift report JSON: {exc}",
            path_rules=_path_rules(),
        )

    up_to_date = report.get("up_to_date", [])
    if not up_to_date:
        return SurfaceResult(
            surface=SURFACE,
            mode="close",
            status=STATUS_PASS,
            reason_code="ok",
            message="No up-to-date entries to close.",
            path_rules=_path_rules(),
        )

    run_id = os.environ.get("GITHUB_RUN_ID", "unknown")
    closed = 0
    not_found = 0
    failed = 0

    for entry in up_to_date:
        registry = f"{entry.get('owner', 'unknown')}/{entry.get('repo', 'unknown')}"
        source_key = entry.get("path", "unknown")
        dedupe_key = f"ci5-drift:{registry}:{source_key}"
        safe_dedupe_key = _sanitize_gh_md(dedupe_key.replace('"', ""))

        existing_num = _search_existing_issue(safe_dedupe_key)
        if existing_num is None:
            not_found += 1
            continue

        if _close_issue(existing_num, run_id):
            print(f"Closed resolved issue #{existing_num} for {source_key}")
            closed += 1
        else:
            failed += 1

    message = f"Close-resolved: {closed} closed, {not_found} no issue found, {failed} failed"
    return SurfaceResult(
        surface=SURFACE,
        mode="close",
        status=STATUS_PASS if failed == 0 else STATUS_FAIL,
        reason_code="ok" if failed == 0 else "close_failed",
        message=message,
        path_rules=_path_rules(),
        summary={
            "closed": closed,
            "not_found": not_found,
            "failed": failed,
        },
    )


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Create GitHub Issues for HITL-classified drift entries."
    )
    parser.add_argument(
        "--hitl-entries",
        metavar="PATH",
        required=True,
        help="Path to hitl-entries.json produced by classify_drift.",
    )
    parser.add_argument(
        "--close-resolved",
        action="store_true",
        default=False,
        help="Close issues for entries that are now up-to-date.",
    )
    parser.add_argument(
        "--drift-report",
        metavar="PATH",
        help="Path to drift-report.json (required when --close-resolved is set).",
    )
    return parser


def _args_to_kwargs(args: Any) -> dict[str, Any]:
    if args.close_resolved and not args.drift_report:
        raise ValueError("--close-resolved requires --drift-report")
    return {
        "hitl_entries_path": Path(args.hitl_entries),
        "close_resolved": args.close_resolved,
        "drift_report_path": Path(args.drift_report) if args.drift_report else None,
    }


def _runner(**kwargs: Any) -> SurfaceResult:
    result = process_hitl_entries(
        hitl_entries_path=kwargs["hitl_entries_path"],
    )

    if kwargs.get("close_resolved") and kwargs.get("drift_report_path"):
        close_result = close_resolved_entries(
            drift_report_path=kwargs["drift_report_path"],
        )
        if close_result.status == STATUS_FAIL:
            return close_result
        # Merge summaries
        combined_summary = {**(result.summary or {}), "close_resolved": close_result.summary}
        result = SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=result.status,
            reason_code=result.reason_code,
            message=f"{result.message}; {close_result.message}",
            path_rules=result.path_rules,
            summary=combined_summary,
        )

    return result


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    output_stream: Any = sys.stdout,
) -> int:
    return run_surface_cli(
        argv=argv,
        parser_factory=_build_parser,
        path_rules_factory=_path_rules,
        surface=SURFACE,
        runner=_runner,
        args_to_kwargs=_args_to_kwargs,
        output_stream=output_stream,
    )


if __name__ == "__main__":
    sys.exit(run_cli())
