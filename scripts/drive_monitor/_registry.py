"""Shared registry read/update helpers for the drive_monitor script family.

Registry files (``raw/drive-sources/{alias}.source-registry.json``) are the
three-stage state tracking artifacts for Drive source monitoring.  All
mutations use the ``raw/.drive-sources.lock`` advisory lock and atomic file
replacement to prevent partial writes and concurrent corruption.

Lock ordering rule (ADR-021): callers that need BOTH the wiki write lock AND
the registry lock MUST acquire ``wiki/.kb_write.lock`` FIRST, then acquire
``raw/.drive-sources.lock`` inside the wiki lock context.  This module only
acquires the registry lock; callers are responsible for the outer wiki lock
when both are needed.
"""

from __future__ import annotations

import contextlib
import glob as glob_module
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.kb import contracts, write_utils
from scripts.drive_monitor._types import validate_drive_registry_file


def find_registry_files(repo_root: Path) -> list[Path]:
    """Return all ``*.source-registry.json`` paths under ``raw/drive-sources/``.

    Returns an empty list if the directory does not exist.
    """
    pattern = str(repo_root / "raw" / "drive-sources" / "*.source-registry.json")
    return sorted(Path(p) for p in glob_module.glob(pattern))


def find_registry_by_alias(repo_root: Path, alias: str) -> Path | None:
    """Return the registry file path for the given *alias*, or ``None``.

    Scans all ``*.source-registry.json`` files under ``raw/drive-sources/``
    and returns the one whose top-level ``alias`` field matches.
    """
    for p in find_registry_files(repo_root):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(
                f"WARNING: skipping unreadable/corrupt registry file {p}: {exc}",
                file=sys.stderr,
            )
            continue
        if data.get("alias") == alias:
            return p
    return None


