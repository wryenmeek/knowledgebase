"""Write-path lock and state-change logging helpers."""

from __future__ import annotations

import contextlib
from contextlib import contextmanager
import fcntl
import os
from os import PathLike
from pathlib import Path
from typing import Iterator

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
        super().__init__(self.failure_reason)


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
        with _open_atomic_temp_path(temp_path) as handle:
            handle.write(content)
        os.replace(temp_path, target_path)
    except OSError:
        with contextlib.suppress(OSError):
            temp_path.unlink()
        raise

    return target_path


def _open_atomic_temp_path(temp_path: Path):
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
    "LockUnavailableError",
    "atomic_replace_governed_artifact",
    "exclusive_write_lock",
    "governed_artifact_contract_for_path",
    "governed_artifact_requires_atomic_replace",
    "governed_artifact_requires_lock",
    "lock_unavailable_reason",
    "append_log_only_state_changes",
    "validate_log_entry",
]
