"""Thin state-sync wrapper over allowlisted knowledgebase scripts."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_OWNER = "local"
REPO_NAME = re.sub(r"[^A-Za-z0-9_.-]", "-", REPO_ROOT.name) or "repo"
WIKI_ROOT = "wiki"
QMD_REQUIRED_RESOURCE = ".qmd/index"


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Synchronize deterministic wiki state using fixed allowlisted "
            "knowledgebase entrypoints."
        )
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
    return parser


def run_prechecks(*, write_index: bool) -> None:
    command_specs = WRITE_PRECHECKS if write_index else READ_ONLY_PRECHECKS
    for command_spec in command_specs:
        subprocess.run(
            command_spec.to_command(),
            cwd=REPO_ROOT,
            check=True,
        )


def run_sync(*, write_index: bool) -> None:
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
    try:
        run_sync(write_index=bool(args.write_index))
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
