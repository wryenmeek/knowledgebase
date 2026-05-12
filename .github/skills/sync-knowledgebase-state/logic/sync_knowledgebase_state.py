"""Thin state-sync wrapper over allowlisted knowledgebase scripts."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import re
import subprocess
import sys
from typing import Sequence

if __package__ in (None, ""):  # supports both 'python -m' and direct invocation without package install
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.kb import contracts, path_utils, write_utils


REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_OWNER = "local"
REPO_NAME = re.sub(r"[^A-Za-z0-9_.-]", "-", REPO_ROOT.name) or "repo"
WIKI_ROOT = "wiki"
QMD_REQUIRED_RESOURCE = ".qmd/index"
INDEX_ARTIFACT = "wiki/index.md"
LOG_ARTIFACT = "wiki/log.md"
OPEN_QUESTIONS_ARTIFACT = "wiki/open-questions.md"
BACKLOG_ARTIFACT = "wiki/backlog.md"
STATUS_ARTIFACT = "wiki/status.md"
SUPPORTED_ARTIFACTS: tuple[str, ...] = contracts.GOVERNED_ARTIFACT_PATHS


class SyncReasonCode(StrEnum):
    INVALID_ARGUMENTS = "invalid_arguments"
    UNSUPPORTED_ARTIFACT = "unsupported_artifact"


class SyncArgumentError(ValueError):
    def __init__(self, reason_code: SyncReasonCode | str, message: str) -> None:
        self.reason_code = str(reason_code)
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class CommandSpec:
    script_relative_path: str
    args: tuple[str, ...]

    def to_command(self) -> list[str]:
        return [
            sys.executable,
            str(REPO_ROOT / self.script_relative_path),
            *self.args,
        ]


@dataclass(frozen=True, slots=True)
class SnapshotWriteMode:
    flag: str
    dest: str
    artifact_path: str
    help_text: str


READ_ONLY_PRECHECKS: tuple[CommandSpec, ...] = (
    CommandSpec(
        script_relative_path="scripts/kb/qmd_preflight.py",
        args=(
            "--repo-root",
            str(REPO_ROOT),
            "--required-resource",
            QMD_REQUIRED_RESOURCE,
        ),
    ),
    CommandSpec(
        script_relative_path="scripts/kb/update_index.py",
        args=("--wiki-root", WIKI_ROOT, "--check"),
    ),
    CommandSpec(
        script_relative_path="scripts/kb/lint_wiki.py",
        args=(
            "--wiki-root",
            WIKI_ROOT,
            "--strict",
            "--authoritative-sourcerefs",
            "--repo-owner",
            REPO_OWNER,
            "--repo-name",
            REPO_NAME,
        ),
    ),
)
WRITE_PRECHECKS: tuple[CommandSpec, ...] = (
    READ_ONLY_PRECHECKS[0],
    CommandSpec(
        script_relative_path="scripts/kb/lint_wiki.py",
        args=(
            "--wiki-root",
            WIKI_ROOT,
            "--strict",
            "--skip-orphan-check",
            "--authoritative-sourcerefs",
            "--repo-owner",
            REPO_OWNER,
            "--repo-name",
            REPO_NAME,
        ),
    ),
)
WRITE_POSTCHECKS: tuple[CommandSpec, ...] = (
    CommandSpec(
        script_relative_path="scripts/kb/lint_wiki.py",
        args=(
            "--wiki-root",
            WIKI_ROOT,
            "--strict",
            "--authoritative-sourcerefs",
            "--repo-owner",
            REPO_OWNER,
            "--repo-name",
            REPO_NAME,
        ),
    ),
)
WRITE_INDEX_COMMAND = CommandSpec(
    script_relative_path="scripts/kb/update_index.py",
    args=("--wiki-root", WIKI_ROOT, "--write"),
)
SNAPSHOT_WRITE_MODES: tuple[SnapshotWriteMode, ...] = (
    SnapshotWriteMode(
        flag="--write-open-questions-from",
        dest="write_open_questions_from",
        artifact_path=OPEN_QUESTIONS_ARTIFACT,
        help_text="Atomically publish wiki/open-questions.md from a staged repo-relative file.",
    ),
    SnapshotWriteMode(
        flag="--write-backlog-from",
        dest="write_backlog_from",
        artifact_path=BACKLOG_ARTIFACT,
        help_text="Atomically publish wiki/backlog.md from a staged repo-relative file.",
    ),
    SnapshotWriteMode(
        flag="--write-status-from",
        dest="write_status_from",
        artifact_path=STATUS_ARTIFACT,
        help_text="Atomically publish wiki/status.md from a staged repo-relative file.",
    ),
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Synchronize deterministic wiki state using fixed allowlisted "
            "knowledgebase entrypoints."
        )
    )
    parser.add_argument(
        "--artifact",
        default=INDEX_ARTIFACT,
        help=(
            "Governed artifact path for --check-only. Supported values: "
            + ", ".join(SUPPORTED_ARTIFACTS)
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check-only",
        action="store_true",
        help="Run read-only prechecks only (default behavior).",
    )
    mode.add_argument(
        "--write-index",
        action="store_true",
        help="Write wiki/index.md only after all read-only prechecks pass.",
    )
    mode.add_argument(
        "--append-log-entry",
        metavar="ENTRY",
        help="Append a single wiki/log.md bullet entry under the write lock.",
    )
    for snapshot_write_mode in SNAPSHOT_WRITE_MODES:
        mode.add_argument(
            snapshot_write_mode.flag,
            dest=snapshot_write_mode.dest,
            metavar="PATH",
            help=snapshot_write_mode.help_text,
        )
    parser.add_argument(
        "--state-changed",
        action="store_true",
        help="Required signal for append-only log writes; false means no-op.",
    )
    return parser


def run_prechecks(*, write_index: bool) -> None:
    command_specs = WRITE_PRECHECKS if write_index else READ_ONLY_PRECHECKS
    for command_spec in command_specs:
        subprocess.run(
            command_spec.to_command(),
            cwd=REPO_ROOT,
            check=True,
        )


def _validate_supported_artifact(path: str) -> str:
    normalized = path.strip()
    if normalized not in SUPPORTED_ARTIFACTS:
        raise SyncArgumentError(
            SyncReasonCode.UNSUPPORTED_ARTIFACT,
            f"unsupported governed artifact: {path}",
        )
    return normalized


def _assert_no_symlink_components(path: str) -> None:
    raw_path = Path(path)
    candidate_path = REPO_ROOT
    for part in raw_path.parts:
        candidate_path /= part
        if candidate_path.is_symlink():
            raise SyncArgumentError(
                SyncReasonCode.INVALID_ARGUMENTS,
                f"staged source must be a regular repo file: {path}",
            )


def _read_staged_repo_file(path: str) -> str:
    try:
        normalized_path = path_utils.normalize_repo_relative_path(path)
    except path_utils.RepoRelativePathError as exc:
        raise SyncArgumentError(
            SyncReasonCode.INVALID_ARGUMENTS,
            str(exc),
        ) from exc
    _assert_no_symlink_components(normalized_path)
    candidate_path = REPO_ROOT / normalized_path
    staged_path = candidate_path.resolve()
    repo_root = REPO_ROOT.resolve()
    if not staged_path.is_file():
        raise SyncArgumentError(
            SyncReasonCode.INVALID_ARGUMENTS,
            f"staged source must be a regular repo file: {path}",
        )
    try:
        staged_path.relative_to(repo_root)
    except ValueError as exc:
        raise SyncArgumentError(
            SyncReasonCode.INVALID_ARGUMENTS,
            f"staged source must stay within the repository: {path}",
        ) from exc
    return staged_path.read_text(encoding="utf-8")


def append_log_entry(entry: str, *, state_changed: bool) -> bool:
    try:
        normalized_entry = write_utils.validate_log_entry(entry)
    except ValueError as exc:
        raise SyncArgumentError(SyncReasonCode.INVALID_ARGUMENTS, str(exc)) from exc
    if not state_changed:
        return False
    with write_utils.exclusive_write_lock(REPO_ROOT):
        return write_utils.append_log_only_state_changes(
            REPO_ROOT,
            normalized_entry,
            state_changed=True,
        )


def publish_snapshot_artifact(*, artifact_path: str, staged_source_path: str) -> Path:
    supported_artifact = _validate_supported_artifact(artifact_path)
    content = _read_staged_repo_file(staged_source_path)
    with write_utils.exclusive_write_lock(REPO_ROOT):
        return write_utils.atomic_replace_governed_artifact(
            REPO_ROOT,
            supported_artifact,
            content,
        )


def resolve_snapshot_write_request(args: argparse.Namespace) -> tuple[str, str] | None:
    for snapshot_write_mode in SNAPSHOT_WRITE_MODES:
        staged_source_path = getattr(args, snapshot_write_mode.dest)
        if staged_source_path is not None:
            return snapshot_write_mode.artifact_path, staged_source_path
    return None


def run_sync(*, artifact: str, write_index: bool) -> None:
    supported_artifact = _validate_supported_artifact(artifact)
    if supported_artifact != INDEX_ARTIFACT:
        if write_index:
            raise SyncArgumentError(
                SyncReasonCode.INVALID_ARGUMENTS,
                "--write-index only supports wiki/index.md",
            )
        return
    run_prechecks(write_index=write_index)
    if write_index:
        subprocess.run(
            WRITE_INDEX_COMMAND.to_command(),
            cwd=REPO_ROOT,
            check=True,
        )
        for command_spec in WRITE_POSTCHECKS:
            subprocess.run(
                command_spec.to_command(),
                cwd=REPO_ROOT,
                check=True,
            )


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    snapshot_write_request = resolve_snapshot_write_request(args)
    try:
        if args.append_log_entry is not None:
            append_log_entry(args.append_log_entry, state_changed=bool(args.state_changed))
        elif snapshot_write_request is not None:
            artifact_path, staged_source_path = snapshot_write_request
            publish_snapshot_artifact(
                artifact_path=artifact_path,
                staged_source_path=staged_source_path,
            )
        else:
            run_sync(
                artifact=args.artifact,
                write_index=bool(args.write_index),
            )
    except (SyncArgumentError, write_utils.LockUnavailableError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
