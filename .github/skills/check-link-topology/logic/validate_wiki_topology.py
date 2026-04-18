"""Validate bounded wiki topology expectations without mutating the graph."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.kb import path_utils

REPO_ROOT = Path(__file__).resolve().parents[4]
MARKDOWN_LINK_RE = re.compile(r'(?<!!)\[[^\]]+\]\(([^)]+)\)')
EXEMPT_ORPHAN_PATHS = {'wiki/index.md', 'wiki/log.md'}
REQUIRED_CONTROL_ARTIFACTS = ('wiki/index.md', 'wiki/log.md')


@dataclass(frozen=True, slots=True)
class TopologyViolation:
    page: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {'page': self.page, 'code': self.code, 'message': self.message}


@dataclass(frozen=True, slots=True)
class TopologyValidationResult:
    valid: bool
    reason_code: str
    violations: tuple[TopologyViolation, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            'valid': self.valid,
            'reason_code': self.reason_code,
            'violations': [violation.to_dict() for violation in self.violations],
        }


def _normalize_repo_relative_path(value: str | Path) -> tuple[str, str | None]:
    normalized, error_kind = path_utils.try_normalize_repo_relative_path(value)
    if error_kind == path_utils.ERROR_KIND_PATH_TRAVERSAL:
        return normalized, 'path_traversal'
    if error_kind == path_utils.ERROR_KIND_INVALID_PATH:
        return normalized, 'invalid_path'
    if not normalized.startswith('wiki/') or not normalized.endswith('.md'):
        return normalized, 'path_not_allowlisted'
    return normalized, None


def _discover_scope(repo_root: Path, scoped_paths: Sequence[str]) -> tuple[str, ...] | str:
    if not scoped_paths:
        return tuple(
            path.relative_to(repo_root).as_posix()
            for path in sorted((repo_root / 'wiki').rglob('*.md'))
            if path.is_file()
        )
    normalized_paths: list[str] = []
    for raw_path in scoped_paths:
        normalized, error = _normalize_repo_relative_path(raw_path)
        if error is not None:
            return error
        normalized_paths.append(normalized)
    return tuple(normalized_paths)


def _read_markdown_pages(repo_root: Path) -> dict[str, str]:
    wiki_root = repo_root / 'wiki'
    if not wiki_root.exists():
        return {}
    return {
        path.relative_to(repo_root).as_posix(): path.read_text(encoding='utf-8')
        for path in sorted(wiki_root.rglob('*.md'))
        if path.is_file()
    }


def _has_h1_heading(text: str) -> bool:
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('```'):
            in_fence = not in_fence
            continue
        if not in_fence and stripped.startswith('# '):
            return True
    return False


def _iter_internal_targets(source_path: str, text: str) -> tuple[str, ...]:
    source_parent = PurePosixPath(source_path).parent
    targets: list[str] = []
    for raw_target in MARKDOWN_LINK_RE.findall(text):
        target = raw_target.split('#', 1)[0].split('?', 1)[0].strip()
        if not target or '://' in target or target.startswith('mailto:') or target.startswith('tel:'):
            continue
        candidate = PurePosixPath(target)
        if not candidate.is_absolute():
            candidate = source_parent / candidate
        normalized = candidate.as_posix().lstrip('/')
        if normalized.startswith('wiki/') and Path(normalized).suffix == '.md':
            targets.append(normalized)
    return tuple(targets)


def validate_wiki_topology(
    scoped_paths: Sequence[str] = (),
    *,
    repo_root: str | Path = REPO_ROOT,
) -> TopologyValidationResult:
    repo_root_path = Path(repo_root)
    discovered_scope = _discover_scope(repo_root_path, tuple(scoped_paths))
    if isinstance(discovered_scope, str):
        return TopologyValidationResult(valid=False, reason_code=discovered_scope)

    page_text = _read_markdown_pages(repo_root_path)
    violations: list[TopologyViolation] = []
    for control_artifact in REQUIRED_CONTROL_ARTIFACTS:
        if control_artifact not in page_text:
            violations.append(
                TopologyViolation(
                    page=control_artifact,
                    code='missing-control-artifact',
                    message='required control artifact is missing',
                )
            )

    inbound_links: dict[str, set[str]] = {path: set() for path in page_text}
    for source_path, text in page_text.items():
        for target in _iter_internal_targets(source_path, text):
            inbound_links.setdefault(target, set()).add(source_path)
        if source_path in discovered_scope and not _has_h1_heading(text):
            violations.append(
                TopologyViolation(
                    page=source_path,
                    code='missing-heading',
                    message='page must contain a real H1 heading outside fenced code blocks',
                )
            )

    for scoped_path in discovered_scope:
        if scoped_path in EXEMPT_ORPHAN_PATHS:
            continue
        if not inbound_links.get(scoped_path):
            violations.append(
                TopologyViolation(
                    page=scoped_path,
                    code='orphan-page',
                    message='page is not linked from wiki/index.md or any other wiki page',
                )
            )

    return TopologyValidationResult(
        valid=not violations,
        reason_code='ok' if not violations else 'topology_invalid',
        violations=tuple(violations),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Validate bounded wiki topology signals.')
    parser.add_argument('--page', action='append', default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_wiki_topology(tuple(args.page))
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0 if result.valid else 1


if __name__ == '__main__':
    raise SystemExit(main())
