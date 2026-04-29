"""Drift detection for monitored Google Drive sources (Phase 1 — read-only).

Reads every active folder_entry from ``*.source-registry.json`` files under
``raw/drive-sources/``, queries the Drive Changes API for changed file IDs,
resolves new files via parent-chain lookup, and compares drive_version
(native) or md5Checksum (non-native) against registry values.

Produces a structured drift report (``--output drift-report.json``) that
downstream scripts consume.  This surface performs **no repository writes**
— it is read-only.  The Changes API cursor is NOT advanced in this script;
cursor advancement happens only after a successful write by fetch_content.py.

Usage::

    python -m scripts.drive_monitor.check_drift \\
        [--registry raw/drive-sources/alias.source-registry.json] \\
        [--repo-root /path/to/repo] \\
        [--output drift-report.json]

Authentication:
    Set ``GDRIVE_SA_KEY`` (service account JSON key content) in the
    environment.  Never accepted as a CLI argument.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from scripts._optional_surface_common import (
    STATUS_FAIL,
    STATUS_PASS,
    JsonArgumentParser,
    SurfaceResult,
    base_path_rules,
    invalid_input_result,
    looks_like_repo_root,
    repo_root_failure,
    run_surface_cli,
)
from scripts.kb.contracts import DriveMonitorReasonCode
from scripts.drive_monitor._types import (
    DRIFT_REPORT_VERSION,
    DRIVE_MIME_ALLOWLIST,
    MIME_EXPORT_MAP,
    DriveDriftedEntry,
    DriveUpToDateEntry,
    DriveUninitializedEntry,
    DriveErrorEntry,
    validate_drive_registry_file,
)
from scripts.drive_monitor._http import (
    build_drive_client,
    get_changes_start_page_token,
    list_changes,
    get_file_parents,
    DriveAPIRequestError,
    DriveAPIResponseError,
)
from scripts.drive_monitor._registry import find_registry_files
from scripts.drive_monitor._validators import validate_file_id

SURFACE = "drive_monitor.check_drift"
MODE = "check"


def _path_rules() -> dict[str, Any]:
    return base_path_rules(
        allowed_roots=["raw/drive-sources"],
        allowed_suffixes=[".json"],
    )


def _is_binary(data: bytes) -> bool:
    return b"\x00" in data


def _resolve_parent_folder(
    drive: Any,
    file_id: str,
    registered_folder_ids: set[str],
    *,
    max_depth: int = 10,
) -> str | None:
    """Walk the parent chain of *file_id* to find a registered folder.

    Returns the matching registered ``folder_id``, or ``None`` if no
    registered folder is found within *max_depth* hops.
    """
    current_id = file_id
    for _ in range(max_depth):
        parents = get_file_parents(drive, current_id)
        if not parents:
            return None
        for parent_id in parents:
            if parent_id in registered_folder_ids:
                return parent_id
            current_id = parent_id
    return None


def _check_single_registry(
    registry_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    """Run drift detection for one registry file.

    Returns a partial dict with keys: ``drifted``, ``up_to_date``,
    ``uninitialized``, ``errors``, ``has_drift``, ``registry``.
    """
    drifted: list[dict[str, Any]] = []
    up_to_date: list[dict[str, Any]] = []
    uninitialized: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
        registry = validate_drive_registry_file(raw)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        errors.append({
            "alias": str(registry_path.stem),
            "file_id": "",
            "reason_code": str(DriveMonitorReasonCode.FETCH_FAILED),
            "message": f"Failed to read/validate registry: {exc}",
        })
        return {
            "registry": str(registry_path.relative_to(repo_root)),
            "alias": str(registry_path.stem),
            "new_page_token": None,
            "drifted": drifted,
            "up_to_date": up_to_date,
            "uninitialized": uninitialized,
            "errors": errors,
            "has_drift": False,
        }

    alias = registry["alias"]
    credential_secret = registry.get("credential_secret_name") or "GDRIVE_SA_KEY"

    # Build Drive client
    try:
        drive = build_drive_client(credential_secret)
    except DriveAPIRequestError as exc:
        errors.append({
            "alias": alias,
            "file_id": "",
            "reason_code": str(DriveMonitorReasonCode.AUTH_FAILED),
            "message": str(exc),
        })
        return {
            "registry": str(registry_path.relative_to(repo_root)),
            "alias": alias,
            "new_page_token": None,
            "drifted": drifted,
            "up_to_date": up_to_date,
            "uninitialized": uninitialized,
            "errors": errors,
            "has_drift": False,
        }

    # Active folder IDs for parent-chain resolution
    active_folder_ids: set[str] = {
        fe["folder_id"]
        for fe in registry.get("folder_entries", [])
        if fe.get("tracking_status") == "active"
    }
    # folder_id → wiki_namespace mapping
    folder_namespace: dict[str, str] = {
        fe["folder_id"]: fe.get("wiki_namespace", "")
        for fe in registry.get("folder_entries", [])
    }

    # Build lookup: file_id → file_entry
    file_entry_map: dict[str, dict[str, Any]] = {
        e["file_id"]: e
        for e in registry.get("file_entries", [])
        if e.get("file_id")
    }

    # Handle uninitialized cursor
    page_token = registry.get("changes_page_token")
    if not page_token:
        try:
            start_token = get_changes_start_page_token(drive)
        except (DriveAPIRequestError, DriveAPIResponseError) as exc:
            errors.append({
                "alias": alias,
                "file_id": "",
                "reason_code": str(DriveMonitorReasonCode.FETCH_FAILED),
                "message": f"Failed to get start page token: {exc}",
            })
            return {
                "registry": str(registry_path.relative_to(repo_root)),
                "alias": alias,
                "new_page_token": None,
                "drifted": drifted,
                "up_to_date": up_to_date,
                "uninitialized": uninitialized,
                "errors": errors,
                "has_drift": False,
            }
        # All existing file entries are uninitialized on first run
        for entry in registry.get("file_entries", []):
            uninitialized.append({
                "alias": alias,
                "file_id": entry.get("file_id", ""),
                "display_name": entry.get("display_name", ""),
                "tracking_status": entry.get("tracking_status", "uninitialized"),
            })
        return {
            "registry": str(registry_path.relative_to(repo_root)),
            "alias": alias,
            "new_page_token": start_token,
            "drifted": drifted,
            "up_to_date": up_to_date,
            "uninitialized": uninitialized,
            "errors": errors,
            "has_drift": False,
        }

    # Fetch changes since last cursor
    try:
        changes, new_page_token = list_changes(drive, page_token)
    except (DriveAPIRequestError, DriveAPIResponseError) as exc:
        errors.append({
            "alias": alias,
            "file_id": "",
            "reason_code": str(DriveMonitorReasonCode.FETCH_FAILED),
            "message": f"changes.list failed: {exc}",
        })
        return {
            "registry": str(registry_path.relative_to(repo_root)),
            "alias": alias,
            "new_page_token": None,
            "drifted": drifted,
            "up_to_date": up_to_date,
            "uninitialized": uninitialized,
            "errors": errors,
            "has_drift": False,
        }

    # Process each change
    seen_file_ids: set[str] = set()
    for change in changes:
        file_id = change.get("fileId", "")
        if not file_id or file_id in seen_file_ids:
            continue
        seen_file_ids.add(file_id)

        # File removed from Drive entirely
        if change.get("removed"):
            if file_id in file_entry_map:
                entry = file_entry_map[file_id]
                drifted.append({
                    "alias": alias,
                    "file_id": file_id,
                    "display_name": entry.get("display_name", file_id),
                    "display_path": entry.get("display_path", ""),
                    "mime_type": entry.get("mime_type", ""),
                    "event_type": "deleted",
                    "tracking_status": entry.get("tracking_status", "active"),
                    "wiki_page": entry.get("wiki_page"),
                    "current_drive_version": None,
                    "last_applied_drive_version": entry.get("last_applied_drive_version"),
                    "sha256_at_last_applied": entry.get("sha256_at_last_applied"),
                    "current_md5_checksum": None,
                    "md5_checksum_at_last_applied": entry.get("md5_checksum_at_last_applied"),
                    "parent_folder_id": None,
                    "lines_added": None,
                    "lines_removed": None,
                    "is_binary": None,
                    "file_size_bytes": None,
                })
            continue

        file_meta = change.get("file") or {}
        mime_type = file_meta.get("mimeType", "")
        drive_version = file_meta.get("version")
        md5_checksum = file_meta.get("md5Checksum")
        trashed = file_meta.get("trashed") or file_meta.get("explicitlyTrashed") or False
        display_name = file_meta.get("name", file_id)
        file_size = file_meta.get("size")

        # Trashed file
        if trashed:
            if file_id in file_entry_map:
                entry = file_entry_map[file_id]
                drifted.append({
                    "alias": alias,
                    "file_id": file_id,
                    "display_name": display_name,
                    "display_path": entry.get("display_path", ""),
                    "mime_type": mime_type,
                    "event_type": "trashed",
                    "tracking_status": entry.get("tracking_status", "active"),
                    "wiki_page": entry.get("wiki_page"),
                    "current_drive_version": None,
                    "last_applied_drive_version": entry.get("last_applied_drive_version"),
                    "sha256_at_last_applied": entry.get("sha256_at_last_applied"),
                    "current_md5_checksum": None,
                    "md5_checksum_at_last_applied": entry.get("md5_checksum_at_last_applied"),
                    "parent_folder_id": None,
                    "lines_added": None,
                    "lines_removed": None,
                    "is_binary": None,
                    "file_size_bytes": None,
                })
            continue

        # MIME type not in allowlist
        if mime_type not in DRIVE_MIME_ALLOWLIST:
            if file_id in file_entry_map:
                entry = file_entry_map[file_id]
                drifted.append({
                    "alias": alias,
                    "file_id": file_id,
                    "display_name": display_name,
                    "display_path": entry.get("display_path", ""),
                    "mime_type": mime_type,
                    "event_type": "out_of_scope",
                    "tracking_status": entry.get("tracking_status", "active"),
                    "wiki_page": entry.get("wiki_page"),
                    "current_drive_version": None,
                    "last_applied_drive_version": None,
                    "sha256_at_last_applied": None,
                    "current_md5_checksum": None,
                    "md5_checksum_at_last_applied": None,
                    "parent_folder_id": None,
                    "lines_added": None,
                    "lines_removed": None,
                    "is_binary": None,
                    "file_size_bytes": None,
                })
            continue

        # Known file: compare version/checksum
        if file_id in file_entry_map:
            entry = file_entry_map[file_id]
            tracking_status = entry.get("tracking_status", "active")
            if tracking_status in ("paused", "archived"):
                continue

            is_native = mime_type in MIME_EXPORT_MAP
            has_changed = False
            if is_native:
                last_version = entry.get("last_applied_drive_version")
                if drive_version is not None:
                    current_v = int(drive_version)
                    has_changed = (last_version is None) or (current_v != last_version)
                    if has_changed:
                        drifted.append({
                            "alias": alias,
                            "file_id": file_id,
                            "display_name": display_name,
                            "display_path": entry.get("display_path", ""),
                            "mime_type": mime_type,
                            "event_type": "content_changed",
                            "tracking_status": tracking_status,
                            "wiki_page": entry.get("wiki_page"),
                            "current_drive_version": current_v,
                            "last_applied_drive_version": last_version,
                            "sha256_at_last_applied": entry.get("sha256_at_last_applied"),
                            "current_md5_checksum": None,
                            "md5_checksum_at_last_applied": None,
                            "parent_folder_id": None,
                            "lines_added": None,
                            "lines_removed": None,
                            "is_binary": None,
                            "file_size_bytes": int(file_size) if file_size else None,
                        })
                    else:
                        up_to_date.append({
                            "alias": alias,
                            "file_id": file_id,
                            "display_name": display_name,
                        })
            else:
                last_md5 = entry.get("md5_checksum_at_last_applied")
                has_changed = (last_md5 is None) or (md5_checksum != last_md5)
                if has_changed:
                    drifted.append({
                        "alias": alias,
                        "file_id": file_id,
                        "display_name": display_name,
                        "display_path": entry.get("display_path", ""),
                        "mime_type": mime_type,
                        "event_type": "content_changed",
                        "tracking_status": tracking_status,
                        "wiki_page": entry.get("wiki_page"),
                        "current_drive_version": None,
                        "last_applied_drive_version": None,
                        "sha256_at_last_applied": None,
                        "current_md5_checksum": md5_checksum,
                        "md5_checksum_at_last_applied": last_md5,
                        "parent_folder_id": None,
                        "lines_added": None,
                        "lines_removed": None,
                        "is_binary": None,
                        "file_size_bytes": int(file_size) if file_size else None,
                    })
                else:
                    up_to_date.append({
                        "alias": alias,
                        "file_id": file_id,
                        "display_name": display_name,
                    })
        else:
            # New file: resolve parent chain to find its registered folder
            try:
                parent_folder_id = _resolve_parent_folder(
                    drive, file_id, active_folder_ids
                )
            except (DriveAPIRequestError, DriveAPIResponseError) as exc:
                errors.append({
                    "alias": alias,
                    "file_id": file_id,
                    "reason_code": str(DriveMonitorReasonCode.PARENT_RESOLUTION_FAILED),
                    "message": f"Parent-chain resolution failed for {file_id!r}: {exc}",
                })
                continue

            if parent_folder_id is None:
                # Not under any registered folder — skip
                continue

            wiki_namespace = folder_namespace.get(parent_folder_id, "")
            is_native = mime_type in MIME_EXPORT_MAP
            drifted.append({
                "alias": alias,
                "file_id": file_id,
                "display_name": display_name,
                "display_path": display_name,
                "mime_type": mime_type,
                "event_type": "new_file",
                "tracking_status": "uninitialized",
                "wiki_page": None,
                "current_drive_version": int(drive_version) if is_native and drive_version else None,
                "last_applied_drive_version": None,
                "sha256_at_last_applied": None,
                "current_md5_checksum": md5_checksum if not is_native else None,
                "md5_checksum_at_last_applied": None,
                "parent_folder_id": parent_folder_id,
                "lines_added": None,
                "lines_removed": None,
                "is_binary": None,
                "file_size_bytes": int(file_size) if file_size else None,
            })

    # Any remaining active file_entries not touched by changes remain up_to_date
    for entry in registry.get("file_entries", []):
        fid = entry.get("file_id", "")
        if fid and fid not in seen_file_ids:
            tracking_status = entry.get("tracking_status", "active")
            if tracking_status == "uninitialized":
                uninitialized.append({
                    "alias": alias,
                    "file_id": fid,
                    "display_name": entry.get("display_name", ""),
                    "tracking_status": tracking_status,
                })
            elif tracking_status == "active":
                up_to_date.append({
                    "alias": alias,
                    "file_id": fid,
                    "display_name": entry.get("display_name", ""),
                })

    return {
        "registry": str(registry_path.relative_to(repo_root)),
        "alias": alias,
        "new_page_token": new_page_token,
        "drifted": drifted,
        "up_to_date": up_to_date,
        "uninitialized": uninitialized,
        "errors": errors,
        "has_drift": bool(drifted),
    }


def check_drift(
    *,
    repo_root: Path,
    registry_paths: list[Path] | None = None,
    output_path: Path,
) -> SurfaceResult:
    """Run drift detection across Drive source registries.

    Parameters
    ----------
    repo_root:
        Absolute path to the knowledgebase repository root.
    registry_paths:
        List of specific registry files to check.  If ``None``, all
        ``*.source-registry.json`` files under ``raw/drive-sources/`` are used.
    output_path:
        Path to write the drift report JSON.

    Returns
    -------
    SurfaceResult
        STATUS_PASS on success (even when drift is found);
        STATUS_FAIL on configuration or API errors.
    """
    if not looks_like_repo_root(repo_root):
        return repo_root_failure(
            surface=SURFACE, mode=MODE, approval="none", path_rules=_path_rules()
        )

    if registry_paths is None:
        registry_paths = find_registry_files(repo_root)

    if not registry_paths:
        report = {
            "version": DRIFT_REPORT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "registry": "raw/drive-sources/",
            "has_drift": False,
            "drifted": [],
            "up_to_date": [],
            "uninitialized": [],
            "errors": [],
            "cursors": {},
        }
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_PASS,
            reason_code=str(DriveMonitorReasonCode.NO_DRIFT),
            message="No drive source registries found.",
            path_rules=_path_rules(),
        )

    all_drifted: list[dict[str, Any]] = []
    all_up_to_date: list[dict[str, Any]] = []
    all_uninitialized: list[dict[str, Any]] = []
    all_errors: list[dict[str, Any]] = []
    cursors: dict[str, str] = {}

    for reg_path in registry_paths:
        result = _check_single_registry(reg_path, repo_root)
        all_drifted.extend(result["drifted"])
        all_up_to_date.extend(result["up_to_date"])
        all_uninitialized.extend(result["uninitialized"])
        all_errors.extend(result["errors"])
        token = result.get("new_page_token")
        alias = result.get("alias")
        if alias and token:
            cursors[alias] = token

    has_drift = bool(all_drifted)
    report = {
        "version": DRIFT_REPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry": str(registry_paths[0].relative_to(repo_root))
        if len(registry_paths) == 1
        else "raw/drive-sources/",
        "has_drift": has_drift,
        "drifted": all_drifted,
        "up_to_date": all_up_to_date,
        "uninitialized": all_uninitialized,
        "errors": all_errors,
        "cursors": cursors,
    }

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except OSError as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_FAIL,
            reason_code=str(DriveMonitorReasonCode.FETCH_FAILED),
            message=f"Failed to write drift report: {exc}",
            path_rules=_path_rules(),
        )

    reason = (
        DriveMonitorReasonCode.DRIFT_DETECTED if has_drift
        else DriveMonitorReasonCode.NO_DRIFT
    )
    error_note = f"; {len(all_errors)} error(s)" if all_errors else ""
    message = (
        f"Drive drift check: {len(all_drifted)} drifted, "
        f"{len(all_up_to_date)} up-to-date, "
        f"{len(all_uninitialized)} uninitialized{error_note}"
    )
    print(message, file=sys.stderr)

    return SurfaceResult(
        surface=SURFACE,
        mode=MODE,
        status=STATUS_PASS,
        reason_code=str(reason),
        message=message,
        path_rules=_path_rules(),
        summary={
            "drifted_count": len(all_drifted),
            "up_to_date_count": len(all_up_to_date),
            "uninitialized_count": len(all_uninitialized),
            "error_count": len(all_errors),
            "has_drift": has_drift,
        },
    )


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Detect content drift in monitored Google Drive sources."
    )
    parser.add_argument(
        "--registry",
        metavar="PATH",
        help=(
            "Path to a specific registry file. "
            "Omit to check all registries under raw/drive-sources/."
        ),
    )
    parser.add_argument(
        "--repo-root",
        metavar="PATH",
        default=".",
        help="Repository root directory (default: current directory).",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default="drift-report.json",
        help="Path to write the drift report JSON (default: drift-report.json).",
    )
    return parser


def _args_to_kwargs(args: Any) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    registry_paths = [Path(args.registry)] if args.registry else None
    return {
        "repo_root": repo_root,
        "registry_paths": registry_paths,
        "output_path": Path(args.output),
    }


def _runner(**kwargs: Any) -> SurfaceResult:
    return check_drift(**kwargs)


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
