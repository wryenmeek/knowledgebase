"""Shared registry read/update helpers for the github_monitor script family.

Registry files (``raw/github-sources/*.source-registry.json``) are the
three-stage state tracking artifacts for GitHub source monitoring.  All
mutations use the ``raw/.github-sources.lock`` advisory lock and atomic file
replacement to prevent partial writes and concurrent corruption.

Lock ordering rule (ADR-012): callers that need BOTH the wiki write lock AND
the registry lock MUST acquire ``wiki/.kb_write.lock`` FIRST, then acquire
``raw/.github-sources.lock`` inside the wiki lock context.  This module only
acquires the registry lock; callers are responsible for the outer wiki lock
when both are needed.
"""

from __future__ import annotations

import contextlib
import glob as glob_module
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.kb import contracts, write_utils
from scripts.github_monitor._types import validate_registry_file


def find_registry_for(repo_root: Path, owner: str, repo: str) -> Path | None:
    """Return the registry file path for *owner*/*repo*, or ``None``.

    Scans all ``*.source-registry.json`` files under
    ``raw/github-sources/`` and returns the first one whose top-level
    ``owner`` and ``repo`` fields match.  Returns ``None`` if none match.
    """
    pattern = str(repo_root / "raw" / "github-sources" / "*.source-registry.json")
    for match in sorted(glob_module.glob(pattern)):
        p = Path(match)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("owner") == owner and data.get("repo") == repo:
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
    entry_path: str,
    *,
    commit_sha: str,
    blob_sha: str,
) -> bool:
    """Under the registry lock, advance ``last_fetched_*`` for *entry_path*.

    Acquires ``raw/.github-sources.lock``, reads the registry, finds the
    entry matching *entry_path*, updates ``last_fetched_commit_sha`` and
    ``last_fetched_blob_sha``, then atomically replaces the registry file.

    Returns ``True`` if the entry was found and updated, ``False`` otherwise.
    Does NOT modify ``last_applied_*`` fields.
    """
    with write_utils.exclusive_write_lock(
        repo_root, lock_path=contracts.GITHUB_SOURCES_LOCK_PATH
    ):
        try:
            raw = json.loads(registry_path.read_text(encoding="utf-8"))
            registry = validate_registry_file(raw)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise OSError(
                f"Failed to read/validate registry {registry_path}: {exc}"
            ) from exc

        updated = False
        for entry in registry["entries"]:
            if entry.get("path") == entry_path:
                entry["last_fetched_commit_sha"] = commit_sha
                entry["last_fetched_blob_sha"] = blob_sha
                updated = True
                break

        if updated:
            _atomic_replace_registry(registry_path, registry)

    return updated


def update_last_applied(
    repo_root: Path,
    registry_path: Path,
    entry_path: str,
    *,
    commit_sha: str,
    blob_sha: str,
    sha256: str,
    applied_at: str | None = None,
) -> bool:
    """Under the registry lock, advance ``last_applied_*`` for *entry_path*.

    Acquires ``raw/.github-sources.lock`` (must be called INSIDE the wiki
    write lock — see ADR-012 lock ordering).  Reads the registry, finds the
    entry matching *entry_path*, sets ``last_applied_commit_sha``,
    ``last_applied_blob_sha``, ``sha256_at_last_applied``, and
    ``last_applied_at``, then atomically replaces the registry file.

    Returns ``True`` if the entry was found and updated, ``False`` otherwise.
    Does NOT modify ``last_fetched_*`` fields.
    """
    if applied_at is None:
        applied_at = datetime.now(timezone.utc).isoformat()

    with write_utils.exclusive_write_lock(
        repo_root, lock_path=contracts.GITHUB_SOURCES_LOCK_PATH
    ):
        try:
            raw = json.loads(registry_path.read_text(encoding="utf-8"))
            registry = validate_registry_file(raw)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise OSError(
                f"Failed to read/validate registry {registry_path}: {exc}"
            ) from exc

        updated = False
        for entry in registry["entries"]:
            if entry.get("path") == entry_path:
                entry["last_applied_commit_sha"] = commit_sha
                entry["last_applied_blob_sha"] = blob_sha
                entry["sha256_at_last_applied"] = sha256
                entry["last_applied_at"] = applied_at
                updated = True
                break

        if updated:
            _atomic_replace_registry(registry_path, registry)

    return updated
