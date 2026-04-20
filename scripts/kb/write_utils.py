"""Write-path lock and state-change logging helpers."""

from __future__ import annotations

import contextlib
from contextlib import contextmanager
import fcntl
import os
from os import PathLike
from pathlib import Path
from typing import Iterator, Sequence, TextIO

from . import contracts
from . import path_utils


LOG_PATH = Path("wiki/log.md")

def governed_artifact_contract_for_path(
    path: str | PathLike[str],
) -> contracts.GovernedArtifactContract | None:
    """Return the governed artifact contract for a repo-relative path, if any."""
    try:
        normalized_path = path_utils.normalize_repo_relative_path(path)
    except path_utils.RepoRelativePathError:
        return None
    return contracts.governed_artifact_contract(normalized_path)


def governed_artifact_requires_lock(path: str | PathLike[str]) -> bool:
    """Report whether a declared governed artifact requires the write lock."""
    contract = governed_artifact_contract_for_path(path)
    return contract is not None and contract.lock_path == contracts.WRITE_LOCK_PATH


def governed_artifact_requires_atomic_replace(path: str | PathLike[str]) -> bool:
    """Report whether a governed artifact must use atomic full-file replacement."""
    contract = governed_artifact_contract_for_path(path)
    return (
        contract is not None
        and contract.write_strategy
        == contracts.ArtifactWriteStrategy.ATOMIC_REPLACE_UNDER_LOCK.value
    )


def lock_unavailable_reason(lock_path: str = contracts.WRITE_LOCK_PATH) -> str:
    """Return a deterministic lock contention failure reason."""
    return f"{contracts.ReasonCode.LOCK_UNAVAILABLE.value}:{lock_path}"


class LockUnavailableError(RuntimeError):
    """Raised when the write lock cannot be acquired."""

    reason_code: str
    failure_reason: str

    def __init__(self, lock_path: str = contracts.WRITE_LOCK_PATH) -> None:
        self.reason_code = contracts.ReasonCode.LOCK_UNAVAILABLE.value
        self.failure_reason = lock_unavailable_reason(lock_path)
        hint = "retry after the competing process completes, or remove the lock file if it is stale"
        super().__init__(f"{self.failure_reason} — {hint}")


@contextmanager
def exclusive_write_lock(repo_root: str | Path = ".") -> Iterator[Path]:
    """Acquire an exclusive non-blocking write lock for wiki mutations.

    A pre-existing unlocked lock file is treated as stale metadata and does not
    block acquisition; only an active advisory lock fails closed.
    """
    lock_path = Path(repo_root) / contracts.WRITE_LOCK_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        lock_file = lock_path.open("a+", encoding="utf-8")
    except OSError as exc:
        raise LockUnavailableError() from exc

    with lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise LockUnavailableError() from exc

        try:
            yield lock_path
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def atomic_replace_governed_artifact(
    repo_root: str | Path,
    path: str | PathLike[str],
    content: str,
) -> Path:
    """Atomically replace a governed mutable artifact inside the repo."""
    contract = governed_artifact_contract_for_path(path)
    if contract is None:
        raise ValueError(f"unsupported governed artifact: {path}")
    if contract.write_strategy != contracts.ArtifactWriteStrategy.ATOMIC_REPLACE_UNDER_LOCK.value:
        raise ValueError(f"artifact does not support atomic replace: {contract.path}")

    target_path = Path(repo_root) / contract.path
    temp_path = target_path.with_name(f".{target_path.name}.kbtmp")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(FileNotFoundError):
        temp_path.unlink()

    try:
        with open_atomic_temp_file(temp_path) as handle:
            handle.write(content)
        os.replace(temp_path, target_path)
    except OSError:
        with contextlib.suppress(OSError):
            temp_path.unlink()
        raise

    return target_path


