"""Append-only wiki/log.md helper for state changes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import StrEnum
import json
from pathlib import Path
import sys
from typing import Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.kb import write_utils

REPO_ROOT = Path(__file__).resolve().parents[4]


class LogReasonCode(StrEnum):
    OK = "ok"
    INVALID_ENTRY = "invalid_entry"
    LOCK_UNAVAILABLE = "lock_unavailable"


class LogAppendError(ValueError):
    def __init__(self, reason_code: LogReasonCode | str, message: str) -> None:
        self.reason_code = str(reason_code)
        super().__init__(f"{self.reason_code}: {message}")


@dataclass(frozen=True, slots=True)
class LogAppendResult:
    appended: bool
    log_path: str

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "appended": self.appended,
            "log_path": self.log_path,
        }


def append_log_entry(
    entry: str,
    *,
    state_changed: bool,
    repo_root: str | Path = REPO_ROOT,
) -> LogAppendResult:
    try:
        normalized_entry = write_utils.validate_log_entry(entry)
    except ValueError as exc:
        raise LogAppendError(LogReasonCode.INVALID_ENTRY, str(exc)) from exc
    log_path = (Path(repo_root) / write_utils.LOG_PATH).as_posix()
    if not state_changed:
        return LogAppendResult(appended=False, log_path=log_path)

    with write_utils.exclusive_write_lock(repo_root):
        appended = write_utils.append_log_only_state_changes(
            repo_root,
            normalized_entry,
            state_changed=True,
        )
    return LogAppendResult(appended=appended, log_path=log_path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Append a deterministic wiki/log.md entry.")
    parser.add_argument("--entry", required=True)
    parser.add_argument("--state-changed", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = append_log_entry(
            args.entry,
            state_changed=bool(args.state_changed),
        )
    except LogAppendError as exc:
        print(json.dumps({"reason_code": exc.reason_code, "message": str(exc)}, sort_keys=True))
        return 1
    except write_utils.LockUnavailableError as exc:
        print(
            json.dumps(
                {
                    "reason_code": LogReasonCode.LOCK_UNAVAILABLE.value,
                    "message": str(exc),
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
