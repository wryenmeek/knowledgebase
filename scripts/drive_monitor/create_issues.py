"""Create GitHub Issues for HITL-classified Drive drift entries.

Reads ``hitl-entries.json`` and creates (or updates) a GitHub Issue for each
entry.  Deduplicates against existing issues using a body-embedded dedupe key.

Three Issue body types:
  - ``content_changed`` / ``new_file``: content drift requiring human review.
  - ``trashed`` / ``deleted``: file removed from Drive.
  - ``out_of_scope``: file changed to an unsupported MIME type.
  - Bulk aggregated entries (``is_bulk_aggregation: True``): multiple events
    in the same parent folder combined into one Issue.

Usage::

    python -m scripts.drive_monitor.create_issues \\
        --hitl-entries hitl-entries.json

Environment variables:
    GH_TOKEN / GITHUB_TOKEN    — GitHub token for ``gh`` CLI authentication.
    GITHUB_REPOSITORY          — ``owner/repo`` slug (set by Actions).
    GITHUB_RUN_ID              — Workflow run ID (set by Actions).
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

SURFACE = "drive_monitor.create_issues"
MODE = "create"

_DEDUPE_KEY_PREFIX = "gdrive-monitor-dedupe:"


def _path_rules() -> dict[str, Any]:
    return base_path_rules(
        allowed_roots=["raw/drive-sources"],
        allowed_suffixes=[".json"],
    )


def _redact_stderr(stderr: str, max_len: int = 200) -> str:
    """Truncate and redact stderr before logging to guard against credential leakage."""
    truncated = stderr[:max_len]
    truncated = re.sub(r"[0-9a-fA-F]{40,}", "<redacted>", truncated)
    truncated = re.sub(r"ghp_[A-Za-z0-9_]+", "[REDACTED]", truncated)
    truncated = re.sub(r"github_pat_[A-Za-z0-9_]+", "[REDACTED]", truncated)
    truncated = re.sub(r"gho_[A-Za-z0-9_]+", "[REDACTED]", truncated)
    truncated = re.sub(
        r"Authorization:\s*\S+(?:\s+\S+)?", "[REDACTED]", truncated, flags=re.IGNORECASE
    )
    truncated = re.sub(r"[A-Za-z0-9+/=]{30,}", "[REDACTED]", truncated)
    return truncated.strip()


def _sanitize_gh_md(value: str, max_len: int = 200) -> str:
    """Strip characters that trigger side effects in GitHub-flavoured markdown."""
    s = value.replace("`", "").replace("\n", " ").replace("\r", "")
    s = re.sub(r"[<>]", "", s)
    s = re.sub(r"@[\w/-]+", "", s)
    s = re.sub(r"!\[", "[", s)
    s = re.sub(
        r"\b(fix(es)?|close[sd]?|resolve[sd]?)\s+#\d+",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = s.replace("${{", "[expr]").replace("}}", "[expr]")
    return s[:max_len].strip()


def _search_existing_issue(dedupe_key: str) -> int | None:
    """Search for an existing open issue containing *dedupe_key* in its body."""
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
            f"stderr: {_redact_stderr(result.stderr)}",
            flush=True,
        )
        return None
    try:
        items = json.loads(result.stdout)
        return items[0]["number"] if items else None
    except (json.JSONDecodeError, KeyError, IndexError):
        return None


def _create_issue(title: str, body: str, labels: list[str]) -> bool:
    """Create a GitHub Issue via the ``gh`` CLI.  Returns True on success."""
    cmd = [
        "gh", "issue", "create",
        "--title", title,
        "--body", body,
    ]
    for label in labels:
        cmd += ["--label", label]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(
            f"ERROR: gh issue create failed. "
            f"stderr: {_redact_stderr(result.stderr, 400)}",
            file=sys.stderr,
        )
        return False
    issue_url = result.stdout.strip()
    print(f"Created issue: {issue_url}", file=sys.stderr)
    return True


def _update_issue(issue_number: int, body_suffix: str) -> bool:
    """Append *body_suffix* to an existing issue's body via a comment."""
    result = subprocess.run(
        [
            "gh", "issue", "comment", str(issue_number),
            "--body", body_suffix,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"WARNING: Failed to add comment to issue #{issue_number}: "
            f"{_redact_stderr(result.stderr)}",
            file=sys.stderr,
        )
        return False
    return True


def _build_content_changed_body(entry: dict[str, Any], dedupe_key: str) -> str:
    """Build the GitHub Issue body for a content_changed or new_file entry."""
    alias = _sanitize_gh_md(entry.get("alias", ""), 100)
    file_id = _sanitize_gh_md(entry.get("file_id", ""), 60)
    display_name = _sanitize_gh_md(entry.get("display_name", ""), 200)
    wiki_page = _sanitize_gh_md(entry.get("wiki_page") or "(unassigned)", 200)
    event_type = entry.get("event_type", "content_changed")
    current_version = entry.get("current_drive_version")
    mime_type = _sanitize_gh_md(entry.get("mime_type", ""), 100)
    run_id = os.environ.get("GITHUB_RUN_ID", "unknown")

    lines = [
        f"## Drive source change detected — `{event_type}`",
        "",
        f"**Registry alias:** `{alias}`  ",
        f"**File:** `{display_name}` (`{file_id}`)  ",
        f"**MIME type:** `{mime_type}`  ",
        f"**Wiki page:** `{wiki_page}`  ",
    ]
    if current_version is not None:
        lines.append(f"**New Drive version:** `{current_version}`  ")

    lines += [
        "",
        "### Action required",
        "",
        "Review the updated source in Google Drive and decide whether the wiki page "
        "should be updated.  If yes, run `synthesize_diff.py` manually or approve "
        "the AFK lane for this entry.",
        "",
        "---",
        f"*Created by CI-6 Google Drive Monitor — run `{run_id}`*  ",
        f"<!-- {dedupe_key} -->",
    ]
    return "\n".join(lines)


def _build_deletion_body(entry: dict[str, Any], dedupe_key: str) -> str:
    """Build the GitHub Issue body for a trashed, deleted, or out_of_scope entry."""
    alias = _sanitize_gh_md(entry.get("alias", ""), 100)
    file_id = _sanitize_gh_md(entry.get("file_id", ""), 60)
    display_name = _sanitize_gh_md(entry.get("display_name", ""), 200)
    wiki_page = _sanitize_gh_md(entry.get("wiki_page") or "(unassigned)", 200)
    event_type = entry.get("event_type", "deleted")
    run_id = os.environ.get("GITHUB_RUN_ID", "unknown")

    action_text = {
        "trashed": (
            "The file has been moved to Trash in Google Drive.  "
            "Verify whether it was intentionally deleted or accidentally trashed.  "
            "If deleted intentionally, consider archiving the wiki page."
        ),
        "deleted": (
            "The file has been permanently deleted from Google Drive.  "
            "Decide whether to archive or remove the corresponding wiki page."
        ),
        "out_of_scope": (
            "The file's MIME type changed to an unsupported type.  "
            "Review whether the file should remain monitored or be archived."
        ),
    }.get(event_type, "Review the registry and wiki page.")

    lines = [
        f"## Drive source lifecycle event — `{event_type}`",
        "",
        f"**Registry alias:** `{alias}`  ",
        f"**File:** `{display_name}` (`{file_id}`)  ",
        f"**Wiki page:** `{wiki_page}`  ",
        "",
        "### Action required",
        "",
        action_text,
        "",
        "Update the registry `tracking_status` to `archived` once resolved.",
        "",
        "---",
        f"*Created by CI-6 Google Drive Monitor — run `{run_id}`*  ",
        f"<!-- {dedupe_key} -->",
    ]
    return "\n".join(lines)


def _build_bulk_body(entry: dict[str, Any], dedupe_key: str) -> str:
    """Build the GitHub Issue body for a bulk-aggregated HITL entry."""
    alias = _sanitize_gh_md(entry.get("alias", ""), 100)
    event_type = entry.get("event_type", "deleted")
    parent_folder_id = _sanitize_gh_md(entry.get("parent_folder_id", ""), 60)
    bulk_count = entry.get("bulk_count", 0)
    bulk_file_ids = entry.get("bulk_file_ids", [])
    run_id = os.environ.get("GITHUB_RUN_ID", "unknown")

    file_list = "\n".join(
        f"- `{_sanitize_gh_md(fid, 60)}`"
        for fid in bulk_file_ids[:20]
    )
    if len(bulk_file_ids) > 20:
        file_list += f"\n- … and {len(bulk_file_ids) - 20} more"

    lines = [
        f"## Bulk Drive lifecycle event — `{event_type}` ({bulk_count} files)",
        "",
        f"**Registry alias:** `{alias}`  ",
        f"**Parent folder:** `{parent_folder_id}`  ",
        f"**Event type:** `{event_type}`  ",
        f"**Affected files ({bulk_count}):**",
        "",
        file_list,
        "",
        "### Action required",
        "",
        "Multiple files in the same folder have experienced a lifecycle event.  "
        "Review whether this was intentional and update the registry entries and "
        "wiki pages accordingly.",
        "",
        "---",
        f"*Created by CI-6 Google Drive Monitor — run `{run_id}`*  ",
        f"<!-- {dedupe_key} -->",
    ]
    return "\n".join(lines)


def _build_issue_for_entry(
    entry: dict[str, Any],
) -> tuple[str, str, list[str]] | None:
    """Build (title, body, labels) for one HITL entry.  Returns None to skip."""
    event_type = entry.get("event_type", "")
    file_id = entry.get("file_id", "")
    alias = entry.get("alias", "")
    display_name = _sanitize_gh_md(entry.get("display_name", file_id), 80)
    is_bulk = entry.get("is_bulk_aggregation", False)

    dedupe_key = f"{_DEDUPE_KEY_PREFIX}{alias}:{file_id}:{event_type}"

    if is_bulk:
        bulk_count = entry.get("bulk_count", 0)
        parent_folder_id = _sanitize_gh_md(entry.get("parent_folder_id", ""), 40)
        title = (
            f"[Drive Monitor] Bulk {event_type}: {bulk_count} files in "
            f"folder {parent_folder_id} ({alias})"
        )
        body = _build_bulk_body(entry, dedupe_key)
        labels = ["drive-monitor", "hitl", "bulk-event"]
    elif event_type in ("content_changed", "new_file"):
        title = f"[Drive Monitor] {event_type}: {display_name} ({alias})"
        body = _build_content_changed_body(entry, dedupe_key)
        labels = ["drive-monitor", "hitl"]
    elif event_type in ("trashed", "deleted", "out_of_scope"):
        title = f"[Drive Monitor] {event_type}: {display_name} ({alias})"
        body = _build_deletion_body(entry, dedupe_key)
        labels = ["drive-monitor", "hitl", event_type]
    else:
        print(
            f"WARNING: unknown event_type {event_type!r} for {file_id!r}; skipping",
            file=sys.stderr,
        )
        return None

    return title, body, labels


def create_issues(
    hitl_entries_path: Path,
) -> SurfaceResult:
    """Create GitHub Issues for HITL-classified Drive drift entries.

    Parameters
    ----------
    hitl_entries_path:
        Path to ``hitl-entries.json`` produced by ``classify_drift.py``.

    Returns
    -------
    SurfaceResult
    """
    try:
        raw = hitl_entries_path.read_text(encoding="utf-8")
    except OSError as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_FAIL,
            reason_code="invalid_input",
            message=f"Cannot read HITL entries: {exc}",
            path_rules=_path_rules(),
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_FAIL,
            reason_code="invalid_input",
            message=f"Malformed HITL entries JSON: {exc}",
            path_rules=_path_rules(),
        )

    entries = data.get("entries", [])
    if not entries:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_PASS,
            reason_code="no_hitl_entries",
            message="No HITL entries to process.",
            path_rules=_path_rules(),
        )

    created = 0
    updated = 0
    skipped = 0
    errors = 0

    for entry in entries:
        built = _build_issue_for_entry(entry)
        if built is None:
            skipped += 1
            continue
        title, body, labels = built

        file_id = entry.get("file_id", "")
        alias = entry.get("alias", "")
        event_type = entry.get("event_type", "")
        dedupe_key = f"{_DEDUPE_KEY_PREFIX}{alias}:{file_id}:{event_type}"

        existing = _search_existing_issue(dedupe_key)
        if existing is not None:
            print(
                f"Issue #{existing} already exists for {file_id!r}; adding comment",
                file=sys.stderr,
            )
            run_id = os.environ.get("GITHUB_RUN_ID", "unknown")
            comment = (
                f"*CI-6 Drive Monitor detected this event again (run `{run_id}`). "
                f"No new issue created.*"
            )
            if _update_issue(existing, comment):
                updated += 1
            else:
                errors += 1
        else:
            if _create_issue(title, body, labels):
                created += 1
            else:
                errors += 1

    message = (
        f"Drive HITL issues: {created} created, {updated} updated, "
        f"{skipped} skipped, {errors} errors"
    )
    print(message, file=sys.stderr)

    return SurfaceResult(
        surface=SURFACE,
        mode=MODE,
        status=STATUS_PASS if errors == 0 else STATUS_FAIL,
        reason_code="ok" if errors == 0 else "issue_creation_failed",
        message=message,
        path_rules=_path_rules(),
        summary={
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
        },
    )


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Create GitHub Issues for HITL-classified Drive drift entries."
    )
    parser.add_argument(
        "--hitl-entries",
        metavar="PATH",
        required=True,
        help="Path to hitl-entries.json produced by classify_drift.",
    )
    return parser


def _args_to_kwargs(args: Any) -> dict[str, Any]:
    return {"hitl_entries_path": Path(args.hitl_entries)}


def _runner(**kwargs: Any) -> SurfaceResult:
    return create_issues(**kwargs)


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
