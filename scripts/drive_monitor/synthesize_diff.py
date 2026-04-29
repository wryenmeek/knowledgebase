"""Generate diff-based change notes for drifted Drive sources (Phase 3).

Reads the drift report produced by ``check_drift.py`` (AFK entries only),
loads the old and new vendored assets from ``raw/assets/gdrive/``, computes
a unified diff, appends a dated ``## Change Note`` section to the
corresponding wiki page, and advances ``last_applied_*`` in the source
registry only after the wiki write is confirmed.

Lock ordering (ADR-021): acquires ``wiki/.kb_write.lock`` FIRST, then
``raw/.drive-sources.lock`` inside that context.

Usage::

    python -m scripts.drive_monitor.synthesize_diff \\
        --drift-report afk-entries.json \\
        --approval approved \\
        [--repo-root /path/to/repo]

Requires ``--approval approved`` for any write operation.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from scripts._optional_surface_common import (
    APPROVAL_APPROVED,
    APPROVAL_NONE,
    STATUS_FAIL,
    STATUS_PASS,
    JsonArgumentParser,
    SurfaceResult,
    approval_required_result,
    base_path_rules,
    invalid_input_result,
    looks_like_repo_root,
    repo_root_failure,
    run_surface_cli,
)
from scripts.kb.contracts import DriveMonitorReasonCode
from scripts.kb import write_utils
from scripts.drive_monitor._types import (
    MIME_EXTENSION_MAP,
    MIME_EXPORT_MAP,
    OVERSIZE_LIMIT_BYTES,
    validate_drive_drift_report,
)
from scripts.drive_monitor._validators import (
    build_drive_asset_path,
    build_wiki_page_path,
    validate_file_id,
)
from scripts.drive_monitor._registry import (
    find_registry_by_alias,
    update_last_applied,
)

SURFACE = "drive_monitor.synthesize_diff"
MODE = "synthesize"

_DIFF_SIZE_LIMIT = 100_000
_DIFF_MAX_LINES = 200


def _write_wiki_page(path: Path, content: str) -> None:
    """Write content to a wiki page (extracted for testability)."""
    path.write_text(content, encoding="utf-8")


def _path_rules() -> dict[str, Any]:
    return base_path_rules(
        allowed_roots=["wiki", "raw/drive-sources"],
        allowed_suffixes=[".md", ".json"],
    )


def _is_binary(data: bytes) -> bool:
    return b"\x00" in data


def _render_diff(
    old_text: str,
    new_text: str,
    old_label: str,
    new_label: str,
) -> str:
    """Produce a unified diff string for embedding in a wiki change note."""
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{old_label}",
            tofile=f"b/{new_label}",
            lineterm="",
        )
    )
    if not diff_lines:
        return "(no textual changes detected)"
    if len(diff_lines) > _DIFF_MAX_LINES:
        truncated = diff_lines[:_DIFF_MAX_LINES]
        truncated.append(
            f"\n… diff truncated at {_DIFF_MAX_LINES} lines "
            f"({len(diff_lines) - _DIFF_MAX_LINES} lines omitted) …\n"
        )
        return "".join(truncated)
    return "".join(diff_lines)


def _find_old_asset(
    repo_root: Path,
    alias: str,
    file_id: str,
    last_applied_version: int | None,
    last_applied_md5: str | None,
    display_name: str,
    mime_type: str,
) -> bytes | None:
    """Locate the previously applied asset in raw/assets/gdrive/."""
    import re as _re
    safe_name_base = _re.sub(r"[^\w\-. ]+", "_", display_name).strip().rstrip(".")[:200]
    ext = MIME_EXTENSION_MAP.get(mime_type, "")
    if ext and not safe_name_base.lower().endswith(ext):
        safe_name = safe_name_base + ext
    else:
        safe_name = safe_name_base

    if last_applied_version is not None:
        version_segment = str(last_applied_version)
    elif last_applied_md5:
        version_segment = last_applied_md5
    else:
        return None

    try:
        asset_path = build_drive_asset_path(
            repo_root, alias, file_id, version_segment, safe_name
        )
        if asset_path.exists():
            return asset_path.read_bytes()
    except (ValueError, OSError):
        pass
    return None


def _find_new_asset(
    repo_root: Path,
    alias: str,
    file_id: str,
    current_version: int | None,
    current_md5: str | None,
    display_name: str,
    mime_type: str,
) -> bytes | None:
    """Locate the newly fetched asset in raw/assets/gdrive/."""
    import re as _re
    safe_name_base = _re.sub(r"[^\w\-. ]+", "_", display_name).strip().rstrip(".")[:200]
    ext = MIME_EXTENSION_MAP.get(mime_type, "")
    if ext and not safe_name_base.lower().endswith(ext):
        safe_name = safe_name_base + ext
    else:
        safe_name = safe_name_base

    if current_version is not None:
        version_segment = str(current_version)
    elif current_md5:
        version_segment = current_md5
    else:
        return None

    try:
        asset_path = build_drive_asset_path(
            repo_root, alias, file_id, version_segment, safe_name
        )
        if asset_path.exists():
            return asset_path.read_bytes()
    except (ValueError, OSError):
        pass
    return None


def _build_change_note(
    entry: dict[str, Any],
    old_bytes: bytes | None,
    new_bytes: bytes | None,
) -> str:
    """Build a Markdown change note section for the wiki page."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    file_id = entry.get("file_id", "")
    display_name = entry.get("display_name", file_id)
    mime_type = entry.get("mime_type", "")
    event_type = entry.get("event_type", "content_changed")
    current_version = entry.get("current_drive_version")
    lines: list[str] = [
        f"\n## Change Note — {now}\n",
        f"\n**Source:** Google Drive `{display_name}` (`{file_id}`)\\\n",
        f"**Event:** `{event_type}`\\\n",
    ]
    if current_version is not None:
        lines.append(f"**Drive version:** {current_version}\\\n")
    current_md5 = entry.get("current_md5_checksum")
    if current_md5:
        lines.append(f"**MD5:** `{current_md5}`\\\n")

    if old_bytes is None:
        lines.append("\n*No previous version available — initial ingest.*\n")
    elif new_bytes is None:
        lines.append("\n*New version asset not yet fetched.*\n")
    elif _is_binary(new_bytes):
        lines.append(
            f"\n*Binary file ({len(new_bytes)} bytes) — diff not shown.*\n"
        )
    elif len(new_bytes) > _DIFF_SIZE_LIMIT:
        lines.append(
            f"\n*File too large ({len(new_bytes)} bytes) for inline diff.*\n"
        )
    else:
        try:
            old_text = old_bytes.decode("utf-8", errors="replace")
            new_text = new_bytes.decode("utf-8", errors="replace")
            diff = _render_diff(
                old_text, new_text,
                old_label=f"{display_name} (prev)",
                new_label=f"{display_name} (new)",
            )
            lines.append("\n```diff\n")
            lines.append(diff)
            lines.append("\n```\n")
        except Exception as exc:
            lines.append(f"\n*Diff rendering failed: {exc}*\n")

    return "".join(lines)


