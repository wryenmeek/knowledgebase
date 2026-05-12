"""Validate bounded markdown batches with structure and link checks."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Sequence

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from repair_markdown_structure import REPO_ROOT, repair_markdown_structure

MARKDOWN_LINK_RE = re.compile(r'(?<!!)\[[^\]]+\]\(([^)]+)\)')


@dataclass(frozen=True, slots=True)
class DocValidationResult:
    path: str
    valid: bool
    reason_code: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            'path': self.path,
            'valid': self.valid,
            'reason_code': self.reason_code,
            'message': self.message,
        }


@dataclass(frozen=True, slots=True)
class DocBatchResult:
    valid: bool
    reason_code: str
    results: tuple[DocValidationResult, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            'valid': self.valid,
            'reason_code': self.reason_code,
            'results': [result.to_dict() for result in self.results],
        }


def _normalize_internal_target(source_path: str, raw_target: str) -> str | None:
    target = raw_target.split('#', 1)[0].split('?', 1)[0].strip()
    if not target or '://' in target or target.startswith('mailto:') or target.startswith('tel:'):
        return None
    source_parent = PurePosixPath(source_path).parent
    candidate = PurePosixPath(target)
    if not candidate.is_absolute():
        candidate = source_parent / candidate
    normalized = candidate.as_posix().lstrip('/')
    suffix = Path(normalized).suffix.lower()
    if suffix and suffix != '.md':
        return None
    if not suffix:
        normalized = f'{normalized}.md'
    return normalized


def validate_doc_batch(
    paths: Sequence[str],
    *,
    repo_root: str | Path = REPO_ROOT,
) -> DocBatchResult:
    repo_root_path = Path(repo_root)
    results: list[DocValidationResult] = []
    for raw_path in paths:
        repair_result = repair_markdown_structure(raw_path, repo_root=repo_root_path)
        if not repair_result.valid:
            results.append(
                DocValidationResult(
                    path=str(raw_path),
                    valid=False,
                    reason_code=repair_result.reason_code,
                    message='document path is outside the declared markdown validation surface',
                )
            )
            continue
        if repair_result.changed or repair_result.normalized_text is None:
            results.append(
                DocValidationResult(
                    path=repair_result.path,
                    valid=False,
                    reason_code='needs_repair',
                    message='document requires deterministic markdown repair before batch validation',
                )
            )
            continue
        missing_link: str | None = None
        for raw_target in MARKDOWN_LINK_RE.findall(repair_result.normalized_text):
            normalized_target = _normalize_internal_target(repair_result.path, raw_target)
            if normalized_target is None:
                continue
            if not (repo_root_path / normalized_target).exists():
                missing_link = normalized_target
                break
        if missing_link is not None:
            results.append(
                DocValidationResult(
                    path=repair_result.path,
                    valid=False,
                    reason_code='missing_link',
                    message=f'internal markdown link target does not exist: {missing_link}',
                )
            )
            continue
        results.append(
            DocValidationResult(
                path=repair_result.path,
                valid=True,
                reason_code='ok',
                message='document batch validation passed',
            )
        )
    batch_valid = bool(results) and all(result.valid for result in results)
    return DocBatchResult(
        valid=batch_valid,
        reason_code='ok' if batch_valid else 'batch_invalid',
        results=tuple(results),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Validate a bounded markdown batch.')
    parser.add_argument('--path', action='append', required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_doc_batch(tuple(args.path))
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0 if result.valid else 1


if __name__ == '__main__':
    raise SystemExit(main())
