"""Normalize bounded markdown structure without performing repository writes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.kb import path_utils

REPO_ROOT = Path(__file__).resolve().parents[4]
ALLOWED_DOC_PREFIXES: tuple[str, ...] = (
    '.github/agents/',
    '.github/skills/',
    'docs/',
    'schema/',
    'wiki/',
)
ALLOWED_DOC_FILES: tuple[str, ...] = ('AGENTS.md', 'README.md')


@dataclass(frozen=True, slots=True)
class MarkdownRepairResult:
    valid: bool
    reason_code: str
    path: str
    changed: bool = False
    normalized_text: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            'valid': self.valid,
            'reason_code': self.reason_code,
            'path': self.path,
            'changed': self.changed,
            'normalized_text': self.normalized_text,
        }


def normalize_repo_relative_path(value: str | Path) -> tuple[str, str | None]:
    normalized, error_kind = path_utils.try_normalize_repo_relative_path(value)
    if error_kind == path_utils.ERROR_KIND_PATH_TRAVERSAL:
        return normalized, 'path_traversal'
    if error_kind == path_utils.ERROR_KIND_INVALID_PATH:
        return normalized, 'invalid_path'
    if Path(normalized).suffix.lower() != '.md':
        return normalized, 'invalid_path'
    if normalized not in ALLOWED_DOC_FILES and not any(
        normalized.startswith(prefix) for prefix in ALLOWED_DOC_PREFIXES
    ):
        return normalized, 'path_not_allowlisted'
    return normalized, None


def normalize_markdown_structure(text: str) -> str:
    raw_text = text.replace('\r\n', '\n').replace('\r', '\n')
    normalized_lines: list[str] = []
    in_fence = False
    last_nonblank: str | None = None
    for raw_line in raw_text.split('\n'):
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith('```'):
            in_fence = not in_fence
            normalized_lines.append(stripped or '```')
            last_nonblank = stripped or last_nonblank
            continue
        if not in_fence and stripped.startswith('#'):
            if last_nonblank == stripped:
                continue
            if normalized_lines and normalized_lines[-1] != '':
                normalized_lines.append('')
            normalized_lines.append(stripped)
            last_nonblank = stripped
            continue
        normalized_lines.append(line)
        if stripped:
            last_nonblank = stripped
    if in_fence:
        normalized_lines.append('```')
    normalized_text = '\n'.join(normalized_lines).rstrip('\n') + '\n'
    return normalized_text


def repair_markdown_structure(
    path: str | Path,
    *,
    repo_root: str | Path = REPO_ROOT,
) -> MarkdownRepairResult:
    normalized_path, path_error = normalize_repo_relative_path(path)
    if path_error is not None:
        return MarkdownRepairResult(False, path_error, str(path))
    source_path = Path(repo_root) / normalized_path
    try:
        original_text = source_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return MarkdownRepairResult(False, 'invalid_path', normalized_path)
    normalized_text = normalize_markdown_structure(original_text)
    return MarkdownRepairResult(
        valid=True,
        reason_code='ok',
        path=normalized_path,
        changed=normalized_text != original_text,
        normalized_text=normalized_text,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Normalize bounded markdown structure without writing changes.')
    parser.add_argument('--path', required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    result = repair_markdown_structure(args.path)
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0 if result.valid else 1


if __name__ == '__main__':
    raise SystemExit(main())
