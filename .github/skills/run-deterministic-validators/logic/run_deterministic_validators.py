"""Read-only runner for allowlisted deterministic validators."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import StrEnum
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_OWNER = "local"
REPO_NAME = re.sub(r"[^A-Za-z0-9_.-]", "-", REPO_ROOT.name) or "repo"


@dataclass(frozen=True, slots=True)
class ValidatorSpec:
    name: str
    script_relative_path: str
    args: tuple[str, ...]

    def to_command(self) -> list[str]:
        return [
            sys.executable,
            str(REPO_ROOT / self.script_relative_path),
            *self.args,
        ]


class ValidatorReasonCode(StrEnum):
    OK = "ok"
    UNKNOWN_VALIDATOR = "unknown_validator"
    VALIDATOR_FAILED = "validator_failed"


VALIDATOR_ALLOWLIST: dict[str, ValidatorSpec] = {
    "qmd-preflight": ValidatorSpec(
        name="qmd-preflight",
        script_relative_path="scripts/kb/qmd_preflight.py",
        args=(
            "--repo-root",
            str(REPO_ROOT),
            "--required-resource",
            ".qmd/index",
        ),
    ),
    "index-check": ValidatorSpec(
        name="index-check",
        script_relative_path="scripts/kb/update_index.py",
        args=("--wiki-root", "wiki", "--check"),
    ),
    "lint-strict": ValidatorSpec(
        name="lint-strict",
        script_relative_path="scripts/kb/lint_wiki.py",
        args=(
            "--wiki-root",
            "wiki",
            "--strict",
            "--authoritative-sourcerefs",
            "--repo-owner",
            REPO_OWNER,
            "--repo-name",
            REPO_NAME,
        ),
    ),
}


def resolve_validators(selected_names: Sequence[str]) -> tuple[ValidatorSpec, ...]:
    if not selected_names:
        return tuple(VALIDATOR_ALLOWLIST.values())

    resolved: list[ValidatorSpec] = []
    for name in selected_names:
        validator = VALIDATOR_ALLOWLIST.get(name)
        if validator is None:
            raise ValueError(f"{ValidatorReasonCode.UNKNOWN_VALIDATOR.value}:{name}")
        resolved.append(validator)
    return tuple(resolved)


def run_validators(selected_names: Sequence[str]) -> tuple[str, ...]:
    validator_specs = resolve_validators(selected_names)
    for validator in validator_specs:
        subprocess.run(
            validator.to_command(),
            cwd=REPO_ROOT,
            check=True,
        )
    return tuple(validator.name for validator in validator_specs)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a deterministic subset of allowlisted validators.")
    parser.add_argument("--validator", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        ran = run_validators(args.validator)
    except ValueError as exc:
        print(json.dumps({"reason_code": ValidatorReasonCode.UNKNOWN_VALIDATOR.value, "message": str(exc)}, sort_keys=True))
        return 2
    except subprocess.CalledProcessError as exc:
        print(
            json.dumps(
                {
                    "reason_code": ValidatorReasonCode.VALIDATOR_FAILED.value,
                    "message": str(exc),
                    "returncode": exc.returncode or 1,
                },
                sort_keys=True,
            )
        )
        return exc.returncode or 1
    print(json.dumps({"reason_code": ValidatorReasonCode.OK.value, "validators": list(ran)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
