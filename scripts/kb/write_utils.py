"""Write-path lock and state-change logging helpers."""

from __future__ import annotations

import contextlib
from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import fcntl
import hashlib
import os
from os import PathLike
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Iterator, Sequence, TextIO

from . import contracts
from . import path_utils


LOG_PATH = Path("wiki/log.md")
# Single-threaded reentrancy tracker for CLI surfaces. Do not call
# exclusive_write_lock concurrently from multiple threads without adding a
# threading.Lock around this counter.
_HELD_LOCK_COUNTS: dict[Path, int] = {}
_LOCK_UNAVAILABLE_HINT = (
    "retry after the competing process completes, or remove the lock file if it is stale"
)


def _resolved_governance_sibling_locks(repo_root: Path) -> dict[Path, str]:
    """Map resolved sibling lock paths to canonical contract lock paths."""
    return {
        (repo_root / lock_path).resolve(strict=False): lock_path
        for lock_path in contracts.GOVERNANCE_SIBLING_LOCKS
    }


def _can_cohold_with_held_sibling(target_lock_path: str, held_sibling_lock_path: str) -> bool:
    """Allow approved same-process lock nesting with enforced acquisition order."""
    return (
        held_sibling_lock_path == contracts.WRITE_LOCK_PATH
        and target_lock_path
        in {
            contracts.GITHUB_SOURCES_LOCK_PATH,
            contracts.DRIVE_SOURCES_LOCK_PATH,
        }
    )


def governed_artifact_contract_for_path(
    path: str | PathLike[str],
) -> contracts.GovernedArtifactContract | None:
    """Return the governed artifact contract for a repo-relative path, if any.

    Uses glob-pattern matching so dynamic artifact families (e.g.,
    ``raw/github-sources/*.source-registry.json``, ``raw/assets/**``) resolve
    correctly via ``governed_artifact_contract_by_pattern()``.
    """
    try:
        normalized_path = path_utils.normalize_repo_relative_path(path)
    except path_utils.RepoRelativePathError:
        return None
    return contracts.governed_artifact_contract_by_pattern(normalized_path)


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


def _check_no_symlink_path_within_root(repo_root: Path, path: Path) -> None:
    """Reject symlink components below *repo_root* without following system-level symlinks."""

    root = repo_root.resolve(strict=False)
    candidate = path if path.is_absolute() else root / path
    resolved_candidate = candidate.resolve(strict=False)
    if not resolved_candidate.is_relative_to(root):
        raise OSError(f"path escapes repository root: {path}")
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise OSError(f"path is not under repository root: {path}") from exc
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise OSError(f"symlinked path component is not allowed: {current}")


class LockUnavailableError(RuntimeError):
    """Raised when the write lock cannot be acquired."""

    reason_code: str
    failure_reason: str
    holder_pid: int | None
    holder_alive: bool | None
    holder_started_at: str | None
    holder_context_hash: str | None

    def __init__(
        self,
        lock_path: str = contracts.WRITE_LOCK_PATH,
        lock_file_path: Path | None = None,
    ) -> None:
        self.reason_code = contracts.ReasonCode.LOCK_UNAVAILABLE.value
        self.failure_reason = lock_unavailable_reason(lock_path)
        self.holder_pid = None
        self.holder_alive = None
        self.holder_started_at = None
        self.holder_context_hash = None

        holder_details = _read_lock_holder_details(lock_file_path or Path(lock_path))
        if holder_details is None:
            super().__init__(f"{self.failure_reason} — {_LOCK_UNAVAILABLE_HINT}")
            return

        self.holder_pid = holder_details.pid
        self.holder_started_at = _format_unix_seconds_utc(holder_details.started_at_unix_seconds)
        self.holder_context_hash = _lock_holder_context_hash(holder_details)
        holder_alive = _holder_process_is_alive(
            holder_details.pid,
            expected_started_at_unix_seconds=holder_details.started_at_unix_seconds,
        )
        self.holder_alive = holder_alive

        hash_hint = self.holder_context_hash or "unavailable"
        inspect_hint = (
            f"inspect {lock_path} directly for holder metadata"
            if lock_path
            else "inspect the lock file directly for holder metadata"
        )
        if holder_alive is True:
            super().__init__(
                f"{self.failure_reason} — lock contention active "
                f"(context sha256:{hash_hint}); retry shortly and {inspect_hint}"
            )
            return
        if holder_alive is False:
            super().__init__(
                f"{self.failure_reason} — lock contention active but holder metadata appears stale/reused "
                f"(context sha256:{hash_hint}); retry and {inspect_hint}"
            )
            return
        super().__init__(
            f"{self.failure_reason} — lock contention active with unverifiable holder metadata "
            f"(context sha256:{hash_hint}); {inspect_hint}"
        )


