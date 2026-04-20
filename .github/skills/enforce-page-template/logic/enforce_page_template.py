"""Deterministic wiki page-template validation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Sequence

if __package__ in (None, ""):  # supports both 'python -m' and direct invocation without package install
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.kb import lint_wiki, page_template_utils

REPO_ROOT = Path(__file__).resolve().parents[4]
REQUIRED_FRONTMATTER_KEYS: tuple[str, ...] = lint_wiki.REQUIRED_FRONTMATTER_KEYS
TEMPLATE_SECTION_REQUIREMENTS = page_template_utils.TEMPLATE_SECTION_REQUIREMENTS


@dataclass(frozen=True, slots=True)
class TemplateViolation:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class TemplateReport:
    page: str
    is_valid: bool
    violations: tuple[TemplateViolation, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "page": self.page,
            "is_valid": self.is_valid,
            "violations": [
                {"code": violation.code, "message": violation.message}
                for violation in self.violations
            ],
        }


def validate_page_template(page: str | Path, *, repo_root: str | Path = REPO_ROOT) -> TemplateReport:
    normalized_page, raw_violations = page_template_utils.validate_page_template_path(
        page,
        repo_root=repo_root,
        required_frontmatter_keys=REQUIRED_FRONTMATTER_KEYS,
        template_section_requirements=TEMPLATE_SECTION_REQUIREMENTS,
    )
    violations = tuple(
        TemplateViolation(code=code, message=message) for code, message in raw_violations
    )
    return TemplateReport(
        page=normalized_page,
        is_valid=not violations,
        violations=violations,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a wiki page against the blocking template.")
    parser.add_argument("--page", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    report = validate_page_template(args.page)
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
