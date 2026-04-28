"""Classify drifted Drive entries as HITL or AFK (Phase 2.5 — read-only).

Reads the drift report produced by ``check_drift.py`` and classifies every
drifted entry as either AFK (automatable) or HITL (requires human review).
Outputs ``afk-entries.json`` and ``hitl-entries.json`` as transient CI
artifacts, and optionally sets GitHub Actions step outputs.

AFK is **deny-by-default**: the ``--afk-max-lines`` threshold defaults to 0,
routing all entries to HITL.  AFK routing is only enabled when the operator
explicitly passes a positive threshold AND the entry meets ALL eligibility
criteria (content_changed, native Doc MIME type, tracking_status active,
change below threshold).

Usage::

    python -m scripts.drive_monitor.classify_drift \\
        --drift-report drift-report.json \\
        [--output-dir .] \\
        [--afk-max-lines 0] \\
        [--bulk-hitl-threshold 3]
"""

from __future__ import annotations

import json
import os
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
from scripts.drive_monitor._types import MIME_EXPORT_MAP

SURFACE = "drive_monitor.classify_drift"
MODE = "classify"

# MIME types that are eligible for AFK (native Docs → Markdown export only).
_AFK_ELIGIBLE_MIME_TYPES: frozenset[str] = frozenset({
    "application/vnd.google-apps.document",
})


def _path_rules() -> dict[str, Any]:
    return base_path_rules(
        allowed_roots=["raw/drive-sources"],
        allowed_suffixes=[".json"],
    )


def _write_github_output(has_afk: bool, has_hitl: bool) -> None:
    """Write step outputs to ``$GITHUB_OUTPUT`` if running inside Actions."""
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if not gh_output:
        return
    with open(gh_output, "a") as fh:
        fh.write(f"has_afk={'true' if has_afk else 'false'}\n")
        fh.write(f"has_hitl={'true' if has_hitl else 'false'}\n")


def _is_afk_eligible(entry: dict[str, Any], afk_max_lines: int) -> bool:
    """Return True if *entry* qualifies for AFK classification.

    AFK requires ALL of:
    - ``afk_max_lines > 0`` (0 = deny-by-default).
    - ``event_type == "content_changed"`` (not a new file, deletion, or scope loss).
    - ``tracking_status == "active"``.
    - ``mime_type`` is a native Google Doc (→ Markdown export).
    - ``lines_added`` and ``lines_removed`` both non-None.
    - Total changed lines ``<= afk_max_lines``.
    """
    if afk_max_lines <= 0:
        return False
    if entry.get("event_type") != "content_changed":
        return False
    if entry.get("tracking_status") != "active":
        return False
    if entry.get("mime_type") not in _AFK_ELIGIBLE_MIME_TYPES:
        return False
    lines_added = entry.get("lines_added")
    lines_removed = entry.get("lines_removed")
    if lines_added is None or lines_removed is None:
        return False
    return (lines_added + lines_removed) <= afk_max_lines


def _aggregate_bulk_hitl(
    entries: list[dict[str, Any]],
    bulk_threshold: int,
) -> list[dict[str, Any]]:
    """Aggregate bulk deletion/scope-loss events by parent folder.

    When ``>= bulk_threshold`` entries with the same ``parent_folder_id``
    share the same lifecycle event type (trashed / deleted / out_of_scope),
    they are replaced with a single aggregated entry.

    Returns the modified list of HITL entries.
    """
    if bulk_threshold <= 1:
        return entries

    # Group deletion-like events by (event_type, parent_folder_id)
    bulk_event_types = {"trashed", "deleted", "out_of_scope"}
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    non_bulk: list[dict[str, Any]] = []

    for entry in entries:
        event_type = entry.get("event_type", "")
        parent_id = entry.get("parent_folder_id") or ""
        if event_type in bulk_event_types and parent_id:
            key = (event_type, parent_id)
            buckets.setdefault(key, []).append(entry)
        else:
            non_bulk.append(entry)

    result = list(non_bulk)
    for (event_type, parent_id), group in buckets.items():
        if len(group) >= bulk_threshold:
            # Emit one aggregated entry
            result.append({
                "alias": group[0].get("alias", ""),
                "file_id": f"__bulk_{event_type}_{parent_id}__",
                "display_name": (
                    f"[{len(group)} files] bulk {event_type} in folder {parent_id}"
                ),
                "display_path": f"<folder:{parent_id}>",
                "mime_type": "",
                "event_type": event_type,
                "tracking_status": "active",
                "wiki_page": None,
                "is_bulk_aggregation": True,
                "bulk_count": len(group),
                "bulk_file_ids": [e["file_id"] for e in group],
                "parent_folder_id": parent_id,
                "lines_added": None,
                "lines_removed": None,
                "is_binary": None,
                "file_size_bytes": None,
            })
        else:
            result.extend(group)

    return result


