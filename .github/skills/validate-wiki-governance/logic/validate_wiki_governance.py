"""Read-only governance validation wrapper over allowlisted knowledgebase scripts."""

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


READ_ONLY_VALIDATORS: tuple[CommandSpec, ...] = (
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


def _build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description=(
            "Run fixed, read-only governance validation over allowlisted "
            "knowledgebase entrypoints."
        )
    )


def run_validation() -> None:
    for command_spec in READ_ONLY_VALIDATORS:
        subprocess.run(
            command_spec.to_command(),
            cwd=REPO_ROOT,
            check=True,
        )


def main(argv: Sequence[str] | None = None) -> int:
    _build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        run_validation()
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
