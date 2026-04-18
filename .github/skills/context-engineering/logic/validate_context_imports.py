"""Validate skill-local context import manifests."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Sequence

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from context_import_contract import (
    REPO_ROOT,
    ContextImportContractError,
    ContextImportDocument,
    load_context_import_document,
)


@dataclass(frozen=True, slots=True)
class ContextImportValidationResult:
    valid: bool
    reason_code: str
    document_path: str
    import_count: int = 0
    normalized_document: dict[str, object] | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            'valid': self.valid,
            'reason_code': self.reason_code,
            'document_path': self.document_path,
            'import_count': self.import_count,
            'normalized_document': self.normalized_document,
            'message': self.message,
        }


def validate_context_imports(
    path: str | Path,
    *,
    repo_root: str | Path = REPO_ROOT,
) -> ContextImportValidationResult:
    try:
        normalized_path, document = load_context_import_document(path, repo_root=repo_root)
    except ContextImportContractError as exc:
        return ContextImportValidationResult(
            valid=False,
            reason_code=exc.reason_code,
            document_path=str(path),
            message=str(exc),
        )
    return ContextImportValidationResult(
        valid=True,
        reason_code='ok',
        document_path=normalized_path,
        import_count=len(document.imports),
        normalized_document=document.to_dict(),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Validate a skill-local context import manifest.')
    parser.add_argument('--path', required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_context_imports(args.path)
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0 if result.valid else 1


if __name__ == '__main__':
    raise SystemExit(main())
