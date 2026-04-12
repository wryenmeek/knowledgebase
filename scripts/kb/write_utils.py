"""Write-path lock and state-change logging helpers."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
from pathlib import Path
from typing import Iterator

from . import contracts


LOG_PATH = Path("wiki/log.md")


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
    """Acquire an exclusive non-blocking write lock for wiki mutations."""
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


__all__ = [
    "LockUnavailableError",
    "exclusive_write_lock",
    "lock_unavailable_reason",
    "append_log_only_state_changes",
]
