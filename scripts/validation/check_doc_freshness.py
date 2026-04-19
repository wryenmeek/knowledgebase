"""Deterministic freshness analysis for repo-local markdown content."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
import sys
from typing import Sequence, TextIO

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.kb import page_template_utils
from scripts._optional_surface_common import (
    JsonArgumentParser,
    STATUS_PASS,
    STATUS_FAIL,
    REASON_CODE_OK,
    REASON_CODE_INVALID_INPUT,
    looks_like_repo_root,
)
REASON_CODE_MISSING_UPDATED_AT = "missing_updated_at"
REASON_CODE_INVALID_UPDATED_AT = "invalid_updated_at"
REASON_CODE_STALE_DOCUMENT = "stale_document"
REASON_CODE_PREREQ_MISSING_REPO_ROOT = "prereq_missing:repo_root"

SCOPE_ROOTS: dict[str, tuple[str, ...]] = {
    "wiki": ("wiki",),
    "docs": ("docs",),
    "all": ("docs", "wiki"),
}


@dataclass(frozen=True, slots=True)
class FreshnessFileResult:
    path: str
    status: str
    reason_code: str
    message: str
    updated_at: str | None = None
    age_days: int | None = None

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "path": self.path,
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "updated_at": self.updated_at,
            "age_days": self.age_days,
        }


@dataclass(frozen=True, slots=True)
class FreshnessReport:
    status: str
    reason_code: str
    message: str
    scope: str
    as_of: str
    max_age_days: int
    files: tuple[FreshnessFileResult, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "scope": self.scope,
            "as_of": self.as_of,
            "max_age_days": self.max_age_days,
            "files": [item.to_dict() for item in self.files],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


def run_freshness(
    *,
    repo_root: str | Path = ".",
    scope: str,
    as_of: str,
    max_age_days: int,
    paths: Sequence[str] | None = None,
) -> FreshnessReport:
    normalized_repo_root = Path(repo_root).resolve()
    if not looks_like_repo_root(normalized_repo_root):
        return FreshnessReport(
            status=STATUS_FAIL,
            reason_code=REASON_CODE_PREREQ_MISSING_REPO_ROOT,
            message="repository root must exist and contain AGENTS.md",
            scope=scope,
            as_of=as_of,
            max_age_days=max_age_days,
            files=(),
        )

    try:
        as_of_date = _parse_iso_date(as_of)
        normalized_max_age = _normalize_max_age_days(max_age_days)
        markdown_files = _resolve_markdown_files(
            repo_root=normalized_repo_root,
            scope=scope,
            paths=paths,
        )
    except ValueError as exc:
        return FreshnessReport(
            status=STATUS_FAIL,
            reason_code=REASON_CODE_INVALID_INPUT,
            message=str(exc),
            scope=scope,
            as_of=as_of,
            max_age_days=max_age_days,
            files=(),
        )

    results = tuple(
        _check_file(path, repo_root=normalized_repo_root, as_of_date=as_of_date, max_age_days=normalized_max_age)
        for path in markdown_files
    )
    first_failure = next((result for result in results if result.status == STATUS_FAIL), None)
    if first_failure is None:
        return FreshnessReport(
            status=STATUS_PASS,
            reason_code=REASON_CODE_OK,
            message="all scanned documents satisfy freshness requirements",
            scope=scope,
            as_of=as_of_date.isoformat(),
            max_age_days=normalized_max_age,
            files=results,
        )
    return FreshnessReport(
        status=STATUS_FAIL,
        reason_code=first_failure.reason_code,
        message=first_failure.message,
        scope=scope,
        as_of=as_of_date.isoformat(),
        max_age_days=normalized_max_age,
        files=results,
    )


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    output_stream: TextIO = sys.stdout,
    repo_root: str | Path | None = None,
) -> int:
    try:
        args = _build_parser().parse_args(list(argv) if argv is not None else None)
    except ValueError as exc:
        report = FreshnessReport(
            status=STATUS_FAIL,
            reason_code=REASON_CODE_INVALID_INPUT,
            message=str(exc),
            scope="unknown",
            as_of="unknown",
            max_age_days=-1,
            files=(),
        )
        output_stream.write(report.to_json())
        output_stream.write("\n")
        return 1
    report = run_freshness(
        repo_root=Path(repo_root).resolve() if repo_root is not None else Path.cwd(),
        scope=args.scope,
        as_of=args.as_of,
        max_age_days=args.max_age_days,
        paths=args.path,
    )
    if getattr(args, "failures_only", False):
        report_dict = report.to_dict()
        report_dict["files"] = [f for f in report_dict["files"] if f["status"] == STATUS_FAIL]
        output_stream.write(json.dumps(report_dict, sort_keys=True))
    else:
        output_stream.write(report.to_json())
    output_stream.write("\n")
    return 0 if report.status == STATUS_PASS else 1


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv=argv)


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description="Run deterministic freshness analysis over repo-local markdown.")
    parser.add_argument("--scope", choices=tuple(SCOPE_ROOTS), default="wiki")
    parser.add_argument("--path", action="append", default=[], help="Optional repo-relative markdown file or directory.")
    parser.add_argument("--as-of", required=True, help="Required ISO date used for deterministic age checks.")
    parser.add_argument("--max-age-days", required=True, type=int, help="Maximum allowed age in days.")
    parser.add_argument("--failures-only", action="store_true", default=False, help="Suppress passing files; emit only stale or invalid entries.")
    return parser


def _parse_iso_date(value: str) -> date:
    normalized = value.strip()
    if not normalized:
        raise ValueError("as-of must be a non-empty ISO date")
    try:
        return date.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid as-of date: {value}") from exc


def _normalize_max_age_days(value: int) -> int:
    if value < 0:
        raise ValueError("max-age-days must be zero or greater")
    return value


def _resolve_markdown_files(*, repo_root: Path, scope: str, paths: Sequence[str] | None) -> tuple[Path, ...]:
    scope_roots = SCOPE_ROOTS.get(scope)
    if scope_roots is None:
        raise ValueError(f"unsupported scope: {scope}")

    allowed_roots = tuple((repo_root / root).resolve() for root in scope_roots)
    selected: list[Path] = []
    seen: set[Path] = set()

    if paths:
        for raw_path in paths:
            for candidate in _expand_path_candidate(raw_path, repo_root=repo_root, allowed_roots=allowed_roots):
                if candidate in seen:
                    continue
                seen.add(candidate)
                selected.append(candidate)
    else:
        for allowed_root in allowed_roots:
            if not allowed_root.exists():
                continue
            for candidate in sorted(allowed_root.rglob("*.md")):
                resolved_candidate = candidate.resolve()
                if resolved_candidate in seen:
                    continue
                seen.add(resolved_candidate)
                selected.append(resolved_candidate)

    if not selected:
        raise ValueError(f"no markdown files found for scope: {scope}")
    return tuple(selected)


def _expand_path_candidate(raw_path: str, *, repo_root: Path, allowed_roots: Sequence[Path]) -> tuple[Path, ...]:
    normalized_path = raw_path.strip()
    if not normalized_path:
        raise ValueError("path values must be non-empty repo-relative paths")

    candidate = Path(normalized_path)
    if candidate.is_absolute():
        raise ValueError(f"path must be repo-relative: {normalized_path}")

    resolved_candidate = (repo_root / candidate).resolve()
    if not resolved_candidate.is_relative_to(repo_root):
        raise ValueError(f"path escapes repository root: {normalized_path}")
    if not any(resolved_candidate.is_relative_to(root) for root in allowed_roots):
        raise ValueError(f"path is outside the declared scope '{normalized_path}'")
    if not resolved_candidate.exists():
        raise ValueError(f"path does not exist: {normalized_path}")
    if resolved_candidate.is_dir():
        return tuple(sorted(path.resolve() for path in resolved_candidate.rglob("*.md")))
    if resolved_candidate.suffix.lower() != ".md":
        raise ValueError(f"path must reference markdown content: {normalized_path}")
    return (resolved_candidate,)


def _check_file(path: Path, *, repo_root: Path, as_of_date: date, max_age_days: int) -> FreshnessFileResult:
    relative_path = path.relative_to(repo_root).as_posix()
    updated_at_value = _extract_updated_at(path.read_text(encoding="utf-8"))
    if updated_at_value is None:
        return FreshnessFileResult(
            path=relative_path,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_MISSING_UPDATED_AT,
            message="missing updated_at metadata",
        )
    try:
        updated_at_date = _parse_frontmatter_date(updated_at_value)
    except ValueError:
        return FreshnessFileResult(
            path=relative_path,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_INVALID_UPDATED_AT,
            message=f"invalid updated_at metadata: {updated_at_value}",
        )

    age_days = (as_of_date - updated_at_date).days
    if age_days < 0:
        return FreshnessFileResult(
            path=relative_path,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_INVALID_UPDATED_AT,
            message=f"updated_at is in the future relative to as-of date: {updated_at_value}",
            updated_at=updated_at_date.isoformat(),
            age_days=age_days,
        )
    if age_days > max_age_days:
        return FreshnessFileResult(
            path=relative_path,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_STALE_DOCUMENT,
            message=f"document exceeds freshness threshold ({age_days}d > {max_age_days}d). FIX: update page content and set updated_at: <today's date> in the YAML frontmatter.",
            updated_at=updated_at_date.isoformat(),
            age_days=age_days,
        )
    return FreshnessFileResult(
        path=relative_path,
        status=STATUS_PASS,
        reason_code=REASON_CODE_OK,
        message="document freshness within threshold",
        updated_at=updated_at_date.isoformat(),
        age_days=age_days,
    )


def _extract_updated_at(text: str) -> str | None:
    frontmatter, _body = page_template_utils.extract_frontmatter(text)
    if frontmatter is None:
        return None
    metadata = page_template_utils.parse_frontmatter(frontmatter)
    raw = metadata.get("updated_at")
    if raw is None:
        return None
    value = page_template_utils.strip_quotes(raw)
    return value or None


def _parse_frontmatter_date(value: str) -> date:
    normalized = value.strip()
    if not normalized:
        raise ValueError("updated_at must not be empty")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        if "T" in normalized or "+" in normalized:
            return datetime.fromisoformat(normalized).date()
        return date.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid updated_at value: {value}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
