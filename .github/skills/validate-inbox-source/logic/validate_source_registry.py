"""Validate declarative source registries for intake-safe workflows."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import StrEnum
import json
from pathlib import Path
import sys
from typing import Any, Sequence
from urllib.parse import urlparse

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.kb import path_utils

REPO_ROOT = Path(__file__).resolve().parents[4]
ALLOWED_REGISTRY_PREFIXES: tuple[str, ...] = ('raw/processed/', 'schema/')
ALLOWED_LOCAL_SOURCE_PREFIXES: tuple[str, ...] = ('raw/inbox/', 'raw/processed/', 'raw/assets/')


class SourceRegistryReasonCode(StrEnum):
    OK = 'ok'
    INVALID_PATH = 'invalid_path'
    PATH_TRAVERSAL = 'path_traversal'
    PATH_NOT_ALLOWLISTED = 'path_not_allowlisted'
    INVALID_REGISTRY = 'invalid_registry'
    INVALID_SOURCE_ID = 'invalid_source_id'
    LOCAL_PATH_NOT_ALLOWLISTED = 'local_path_not_allowlisted'
    INVALID_EXTERNAL_URL = 'invalid_external_url'
    DUPLICATE_SOURCE_ID = 'duplicate_source_id'


@dataclass(frozen=True, slots=True)
class SourceRegistryIssue:
    source_id: str | None
    reason_code: str
    message: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            'source_id': self.source_id,
            'reason_code': self.reason_code,
            'message': self.message,
        }


@dataclass(frozen=True, slots=True)
class SourceRegistryResult:
    valid: bool
    reason_code: str
    registry_path: str
    entry_count: int = 0
    issues: tuple[SourceRegistryIssue, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            'valid': self.valid,
            'reason_code': self.reason_code,
            'registry_path': self.registry_path,
            'entry_count': self.entry_count,
            'issues': [issue.to_dict() for issue in self.issues],
        }


def _normalize_repo_relative_path(value: str | Path) -> tuple[str, str]:
    normalized, error_kind = path_utils.try_normalize_repo_relative_path(value)
    if error_kind == path_utils.ERROR_KIND_PATH_TRAVERSAL:
        return normalized, SourceRegistryReasonCode.PATH_TRAVERSAL.value
    if error_kind == path_utils.ERROR_KIND_INVALID_PATH:
        return normalized, SourceRegistryReasonCode.INVALID_PATH.value
    return normalized, SourceRegistryReasonCode.OK.value


def _validate_registry_path(path: str | Path) -> tuple[str, str | None]:
    normalized, reason_code = _normalize_repo_relative_path(path)
    if reason_code != SourceRegistryReasonCode.OK.value:
        return normalized, reason_code
    if not normalized.endswith('.source-registry.json') or not any(
        normalized.startswith(prefix) for prefix in ALLOWED_REGISTRY_PREFIXES
    ):
        return normalized, SourceRegistryReasonCode.PATH_NOT_ALLOWLISTED.value
    return normalized, None


def _validate_source_entry(raw_entry: Any, seen_ids: set[str]) -> SourceRegistryIssue | None:
    if not isinstance(raw_entry, dict):
        return SourceRegistryIssue(None, SourceRegistryReasonCode.INVALID_REGISTRY.value, 'registry entries must be objects')
    source_id = raw_entry.get('id')
    kind = raw_entry.get('kind')
    location = raw_entry.get('location')
    if not isinstance(source_id, str) or not source_id or not source_id.replace('-', '').replace('_', '').isalnum():
        return SourceRegistryIssue(None, SourceRegistryReasonCode.INVALID_SOURCE_ID.value, 'source id must be a stable slug')
    if source_id in seen_ids:
        return SourceRegistryIssue(source_id, SourceRegistryReasonCode.DUPLICATE_SOURCE_ID.value, 'source ids must be unique')
    seen_ids.add(source_id)
    if kind == 'local':
        if not isinstance(location, str):
            return SourceRegistryIssue(source_id, SourceRegistryReasonCode.LOCAL_PATH_NOT_ALLOWLISTED.value, 'local source entries require a repo-relative path')
        normalized_location, location_reason = _normalize_repo_relative_path(location)
        if location_reason != SourceRegistryReasonCode.OK.value or not any(
            normalized_location.startswith(prefix) for prefix in ALLOWED_LOCAL_SOURCE_PREFIXES
        ):
            return SourceRegistryIssue(source_id, SourceRegistryReasonCode.LOCAL_PATH_NOT_ALLOWLISTED.value, 'local source path is outside the raw source surfaces')
        return None
    if kind == 'external':
        parsed = urlparse(location if isinstance(location, str) else '')
        if parsed.scheme != 'https' or not parsed.netloc:
            return SourceRegistryIssue(source_id, SourceRegistryReasonCode.INVALID_EXTERNAL_URL.value, 'external source URLs must be absolute https URLs')
        return None
    return SourceRegistryIssue(source_id, SourceRegistryReasonCode.INVALID_REGISTRY.value, 'source kind must be local or external')


def validate_source_registry(
    path: str | Path,
    *,
    repo_root: str | Path = REPO_ROOT,
) -> SourceRegistryResult:
    normalized_path, path_error = _validate_registry_path(path)
    if path_error is not None:
        return SourceRegistryResult(False, path_error, str(path))

    registry_path = Path(repo_root) / normalized_path
    try:
        raw_registry = json.loads(registry_path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return SourceRegistryResult(False, SourceRegistryReasonCode.INVALID_REGISTRY.value, normalized_path)

    if not isinstance(raw_registry, dict) or raw_registry.get('version') != 1:
        return SourceRegistryResult(False, SourceRegistryReasonCode.INVALID_REGISTRY.value, normalized_path)
    raw_sources = raw_registry.get('sources')
    if not isinstance(raw_sources, list):
        return SourceRegistryResult(False, SourceRegistryReasonCode.INVALID_REGISTRY.value, normalized_path)

    seen_ids: set[str] = set()
    issues = tuple(
        issue
        for issue in (_validate_source_entry(raw_entry, seen_ids) for raw_entry in raw_sources)
        if issue is not None
    )
    return SourceRegistryResult(
        valid=not issues,
        reason_code=SourceRegistryReasonCode.OK.value if not issues else SourceRegistryReasonCode.INVALID_REGISTRY.value,
        registry_path=normalized_path,
        entry_count=len(raw_sources),
        issues=issues,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Validate a deterministic source registry file.')
    parser.add_argument('--path', required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_source_registry(args.path)
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0 if result.valid else 1


if __name__ == '__main__':
    raise SystemExit(main())