class _LockHolderDetails:
    """Parsed lock-holder metadata from a lock file line."""

    def __init__(self, pid: int, started_at_unix_seconds: float) -> None:
        self.pid = pid
        self.started_at_unix_seconds = started_at_unix_seconds


def _format_unix_seconds_utc(unix_seconds: float) -> str:
    """Render unix seconds as UTC ISO-8601 (`YYYY-MM-DDTHH:MM:SSZ`)."""

    return datetime.fromtimestamp(unix_seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lock_holder_context_hash(holder_details: _LockHolderDetails) -> str:
    """Return canonical lock-holder context hash as lower-case 64-hex SHA-256.

    Canonical payload format is exactly ``<pid>\\t<start_time_unix_seconds:.6f>\\n``.
    """

    canonical_payload = f"{holder_details.pid}\t{holder_details.started_at_unix_seconds:.6f}\n"
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def _linux_boot_time_unix_seconds() -> float | None:
    """Return Linux boot time from `/proc/stat` (`btime`), else ``None``."""

    try:
        with Path("/proc/stat").open(encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("btime "):
                    return float(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _linux_pid_start_time_unix_seconds(pid: int) -> float | None:
    """Return Linux process start time as unix seconds, else ``None``."""

    if pid <= 0:
        return None
    boot_time = _linux_boot_time_unix_seconds()
    if boot_time is None:
        return None
    try:
        stat_text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        right_paren = stat_text.rfind(")")
        if right_paren == -1:
            return None
        stat_fields = stat_text[right_paren + 2 :].split()
        if len(stat_fields) < 20:
            return None
        # /proc/<pid>/stat field 22 (starttime) becomes index 19 after dropping pid+comm.
        start_ticks = int(stat_fields[19])
        ticks_per_second = int(os.sysconf("SC_CLK_TCK"))
        if ticks_per_second <= 0:
            return None
    except (OSError, ValueError, TypeError):
        return None
    return boot_time + (start_ticks / ticks_per_second)


def _darwin_pid_start_time_unix_seconds(pid: int) -> float | None:
    """Return Darwin process start time as unix seconds, else ``None``."""

    if pid <= 0:
        return None
    try:
        completed = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    lstart_text = completed.stdout.strip()
    if not lstart_text:
        return None
    try:
        parsed = datetime.strptime(lstart_text, "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return None
    local_tz = datetime.now().astimezone().tzinfo
    if local_tz is None:
        return None
    return parsed.replace(tzinfo=local_tz).timestamp()


def _pid_start_time_unix_seconds(pid: int) -> float | None:
    """Return platform-aware process start time as unix seconds, else ``None``."""

    if sys.platform.startswith("linux"):
        return _linux_pid_start_time_unix_seconds(pid)
    if sys.platform == "darwin":
        return _darwin_pid_start_time_unix_seconds(pid)
    return None


def _current_process_start_time_unix_seconds() -> float:
    """Return current-process start time, falling back to ``time.time()``."""

    started_at = _pid_start_time_unix_seconds(os.getpid())
    if started_at is not None:
        return started_at
    return time.time()


def _write_lock_holder_details(lock_file: TextIO) -> None:
    """Overwrite lock metadata with ``<pid>\\t<start_time_unix_seconds>``."""

    holder_pid = os.getpid()
    holder_started_at = _current_process_start_time_unix_seconds()
    lock_file.seek(0)
    lock_file.truncate()
    lock_file.write(f"{holder_pid}\t{holder_started_at:.6f}\n")
    lock_file.flush()


def _read_lock_holder_details(lock_file_path: Path) -> _LockHolderDetails | None:
    """Parse lock metadata from ``lock_file_path``.

    Returns ``None`` when the file cannot be read, is empty, or is malformed.
    """

    try:
        line = lock_file_path.read_text(encoding="utf-8").splitlines()[0].strip()
    except IndexError:
        return None
    except OSError:
        return None

    if not line:
        return None
    try:
        pid_text, started_at_text = line.split("\t", 1)
        pid = int(pid_text)
        started_at = float(started_at_text)
    except (ValueError, TypeError):
        return None
    if pid <= 0:
        return None
    return _LockHolderDetails(pid=pid, started_at_unix_seconds=started_at)


def _holder_process_is_alive(pid: int, *, expected_started_at_unix_seconds: float) -> bool | None:
    """Return holder liveness: ``True`` alive, ``False`` dead/reused, ``None`` unknown."""

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        if exc.errno == errno.EPERM:
            return True
        return None

    observed_start = _pid_start_time_unix_seconds(pid)
    if observed_start is None:
        return None
    if (
        abs(observed_start - expected_started_at_unix_seconds)
        >= _pid_start_time_tolerance_seconds()
    ):
        # PID reuse: the currently alive process is not the lock holder recorded in the file.
        return False
    return True


def _pid_start_time_tolerance_seconds() -> float:
    """Return start-time comparison tolerance based on Linux clock-tick precision."""

    if sys.platform.startswith("linux"):
        try:
            ticks_per_second = float(int(os.sysconf("SC_CLK_TCK")))
        except (OSError, ValueError, TypeError):
            return 1e-6
        if ticks_per_second <= 0:
            return 1e-6
        return max(1e-6, 0.5 / ticks_per_second)
    if sys.platform == "darwin":
        return 1e-6
    return 1e-6


def _open_lock_file(
    repo_root: Path,
    lock_path: str,
    *,
    create: bool,
) -> tuple[Path, Path, TextIO]:
    """Open a lock file under *repo_root* and return ``(abs, resolved, handle)``."""
    abs_lock = repo_root / lock_path
    resolved_lock = abs_lock.resolve(strict=False)
    _check_no_symlink_path_within_root(repo_root, abs_lock)
    if not resolved_lock.is_relative_to(repo_root):
        raise OSError(f"lock path escapes repository root: {lock_path}")
    if create:
        abs_lock.parent.mkdir(parents=True, exist_ok=True)
        _check_no_symlink_path_within_root(repo_root, abs_lock)
    flags = os.O_RDWR | (os.O_CREAT if create else 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(abs_lock, flags, 0o600)
    return abs_lock, resolved_lock, os.fdopen(fd, "a+", encoding="utf-8")


def _acquire_sibling_governance_lock(
    repo_root: Path,
    lock_path: str,
    lock_file: TextIO,
) -> None:
    """Acquire a sibling governance lock using the meta-lock protocol."""
    _, _, meta_lock_file = _open_lock_file(
        repo_root,
        contracts.GOVERNANCE_META_LOCK_PATH,
        create=True,
    )
    with meta_lock_file:
        try:
            fcntl.flock(meta_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise LockUnavailableError(contracts.GOVERNANCE_META_LOCK_PATH) from exc
        try:
            for sibling_lock_path in sorted(contracts.GOVERNANCE_SIBLING_LOCKS):
                if sibling_lock_path == lock_path:
                    continue
                sibling_resolved = (repo_root / sibling_lock_path).resolve(strict=False)
                if sibling_resolved in _HELD_LOCK_COUNTS:
                    if _can_cohold_with_held_sibling(lock_path, sibling_lock_path):
                        continue
                    raise LockUnavailableError(sibling_lock_path)
                try:
                    _, _, sibling_lock_file = _open_lock_file(
                        repo_root,
                        sibling_lock_path,
                        create=False,
                    )
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    raise LockUnavailableError(sibling_lock_path) from exc
                with sibling_lock_file:
                    try:
                        fcntl.flock(sibling_lock_file.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                    except OSError as exc:
                        raise LockUnavailableError(sibling_lock_path) from exc
                    finally:
                        with contextlib.suppress(OSError):
                            fcntl.flock(sibling_lock_file.fileno(), fcntl.LOCK_UN)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise LockUnavailableError(lock_path) from exc
        finally:
            with contextlib.suppress(OSError):
                fcntl.flock(meta_lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def exclusive_write_lock(
    repo_root: str | Path = ".",
    lock_path: str = contracts.WRITE_LOCK_PATH,
) -> Iterator[Path]:
    """Acquire an exclusive non-blocking write lock.

    Uses *lock_path* relative to *repo_root*.  Defaults to the wiki write
    lock (``wiki/.kb_write.lock``).  Pass
    ``lock_path=contracts.GITHUB_SOURCES_LOCK_PATH`` for the separate
    registry lock used by the github_monitor script family.

    A pre-existing unlocked lock file is treated as stale metadata and does not
    block acquisition; only an active advisory lock fails closed.
    """
    root = Path(repo_root).resolve(strict=False)
    abs_lock = root / lock_path
    resolved_lock = abs_lock.resolve(strict=False)
    if resolved_lock in _HELD_LOCK_COUNTS:
        _HELD_LOCK_COUNTS[resolved_lock] += 1
        try:
            yield abs_lock
        finally:
            remaining = _HELD_LOCK_COUNTS.get(resolved_lock, 0) - 1
            if remaining > 0:
                _HELD_LOCK_COUNTS[resolved_lock] = remaining
            else:
                _HELD_LOCK_COUNTS.pop(resolved_lock, None)
        return

    try:
        abs_lock, resolved_lock, lock_file = _open_lock_file(root, lock_path, create=True)
    except OSError as exc:
        raise LockUnavailableError(lock_path) from exc

    resolved_sibling_locks = _resolved_governance_sibling_locks(root)
    canonical_lock_path = resolved_sibling_locks.get(resolved_lock)

    with lock_file:
        if canonical_lock_path is not None:
            _acquire_sibling_governance_lock(
                root,
                canonical_lock_path,
                lock_file,
            )
        else:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise LockUnavailableError(lock_path, lock_file_path=abs_lock) from exc
        _write_lock_holder_details(lock_file)

        try:
            _HELD_LOCK_COUNTS[resolved_lock] = _HELD_LOCK_COUNTS.get(resolved_lock, 0) + 1
            yield abs_lock
        finally:
            remaining = _HELD_LOCK_COUNTS.get(resolved_lock, 0) - 1
            if remaining > 0:
                _HELD_LOCK_COUNTS[resolved_lock] = remaining
            else:
                _HELD_LOCK_COUNTS.pop(resolved_lock, None)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def is_write_lock_held(
    repo_root: str | Path = ".",
    lock_path: str = contracts.WRITE_LOCK_PATH,
) -> bool:
    """Return whether this process currently holds *lock_path* via this module."""

    return (Path(repo_root) / lock_path).resolve(strict=False) in _HELD_LOCK_COUNTS


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

    root = Path(repo_root).resolve(strict=False)
    target_path = root / contract.path
    _check_no_symlink_path_within_root(root, target_path)
    resolved_target = target_path.resolve(strict=False)
    if not resolved_target.is_relative_to(root):
        raise ValueError(f"artifact path escapes repository root: {contract.path}")
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

    root = Path(repo_root).resolve(strict=False)
    log_path = root / LOG_PATH
    resolved_log = log_path.resolve(strict=False)
    _check_no_symlink_path_within_root(root, log_path)
    if not resolved_log.is_relative_to(root):
        raise OSError(f"log path escapes repository root: {LOG_PATH}")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _check_no_symlink_path_within_root(root, log_path)
    normalized_entry = entry.rstrip("\n") + "\n"

    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(log_path, flags, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as log_file:
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


def exclusive_create_write_once(path: Path, data: bytes) -> None:
    """Write binary *data* to *path* using exclusive-create semantics.

    Intended for write-once assets whose path encodes content identity (e.g.,
    ``raw/assets/{owner}/{repo}/{commit_sha}/{file}``).  Two concurrent calls
    with the same path and identical bytes both succeed without error; a path
    that already exists with *different* bytes is a hard failure.

    Behaviour:
    - Rejects symlinks anywhere in the resolved path chain.
    - If *path* does not exist: creates parent directories, writes *data* to a
      temp file in the same directory, then atomically hardlinks it to *path*
      via ``os.link()`` (which fails with ``FileExistsError`` if the target
      already exists, giving O_EXCL semantics while protecting against
      partial-write poison on process interruption).
    - If *path* already exists (including the TOCTOU case where a concurrent
      process won the link race): computes sha256 of the existing bytes and
      compares to sha256 of *data*.  Matching sha256 → silent no-op.
      Mismatched sha256 → raises ``OSError`` (fail closed).
    - The temp file is always removed in a ``finally`` block, so an interrupted
      write does not leave a poisoned path at the target location.
    """
    check_no_symlink_path(path)

    def _sha256_hex(b: bytes) -> str:
        return hashlib.sha256(b).hexdigest()

    def _check_existing(p: Path) -> None:
        existing = p.read_bytes()
        if _sha256_hex(existing) != _sha256_hex(data):
            raise OSError(
                f"exclusive_create_write_once: path exists with mismatched bytes: {p}"
            )

    if path.exists():
        _check_existing(path)
        return

    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to a sibling temp file, then hardlink atomically to the target.
    # os.link() is atomic on POSIX and fails with FileExistsError if the target
    # already exists — giving O_EXCL semantics.  Because the temp file is fully
    # written before os.link(), a process interruption at any point leaves the
    # target path either uncreated or verifiably complete; there is no partial-
    # write poison scenario.
    fd, tmp_str = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    tmp = Path(tmp_str)
    try:
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        try:
            os.link(tmp, path)
        except FileExistsError:
            # Another process created the target between our exists() check and
            # the hardlink attempt; verify the bytes are identical.
            _check_existing(path)
    finally:
        tmp.unlink(missing_ok=True)


__all__ = [
    "check_no_symlink_path",
    "exclusive_create_write_once",
    "LockUnavailableError",
    "atomic_replace_governed_artifact",
    "exclusive_write_lock",
    "governed_artifact_contract_for_path",
    "governed_artifact_requires_atomic_replace",
    "governed_artifact_requires_lock",
    "is_write_lock_held",
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