def _atomic_replace_registry(registry_path: Path, registry: dict[str, Any]) -> None:
    """Atomically replace *registry_path* with the JSON-serialised *registry*."""
    fd, tmp_str = tempfile.mkstemp(
        dir=registry_path.parent, prefix=f".{registry_path.name}."
    )
    tmp = Path(tmp_str)
    try:
        try:
            os.write(fd, json.dumps(registry, indent=2).encode("utf-8"))
            os.write(fd, b"\n")
        finally:
            os.close(fd)
        os.replace(tmp, registry_path)
    except Exception:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def update_last_fetched(
    repo_root: Path,
    registry_path: Path,
    file_id: str,
    *,
    drive_version: int | None = None,
    md5_checksum: str | None = None,
    sha256: str | None = None,
) -> bool:
    """Under the registry lock, advance ``last_fetched_*`` for *file_id*.

    Acquires ``raw/.drive-sources.lock``, reads the registry, finds the
    file_entry matching *file_id*, updates the relevant ``last_fetched_*``
    fields, then atomically replaces the registry file.

    Returns ``True`` if the entry was found and updated, ``False`` otherwise.
    Does NOT modify ``last_applied_*`` fields.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()

    with write_utils.exclusive_write_lock(
        repo_root, lock_path=contracts.DRIVE_SOURCES_LOCK_PATH
    ):
        try:
            raw = json.loads(registry_path.read_text(encoding="utf-8"))
            registry = validate_drive_registry_file(raw)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise OSError(
                f"Failed to read/validate registry {registry_path}: {exc}"
            ) from exc

        updated = False
        for entry in registry["file_entries"]:
            if entry.get("file_id") == file_id:
                if drive_version is not None:
                    entry["last_fetched_drive_version"] = drive_version
                if md5_checksum is not None:
                    entry["md5_checksum_at_last_fetched"] = md5_checksum
                if sha256 is not None:
                    entry["sha256_at_last_fetched"] = sha256
                entry["last_fetched_at"] = fetched_at
                updated = True
                break

        if updated:
            _atomic_replace_registry(registry_path, registry)

    return updated


def update_last_applied(
    repo_root: Path,
    registry_path: Path,
    file_id: str,
    *,
    drive_version: int | None = None,
    md5_checksum: str | None = None,
    sha256: str | None = None,
    applied_at: str | None = None,
) -> bool:
    """Under the registry lock, advance ``last_applied_*`` for *file_id*.

    MUST be called INSIDE the wiki write lock context (ADR-021 lock ordering).
    Acquires ``raw/.drive-sources.lock``, reads the registry, finds the
    file_entry matching *file_id*, updates ``last_applied_*`` fields, and
    resets ``last_fetched_*`` to ``None``.

    Returns ``True`` if the entry was found and updated, ``False`` otherwise.
    Resets ``last_fetched_*`` fields to ``None`` to reflect the consumed fetch state.
    """
    if applied_at is None:
        applied_at = datetime.now(timezone.utc).isoformat()

    with write_utils.exclusive_write_lock(
        repo_root, lock_path=contracts.DRIVE_SOURCES_LOCK_PATH
    ):
        try:
            raw = json.loads(registry_path.read_text(encoding="utf-8"))
            registry = validate_drive_registry_file(raw)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise OSError(
                f"Failed to read/validate registry {registry_path}: {exc}"
            ) from exc

        updated = False
        for entry in registry["file_entries"]:
            if entry.get("file_id") == file_id:
                if drive_version is not None:
                    entry["last_applied_drive_version"] = drive_version
                    entry["drive_version"] = drive_version
                if md5_checksum is not None:
                    entry["md5_checksum_at_last_applied"] = md5_checksum
                if sha256 is not None:
                    entry["sha256_at_last_applied"] = sha256
                entry["last_applied_at"] = applied_at
                # Reset last_fetched_* after successful apply
                entry["last_fetched_drive_version"] = None
                entry["sha256_at_last_fetched"] = None
                entry["md5_checksum_at_last_fetched"] = None
                entry["last_fetched_at"] = None
                updated = True
                break

        if updated:
            _atomic_replace_registry(registry_path, registry)

    return updated


def update_changes_cursor(
    repo_root: Path,
    registry_path: Path,
    new_page_token: str,
) -> None:
    """Under the registry lock, save the new Changes API page token.

    Must be called by ``advance_cursor.py`` after all entries for the alias
    are durably handled, to advance the cursor and avoid re-processing the
    same changes on the next run.
    """
    with write_utils.exclusive_write_lock(
        repo_root, lock_path=contracts.DRIVE_SOURCES_LOCK_PATH
    ):
        try:
            raw = json.loads(registry_path.read_text(encoding="utf-8"))
            registry = validate_drive_registry_file(raw)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise OSError(
                f"Failed to read/validate registry {registry_path}: {exc}"
            ) from exc

        registry["changes_page_token"] = new_page_token  # type: ignore[typeddict-item]
        _atomic_replace_registry(registry_path, registry)


def add_file_entry(
    repo_root: Path,
    registry_path: Path,
    file_id: str,
    *,
    display_name: str,
    display_path: str,
    mime_type: str,
    wiki_namespace: str,
) -> None:
    """Under the registry lock, add a new file_entry for a newly-discovered file.

    The entry is added with ``tracking_status: "uninitialized"`` and all
    version/hash fields set to ``None``.  The wiki_page is auto-assigned from
    ``wiki_namespace`` + slugified ``display_name``.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", display_name.lower()).strip("-")
    wiki_page = f"wiki/{wiki_namespace.rstrip('/')}/{slug}.md"

    new_entry: dict[str, Any] = {
        "file_id": file_id,
        "display_name": display_name,
        "display_path": display_path,
        "mime_type": mime_type,
        "tracking_status": "uninitialized",
        "wiki_page": wiki_page,
        "drive_version": None,
        "last_applied_drive_version": None,
        "last_applied_at": None,
        "sha256_at_last_applied": None,
        "last_fetched_drive_version": None,
        "last_fetched_at": None,
        "sha256_at_last_fetched": None,
        "md5_checksum_at_last_applied": None,
        "md5_checksum_at_last_fetched": None,
        "notes": "",
    }

    with write_utils.exclusive_write_lock(
        repo_root, lock_path=contracts.DRIVE_SOURCES_LOCK_PATH
    ):
        try:
            raw = json.loads(registry_path.read_text(encoding="utf-8"))
            registry = validate_drive_registry_file(raw)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise OSError(
                f"Failed to read/validate registry {registry_path}: {exc}"
            ) from exc

        # Deduplication: don't add if file_id already present
        existing_ids = {e.get("file_id") for e in registry["file_entries"]}
        if file_id not in existing_ids:
            registry["file_entries"].append(new_entry)  # type: ignore[arg-type]
            _atomic_replace_registry(registry_path, registry)