def synthesize_diff(
    *,
    repo_root: Path,
    drift_report_path: Path,
    approval: str = APPROVAL_NONE,
) -> SurfaceResult:
    """Apply diff-aware wiki updates for AFK-classified Drive entries.

    Parameters
    ----------
    repo_root:
        Absolute path to the knowledgebase repository root.
    drift_report_path:
        Path to the AFK drift entries JSON (output of classify_drift.py).
    approval:
        Must be ``"approved"`` for any writes to occur.
    """
    if approval != APPROVAL_APPROVED:
        return approval_required_result(surface=SURFACE, mode=MODE, path_rules=_path_rules(), lock_required=True)

    if not looks_like_repo_root(repo_root):
        return repo_root_failure(surface=SURFACE, mode=MODE, approval=approval, path_rules=_path_rules())

    try:
        raw = drift_report_path.read_text(encoding="utf-8")
    except OSError as exc:
        return invalid_input_result(
            surface=SURFACE, mode=MODE, approval=approval,
            path_rules=_path_rules(),
            message=f"Cannot read drift report: {exc}",
        )

    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        return invalid_input_result(
            surface=SURFACE, mode=MODE, approval=approval,
            path_rules=_path_rules(),
            message=f"Malformed JSON: {exc}",
        )

    # Accept either a full drift report or a classify_drift afk output
    if "entries" in report:
        entries = report["entries"]
    elif "drifted" in report:
        entries = report["drifted"]
    else:
        entries = []

    entries = [
        e for e in entries
        if e.get("event_type") in ("content_changed", "new_file")
    ]

    if not entries:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_PASS,
            reason_code=str(DriveMonitorReasonCode.NO_DRIFT),
            message="No synthesizable entries.",
            path_rules=_path_rules(),
        )

    success_count = 0
    error_count = 0
    errors: list[dict[str, Any]] = []

    for entry in entries:
        file_id = entry.get("file_id", "")
        alias = entry.get("alias", "")
        wiki_page = entry.get("wiki_page")
        display_name = entry.get("display_name", file_id)
        mime_type = entry.get("mime_type", "")
        is_native = mime_type in MIME_EXPORT_MAP

        if not wiki_page:
            errors.append({
                "file_id": file_id,
                "reason": "wiki_page is null; cannot synthesize without target page",
            })
            error_count += 1
            continue

        try:
            wiki_path = build_wiki_page_path(repo_root, wiki_page)
        except ValueError as exc:
            errors.append({"file_id": file_id, "reason": str(exc)})
            error_count += 1
            continue

        registry_path = find_registry_by_alias(repo_root, alias)
        if not registry_path:
            errors.append({
                "file_id": file_id,
                "reason": f"No registry found for alias {alias!r}",
            })
            error_count += 1
            continue

        # Locate old and new assets
        old_bytes = _find_old_asset(
            repo_root, alias, file_id,
            entry.get("last_applied_drive_version"),
            entry.get("md5_checksum_at_last_applied"),
            display_name, mime_type,
        )
        new_bytes = _find_new_asset(
            repo_root, alias, file_id,
            entry.get("current_drive_version"),
            entry.get("current_md5_checksum"),
            display_name, mime_type,
        )

        if new_bytes is None:
            errors.append({
                "file_id": file_id,
                "reason": "New asset not found in raw/assets/gdrive/ — run fetch_content first",
            })
            error_count += 1
            continue

        change_note = _build_change_note(entry, old_bytes, new_bytes)

        # Acquire wiki lock FIRST, then drive-sources lock inside
        try:
            with write_utils.exclusive_write_lock(repo_root):
                # Capture original content for compensating rollback
                wiki_path.parent.mkdir(parents=True, exist_ok=True)
                original_existed = wiki_path.exists()
                original_content = (
                    wiki_path.read_text(encoding="utf-8")
                    if original_existed
                    else None
                )

                # Append change note to wiki page
                if original_content is not None:
                    new_content = original_content.rstrip() + "\n" + change_note
                else:
                    # New wiki page — create a minimal page
                    safe_title = json.dumps(display_name)
                    new_content = (
                        f"---\ntitle: {safe_title}\nsource_type: google_drive\n"
                        f"alias: {alias}\nfile_id: {file_id}\n---\n"
                        f"# {display_name}\n\n"
                        f"*Auto-created by CI-6 Drive monitor.*\n"
                        + change_note
                    )
                _write_wiki_page(wiki_path, new_content)

                # Wiki write confirmed — now advance last_applied_*
                current_version = entry.get("current_drive_version")
                current_md5 = entry.get("current_md5_checksum")
                sha256_hex = hashlib.sha256(new_bytes).hexdigest()

                try:
                    update_last_applied(
                        repo_root,
                        registry_path,
                        file_id,
                        drive_version=int(current_version) if current_version is not None else None,
                        md5_checksum=current_md5,
                        sha256=sha256_hex,
                    )
                except OSError as reg_exc:
                    # Registry update failed — compensating rollback
                    try:
                        if original_content is not None:
                            _write_wiki_page(wiki_path, original_content)
                        elif wiki_path.exists():
                            wiki_path.unlink()
                    except OSError as rollback_exc:
                        errors.append({
                            "file_id": file_id,
                            "reason": (
                                f"Registry update failed: {reg_exc}; "
                                f"rollback also failed: {rollback_exc}"
                            ),
                        })
                        error_count += 1
                        continue
                    errors.append({
                        "file_id": file_id,
                        "reason": (
                            f"Registry update failed (wiki rolled back): {reg_exc}"
                        ),
                    })
                    error_count += 1
                    continue

                success_count += 1

        except OSError as exc:
            errors.append({"file_id": file_id, "reason": f"Write failed: {exc}"})
            error_count += 1

    message = (
        f"Drive synthesize: {success_count} synthesized, "
        f"{error_count} errors (of {len(entries)} entries)"
    )
    print(message, file=sys.stderr)
    if errors:
        for e in errors:
            print(f"  ERROR [{e.get('file_id','?')}]: {e.get('reason','?')}", file=sys.stderr)

    status = STATUS_PASS if error_count == 0 else STATUS_FAIL
    return SurfaceResult(
        surface=SURFACE,
        mode=MODE,
        status=status,
        reason_code=str(
            DriveMonitorReasonCode.DRIFT_DETECTED if success_count > 0
            else DriveMonitorReasonCode.FETCH_FAILED
        ),
        message=message,
        path_rules=_path_rules(),
        summary={
            "success_count": success_count,
            "error_count": error_count,
        },
    )


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Apply diff-aware wiki updates for AFK-classified Drive entries."
    )
    parser.add_argument(
        "--drift-report",
        metavar="PATH",
        required=True,
        help="Path to the AFK entries JSON (output of classify_drift.py).",
    )
    parser.add_argument(
        "--repo-root",
        metavar="PATH",
        default=".",
        help="Repository root directory (default: current directory).",
    )
    parser.add_argument(
        "--approval",
        metavar="APPROVAL",
        default=APPROVAL_NONE,
        help="Must be 'approved' to perform writes.",
    )
    return parser


def _args_to_kwargs(args: Any) -> dict[str, Any]:
    return {
        "repo_root": Path(args.repo_root).resolve(),
        "drift_report_path": Path(args.drift_report),
        "approval": args.approval,
    }


def _runner(**kwargs: Any) -> SurfaceResult:
    return synthesize_diff(**kwargs)


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
