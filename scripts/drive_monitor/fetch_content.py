"""Fetch content for drifted Drive sources (Phase 2 — write-capable).

Reads the drift report produced by ``check_drift.py``, exports/downloads
changed files from the Drive API, normalizes Markdown exports, computes
SHA-256 checksums, writes assets to
``raw/assets/gdrive/{alias}/{file_id}/{version}/{filename}`` using
``exclusive_create_write_once()``, and advances ``last_fetched_*`` in the
source registry.

This script does NOT modify ``last_applied_*`` fields — that is the
responsibility of ``synthesize_diff.py`` (Phase 3).

Lock ordering: only ``raw/.drive-sources.lock`` is acquired (no wiki lock
needed since no wiki writes occur here).

Usage::

    python -m scripts.drive_monitor.fetch_content \\
        --drift-report drift-report.json \\
        --approval approved \\
        [--repo-root /path/to/repo]

Requires ``--approval approved`` for any write operation.  Authentication:
set ``GDRIVE_SA_KEY`` (service account JSON key content) in the environment.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
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
from scripts.kb.write_utils import exclusive_create_write_once
from scripts.drive_monitor._types import (
    MIME_EXPORT_MAP,
    MIME_EXTENSION_MAP,
    OVERSIZE_LIMIT_BYTES,
    validate_drive_drift_report,
)
from scripts.drive_monitor._http import (
    build_drive_client,
    export_file_as_markdown,
    export_file_as_pdf,
    download_file,
    DriveAPIRequestError,
    DriveAPIResponseError,
)
from scripts.drive_monitor._normalize import normalize_markdown_export
from scripts.drive_monitor._validators import (
    build_drive_asset_path,
    validate_file_id,
    validate_display_name,
)
from scripts.drive_monitor._registry import (
    find_registry_by_alias,
    update_last_fetched,
)

SURFACE = "drive_monitor.fetch_content"
MODE = "fetch"


def _path_rules() -> dict[str, Any]:
    return base_path_rules(
        allowed_roots=["raw/assets/gdrive", "raw/drive-sources"],
        allowed_suffixes=None,
    )


def _safe_filename(display_name: str, mime_type: str) -> str:
    """Build a safe filename for the asset from the display name and MIME type.

    Replaces unsafe characters with underscores, limits length to 200 chars,
    and appends the canonical extension for the MIME type.
    """
    # Strip the file extension from the display name if it already has one
    base = re.sub(r"[^\w\-. ]+", "_", display_name).strip().rstrip(".")
    if not base:
        base = "untitled"
    base = base[:200]
    ext = MIME_EXTENSION_MAP.get(mime_type, "")
    if ext and not base.lower().endswith(ext):
        return base + ext
    return base


def _fetch_and_store_asset(
    repo_root: Path,
    entry: dict[str, Any],
    drive: Any,
) -> tuple[bool, str | None, str | None, str | None]:
    """Fetch/export one drifted entry and store it in raw/assets/gdrive/.

    Returns ``(success, version_segment, sha256_hex, normalized_filename)``.
    ``version_segment`` is the drive_version string (native) or md5checksum (non-native).
    On error returns ``(False, None, None, None)`` and logs to stderr.
    """
    file_id = entry.get("file_id", "")
    mime_type = entry.get("mime_type", "")
    display_name = entry.get("display_name", file_id)
    alias = entry.get("alias", "")
    event_type = entry.get("event_type", "")

    # Lifecycle events don't require a fetch
    if event_type in ("trashed", "deleted", "out_of_scope"):
        return True, None, None, None

    try:
        validate_file_id(file_id)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return False, None, None, None

    is_native = mime_type in MIME_EXPORT_MAP

    try:
        if is_native:
            if mime_type == "application/vnd.google-apps.document":
                raw_bytes = export_file_as_markdown(drive, file_id)
                asset_bytes = normalize_markdown_export(raw_bytes)
            else:
                # Slides → PDF
                asset_bytes = export_file_as_pdf(drive, file_id)
            drive_version = entry.get("current_drive_version")
            if drive_version is None:
                print(
                    f"WARNING: no drive_version for {file_id!r}; skipping fetch",
                    file=sys.stderr,
                )
                return False, None, None, None
            version_segment = str(drive_version)
            md5_checksum = None
        else:
            asset_bytes = download_file(drive, file_id)
            md5_checksum = entry.get("current_md5_checksum")
            if not md5_checksum:
                import hashlib as _hl
                import binascii as _bi
                import struct as _st
                # Compute MD5 from downloaded bytes as fallback
                md5_checksum = hashlib.md5(asset_bytes).hexdigest()
            version_segment = md5_checksum
            drive_version = None

    except (DriveAPIRequestError, DriveAPIResponseError) as exc:
        print(f"ERROR: fetch failed for {file_id!r}: {exc}", file=sys.stderr)
        return False, None, None, None

    if len(asset_bytes) > OVERSIZE_LIMIT_BYTES:
        print(
            f"WARNING: asset {file_id!r} is {len(asset_bytes)} bytes "
            f"(>{OVERSIZE_LIMIT_BYTES}); skipping",
            file=sys.stderr,
        )
        return False, None, None, None

    sha256_hex = hashlib.sha256(asset_bytes).hexdigest()

    try:
        safe_name = _safe_filename(display_name, mime_type)
        asset_path = build_drive_asset_path(
            repo_root, alias, file_id, version_segment, safe_name
        )
    except ValueError as exc:
        print(f"ERROR: asset path validation failed for {file_id!r}: {exc}", file=sys.stderr)
        return False, None, None, None

    try:
        exclusive_create_write_once(asset_path, asset_bytes)
    except FileExistsError:
        # Asset already exists (idempotent — same content, same version)
        pass
    except OSError as exc:
        print(f"ERROR: failed to write asset {asset_path}: {exc}", file=sys.stderr)
        return False, None, None, None

    return True, version_segment, sha256_hex, safe_name


def fetch_content(
    *,
    repo_root: Path,
    drift_report_path: Path,
    approval: str = APPROVAL_NONE,
) -> SurfaceResult:
    """Fetch and vendor all drifted Drive file entries.

    Parameters
    ----------
    repo_root:
        Absolute path to the knowledgebase repository root.
    drift_report_path:
        Path to the drift report JSON from ``check_drift.py``.
    approval:
        Must be ``"approved"`` for any writes to occur.

    Returns
    -------
    SurfaceResult
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
        validate_drive_drift_report(report)
    except (json.JSONDecodeError, ValueError) as exc:
        return invalid_input_result(
            surface=SURFACE, mode=MODE, approval=approval,
            path_rules=_path_rules(),
            message=f"Malformed drift report: {exc}",
        )

    drifted = report.get("drifted", [])
    if not drifted:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_PASS,
            reason_code=str(DriveMonitorReasonCode.NO_DRIFT),
            message="No drifted entries to fetch.",
            path_rules=_path_rules(),
        )

    # Group entries by alias to build one Drive client per credential
    by_alias: dict[str, list[dict[str, Any]]] = {}
    for entry in drifted:
        by_alias.setdefault(entry.get("alias", ""), []).append(entry)

    success_count = 0
    error_count = 0
    skipped_count = 0

    for alias, entries in by_alias.items():
        registry_path = find_registry_by_alias(repo_root, alias)
        if not registry_path:
            print(
                f"WARNING: no registry found for alias {alias!r}; skipping",
                file=sys.stderr,
            )
            error_count += len(entries)
            continue

        try:
            registry_raw = json.loads(registry_path.read_text(encoding="utf-8"))
            credential_secret = registry_raw.get("credential_secret_name") or "GDRIVE_SA_KEY"
            drive = build_drive_client(credential_secret)
        except (OSError, DriveAPIRequestError) as exc:
            print(f"ERROR: cannot build Drive client for {alias!r}: {exc}", file=sys.stderr)
            error_count += len(entries)
            continue

        for entry in entries:
            event_type = entry.get("event_type", "")
            if event_type in ("trashed", "deleted", "out_of_scope"):
                skipped_count += 1
                continue

            ok, version_segment, sha256_hex, _filename = _fetch_and_store_asset(
                repo_root, entry, drive
            )
            if not ok:
                error_count += 1
                continue

            # Update last_fetched_* in registry
            file_id = entry.get("file_id", "")
            mime_type = entry.get("mime_type", "")
            is_native = mime_type in MIME_EXPORT_MAP

            try:
                if is_native:
                    drive_version = entry.get("current_drive_version")
                    update_last_fetched(
                        repo_root,
                        registry_path,
                        file_id,
                        drive_version=int(drive_version) if drive_version else None,
                        sha256=sha256_hex,
                    )
                else:
                    md5_checksum = version_segment
                    update_last_fetched(
                        repo_root,
                        registry_path,
                        file_id,
                        md5_checksum=md5_checksum,
                        sha256=sha256_hex,
                    )
            except OSError as exc:
                print(
                    f"ERROR: failed to update last_fetched for {file_id!r}: {exc}",
                    file=sys.stderr,
                )
                error_count += 1
                continue

            success_count += 1

    total = len(drifted)
    message = (
        f"Drive fetch: {success_count} fetched, "
        f"{skipped_count} lifecycle-skipped, "
        f"{error_count} errors (of {total} entries)"
    )
    print(message, file=sys.stderr)

    status = STATUS_PASS if error_count == 0 else STATUS_FAIL
    reason = (
        DriveMonitorReasonCode.DRIFT_DETECTED if success_count > 0
        else DriveMonitorReasonCode.FETCH_FAILED
    )

    return SurfaceResult(
        surface=SURFACE,
        mode=MODE,
        status=status,
        reason_code=str(reason),
        message=message,
        path_rules=_path_rules(),
        summary={
            "success_count": success_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
        },
    )


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Fetch and vendor drifted Google Drive source files."
    )
    parser.add_argument(
        "--drift-report",
        metavar="PATH",
        required=True,
        help="Path to the drift report JSON produced by check_drift.",
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
    return fetch_content(**kwargs)


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
