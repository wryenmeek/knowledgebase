"""Typed contract helpers for skill-local context import manifests."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in (None, ""):  # supports both 'python -m' and direct invocation without package install
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.kb import path_utils

REPO_ROOT = Path(__file__).resolve().parents[4]
ALLOWED_CONTEXT_FILE_PREFIXES: tuple[str, ...] = (
    '.github/skills/',
    '.github/agents/',
)
ALLOWED_IMPORT_PREFIXES: tuple[str, ...] = (
    '.github/agents/',
    '.github/skills/',
    'docs/',
    'raw/processed/',
    'schema/',
    'scripts/kb/',
    'tests/kb/',
    'wiki/',
)
ALLOWED_IMPORT_FILES: tuple[str, ...] = ('AGENTS.md', 'README.md')
MAX_CONTEXT_IMPORTS = 12


class ContextImportReasonCode(StrEnum):
    OK = 'ok'
    INVALID_PATH = 'invalid_path'
    PATH_TRAVERSAL = 'path_traversal'
    PATH_NOT_ALLOWLISTED = 'path_not_allowlisted'
    INVALID_DOCUMENT = 'invalid_document'
    TOO_MANY_IMPORTS = 'too_many_imports'
    DUPLICATE_IMPORT = 'duplicate_import'
    UNSUPPORTED_VERSION = 'unsupported_version'


class ContextImportContractError(ValueError):
    def __init__(self, reason_code: ContextImportReasonCode | str, message: str) -> None:
        self.reason_code = str(reason_code)
        super().__init__(f'{self.reason_code}: {message}')


@dataclass(frozen=True, slots=True)
class ContextImportEntry:
    path: str

    def to_dict(self) -> dict[str, str]:
        return {'path': self.path}


@dataclass(frozen=True, slots=True)
class ContextImportDocument:
    version: int
    imports: tuple[ContextImportEntry, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            'version': self.version,
            'imports': [entry.to_dict() for entry in self.imports],
        }


@dataclass(frozen=True, slots=True)
class ContextImportIssue:
    reason_code: str
    message: str
    value: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            'reason_code': self.reason_code,
            'message': self.message,
            'value': self.value,
        }


def normalize_repo_relative_path(value: str | Path) -> tuple[str, str]:
    normalized, error_kind = path_utils.try_normalize_repo_relative_path(value)
    if error_kind == path_utils.ERROR_KIND_PATH_TRAVERSAL:
        return normalized, ContextImportReasonCode.PATH_TRAVERSAL.value
    if error_kind == path_utils.ERROR_KIND_INVALID_PATH:
        return normalized, ContextImportReasonCode.INVALID_PATH.value
    return normalized, ContextImportReasonCode.OK.value


def validate_context_file_path(path: str | Path) -> str:
    normalized, reason_code = normalize_repo_relative_path(path)
    if reason_code != ContextImportReasonCode.OK.value:
        raise ContextImportContractError(reason_code, 'context import file path is invalid')
    if not normalized.endswith('context-imports.json'):
        raise ContextImportContractError(
            ContextImportReasonCode.PATH_NOT_ALLOWLISTED,
            'context import manifests must end with context-imports.json',
        )
    if not any(normalized.startswith(prefix) for prefix in ALLOWED_CONTEXT_FILE_PREFIXES):
        raise ContextImportContractError(
            ContextImportReasonCode.PATH_NOT_ALLOWLISTED,
            'context import manifest is outside the declared skill/agent surface',
        )
    return normalized


def _normalize_import_path(value: Any) -> str:
    if not isinstance(value, str):
        raise ContextImportContractError(
            ContextImportReasonCode.INVALID_DOCUMENT,
            'context imports must use string repo-relative paths',
        )
    normalized, reason_code = normalize_repo_relative_path(value)
    if reason_code != ContextImportReasonCode.OK.value:
        raise ContextImportContractError(reason_code, 'context import path is invalid')
    if normalized not in ALLOWED_IMPORT_FILES and not any(
        normalized.startswith(prefix) for prefix in ALLOWED_IMPORT_PREFIXES
    ):
        raise ContextImportContractError(
            ContextImportReasonCode.PATH_NOT_ALLOWLISTED,
            f'context import path is outside the declared read surface: {normalized}',
        )
    return normalized


def normalize_context_import_document(raw_document: Any) -> ContextImportDocument:
    if isinstance(raw_document, list):
        version = 1
        raw_imports = raw_document
    elif isinstance(raw_document, dict):
        version = raw_document.get('version', 1)
        raw_imports = raw_document.get('imports')
    else:
        raise ContextImportContractError(
            ContextImportReasonCode.INVALID_DOCUMENT,
            'context import document must be a list or object',
        )

    if version != 1:
        raise ContextImportContractError(
            ContextImportReasonCode.UNSUPPORTED_VERSION,
            f'unsupported context import manifest version: {version}',
        )
    if not isinstance(raw_imports, list):
        raise ContextImportContractError(
            ContextImportReasonCode.INVALID_DOCUMENT,
            'context import document must contain an imports list',
        )
    if len(raw_imports) > MAX_CONTEXT_IMPORTS:
        raise ContextImportContractError(
            ContextImportReasonCode.TOO_MANY_IMPORTS,
            f'context import document exceeds the {MAX_CONTEXT_IMPORTS} import cap',
        )

    normalized_entries: list[ContextImportEntry] = []
    seen_paths: set[str] = set()
    for raw_entry in raw_imports:
        if isinstance(raw_entry, str):
            normalized_path = _normalize_import_path(raw_entry)
        elif isinstance(raw_entry, dict) and set(raw_entry).issubset({'path'}) and 'path' in raw_entry:
            normalized_path = _normalize_import_path(raw_entry['path'])
        else:
            raise ContextImportContractError(
                ContextImportReasonCode.INVALID_DOCUMENT,
                'each context import entry must be a string path or {"path": ...}',
            )
        if normalized_path in seen_paths:
            raise ContextImportContractError(
                ContextImportReasonCode.DUPLICATE_IMPORT,
                f'duplicate context import path: {normalized_path}',
            )
        seen_paths.add(normalized_path)
        normalized_entries.append(ContextImportEntry(path=normalized_path))

    return ContextImportDocument(version=1, imports=tuple(normalized_entries))


def load_context_import_document(
    path: str | Path,
    *,
    repo_root: str | Path = REPO_ROOT,
) -> tuple[str, ContextImportDocument]:
    normalized_path = validate_context_file_path(path)
    document_path = Path(repo_root) / normalized_path
    try:
        raw_document = json.loads(document_path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise ContextImportContractError(
            ContextImportReasonCode.INVALID_DOCUMENT,
            f'context import manifest does not exist: {normalized_path}',
        ) from exc
    except json.JSONDecodeError as exc:
        raise ContextImportContractError(
            ContextImportReasonCode.INVALID_DOCUMENT,
            f'context import manifest is not valid JSON: {normalized_path}',
        ) from exc
    return normalized_path, normalize_context_import_document(raw_document)