def open_atomic_temp_file(temp_path: Path) -> TextIO:
    """Open *temp_path* for exclusive creation and return a writable text handle.

    Uses ``O_EXCL`` so that two concurrent writers cannot both succeed on the same
    temp path (prevents TOCTOU races).  The caller is responsible for the commit:

    * **On success:** call ``os.replace(temp_path, dest)`` to atomically rename the
      temp file into place.
    * **On failure:** call ``temp_path.unlink()`` (or suppress ``OSError``) to avoid
      leaving a stale temp file behind.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temp_path, flags, 0o600)
    return os.fdopen(fd, "w", encoding="utf-8", newline="\n")


def append_log_only_state_changes(
    repo_root: str | Path,
    entry: str,
    *,
    state_changed: bool,
) -> bool:
    """Append an entry to wiki/log.md only when state has changed."""
    if not state_changed:
        return False

    log_path = Path(repo_root) / LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_entry = entry.rstrip("\n") + "\n"

    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(normalized_entry)

    return True


def write_text_capturing_previous(path: Path, content: str) -> tuple[bool, str | None]:
    """Write content to path and return ``(changed, previous_content)``.

    Reads the existing content (if any) before writing so the caller can
    later restore it with ``rollback_file_state``.  If the content is
    unchanged, returns ``(False, existing_content)`` without writing.
    Creates parent directories as needed.

    Use this variant when the caller needs to accumulate rollback snapshots.
    For write-only calls where rollback is not needed, prefer
    ``write_text_if_changed``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_content: str | None = path.read_text(encoding="utf-8") if path.exists() else None
    if previous_content == content:
        return False, previous_content
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    return True, previous_content


def check_no_symlink_path(path: Path) -> None:
    """Raise OSError if any component of path (up to root) is a symlink."""
    current = path
    while True:
        if current.is_symlink():
            raise OSError(f"symlinked path component is not allowed: {current}")
        if current.parent == current:
            return
        current = current.parent


def write_text_capturing_previous_safe(path: Path, content: str) -> tuple[bool, str | None]:
    """Like ``write_text_capturing_previous`` but with symlink and atomic-write guards.

    Rejects symlinks anywhere in the path chain, and uses a temp-file + rename to
    write atomically.  Use this for paths that may be security-sensitive or where
    partial writes must be prevented.

    Returns ``(changed, previous_content)`` — suitable for use with
    ``rollback_file_state``.
    """
    if path.exists() or path.is_symlink():
        check_no_symlink_path(path)

    previous_content: str | None = path.read_text(encoding="utf-8") if path.exists() else None
    if previous_content == content:
        return False, previous_content

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_created = False
    try:
        with open_atomic_temp_file(temp_path) as handle:
            temp_created = True
            handle.write(content)
        check_no_symlink_path(path)
        os.replace(temp_path, path)
    except OSError:
        if temp_created:
            with contextlib.suppress(OSError):
                temp_path.unlink()
        raise

    return True, previous_content


def read_optional_text(path: Path) -> str | None:
    """Return path's text content, or None if it does not exist."""
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def write_text_if_changed(path: Path, content: str) -> bool:
    """Write content to path only when it differs from the existing content.

    Creates parent directories as needed. Returns True when the file was
    written, False when the existing content already matched.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    if existing == content:
        return False
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    return True


def _restore_optional_text(path: Path, previous_content: str | None) -> None:
    """Restore path to previous_content, or delete it if previous_content is None."""
    if previous_content is None:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(previous_content)


def rollback_file_state(snapshots: Sequence[tuple[Path, str | None]]) -> None:
    """Restore a sequence of (path, previous_content) snapshots in reverse order.

    Iterates snapshots in reverse so the most recent mutation is undone first.
    Collects all OSError failures and raises a single combined OSError at the end
    so every snapshot gets an attempted restore.
    """
    rollback_errors: list[str] = []
    for path, previous_content in reversed(tuple(snapshots)):
        try:
            _restore_optional_text(path, previous_content)
        except OSError as exc:
            rollback_errors.append(f"{path}: {exc}")
    if rollback_errors:
        raise OSError(f"rollback failed: {'; '.join(rollback_errors)}")


def validate_log_entry(entry: str) -> str:
    """Validate a wiki/log.md bullet and return its stripped form.

    Raises ``ValueError`` for non-strings, empty values, missing ``- `` prefix,
    or embedded newlines / carriage returns.
    """
    if not isinstance(entry, str):
        raise ValueError("entry must be a string")
    normalized = entry.strip()
    if not normalized or not normalized.startswith("- ") or "\n" in normalized or "\r" in normalized:
        raise ValueError(
            "entry must be a single non-empty markdown bullet beginning with '- '"
        )
    return normalized


__all__ = [
    "check_no_symlink_path",
    "LockUnavailableError",
    "atomic_replace_governed_artifact",
    "exclusive_write_lock",
    "governed_artifact_contract_for_path",
    "governed_artifact_requires_atomic_replace",
    "governed_artifact_requires_lock",
    "lock_unavailable_reason",
    "open_atomic_temp_file",
    "append_log_only_state_changes",
    "read_optional_text",
    "rollback_file_state",
    "validate_log_entry",
    "write_text_capturing_previous",
    "write_text_capturing_previous_safe",
    "write_text_if_changed",
]