def classify_drift(
    drift_report_path: Path,
    output_dir: Path,
    afk_max_lines: int = 0,
    bulk_hitl_threshold: int = 3,
) -> SurfaceResult:
    """Classify drifted Drive entries from a drift report as HITL or AFK.

    Returns a ``SurfaceResult`` with the classification summary.
    """
    try:
        raw = drift_report_path.read_text(encoding="utf-8")
    except OSError as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
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
            mode=MODE,
            status=STATUS_FAIL,
            reason_code="invalid_input",
            message=f"Malformed drift report JSON: {exc}",
            path_rules=_path_rules(),
        )

    drifted = report.get("drifted", [])

    afk_entries: list[dict[str, Any]] = []
    hitl_entries: list[dict[str, Any]] = []

    for entry in drifted:
        if _is_afk_eligible(entry, afk_max_lines):
            afk_entries.append(entry)
        else:
            hitl_entries.append(entry)

    # Aggregate bulk HITL events
    hitl_entries = _aggregate_bulk_hitl(hitl_entries, bulk_hitl_threshold)

    has_afk = len(afk_entries) > 0
    has_hitl = len(hitl_entries) > 0

    _write_github_output(has_afk, has_hitl)

    output_dir.mkdir(parents=True, exist_ok=True)
    afk_path = output_dir / "afk-entries.json"
    hitl_path = output_dir / "hitl-entries.json"
    afk_path.write_text(json.dumps({"entries": afk_entries}, indent=2), encoding="utf-8")
    hitl_path.write_text(json.dumps({"entries": hitl_entries}, indent=2), encoding="utf-8")

    message = f"Drive classification: {len(afk_entries)} AFK, {len(hitl_entries)} HITL"
    print(message, file=sys.stderr)

    return SurfaceResult(
        surface=SURFACE,
        mode=MODE,
        status=STATUS_PASS,
        reason_code="ok",
        message=message,
        path_rules=_path_rules(),
        summary={
            "afk_count": len(afk_entries),
            "hitl_count": len(hitl_entries),
            "has_afk": has_afk,
            "has_hitl": has_hitl,
        },
    )


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Classify drifted Drive entries as HITL or AFK."
    )
    parser.add_argument(
        "--drift-report",
        metavar="PATH",
        required=True,
        help="Path to the drift report JSON produced by check_drift.",
    )
    parser.add_argument(
        "--output-dir",
        metavar="PATH",
        default=".",
        help=(
            "Directory to write afk-entries.json and hitl-entries.json "
            "(default: current directory)."
        ),
    )
    parser.add_argument(
        "--afk-max-lines",
        metavar="N",
        type=int,
        default=0,
        help=(
            "Max total changed lines for AFK eligibility "
            "(default: 0 = deny-by-default, all HITL)."
        ),
    )
    parser.add_argument(
        "--bulk-hitl-threshold",
        metavar="N",
        type=int,
        default=3,
        help=(
            "Aggregate >= N deletion/scope-loss events in the same parent folder "
            "into a single HITL Issue (default: 3)."
        ),
    )
    return parser


def _args_to_kwargs(args: Any) -> dict[str, Any]:
    return {
        "drift_report_path": Path(args.drift_report),
        "output_dir": Path(args.output_dir),
        "afk_max_lines": args.afk_max_lines,
        "bulk_hitl_threshold": args.bulk_hitl_threshold,
    }


def _runner(**kwargs: Any) -> SurfaceResult:
    return classify_drift(**kwargs)


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
