"""Read-only semantic and structural linting for wiki markdown content."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import re
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.kb import sourceref

REQUIRED_FRONTMATTER_KEYS: tuple[str, ...] = (
    "type",
    "title",
    "status",
    "sources",
    "open_questions",
    "confidence",
    "sensitivity",
    "updated_at",
    "tags",
)

_FRONTMATTER_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:")
_MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
_MARKDOWN_LINK_TITLE_RE = re.compile(r"^(?P<url>\S+)\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\))$")
_CONTRADICTION_MARKER_RE = re.compile(
    r"(\[\s*CONTRADICTION\s*]|\{\{\s*contradiction\s*}}|UNRESOLVED_CONTRADICTION|<!--\s*CONTRADICTION\b[^>]*-->)",
    re.IGNORECASE,
)
_EXTERNAL_LINK_PREFIXES = ("http://", "https://", "mailto:", "tel:", "ftp://")
_TOPICAL_NAMESPACES: tuple[str, ...] = ("sources", "entities", "concepts", "analyses")


@dataclass(frozen=True, slots=True)
class Violation:
    """Lint violation emitted for strict wiki checks."""

    page: Path
    code: str
    message: str


def _extract_frontmatter(text: str) -> tuple[str | None, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text

    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            frontmatter = "\n".join(lines[1:index])
            body = "\n".join(lines[index + 1 :])
            return frontmatter, body

    return None, text


def _extract_frontmatter_keys(frontmatter: str) -> set[str]:
    keys: set[str] = set()
    for line in frontmatter.splitlines():
        match = _FRONTMATTER_KEY_RE.match(line)
        if match:
            keys.add(match.group(1))
    return keys


def _extract_frontmatter_source_refs(frontmatter: str) -> list[str]:
    lines = frontmatter.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("sources:"):
            continue
        inline_value = stripped[len("sources:") :].strip()
        if inline_value == "[]":
            return []
        if inline_value:
            return [_normalize_frontmatter_scalar(inline_value)]
        sources: list[str] = []
        for candidate in lines[index + 1 :]:
            if not candidate.startswith("  "):
                break
            candidate = candidate.strip()
            if not candidate.startswith("- "):
                continue
            sources.append(_normalize_frontmatter_scalar(candidate[2:].strip()))
        return sources
    return []


def _normalize_frontmatter_scalar(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _is_within(path: Path, root: Path) -> bool:
    # ⚡ Bolt: `is_relative_to` is a natively implemented method string comparison under the hood.
    # It avoids expensive `try/except` block and `relative_to` value error exceptions which is slower.
    return path.is_relative_to(root)


def _normalize_link_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if not target:
        return None

    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()

    title_match = _MARKDOWN_LINK_TITLE_RE.match(target)
    if title_match:
        target = title_match.group("url")

    lower_target = target.lower()
    if lower_target.startswith(_EXTERNAL_LINK_PREFIXES) or "://" in target:
        return None

    if lower_target.startswith("javascript:"):
        return None

    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target:
        return None

    suffix = Path(target).suffix.lower()
    if suffix and suffix != ".md":
        return None

    return target


def _resolve_internal_markdown_target(
    source_page: Path,
    raw_target: str,
    wiki_root: Path,
) -> Path | None:
    target = _normalize_link_target(raw_target)
    if target is None:
        return None

    # ⚡ Bolt: Defer calling `.resolve()` on the candidate path here.
    # Eager `.resolve()` inside a hotloop forces frequent expensive OS stat calls.
    # Instead, we just build the raw path and let the caller `lint_wiki` resolve it exactly once.
    # This reduces execution time significantly when linting thousands of links.
    if target.startswith("wiki/"):
        candidate = (wiki_root.parent / target)
    elif target.startswith("/"):
        candidate = (wiki_root / target.lstrip("/"))
    else:
        candidate = (source_page.parent / target)

    if candidate.suffix:
        return candidate

    if candidate.is_file():
        return candidate

    return candidate.with_suffix(".md")


def _display_path(path: Path, wiki_root: Path) -> str:
    # ⚡ Bolt Optimization: Use is_relative_to instead of try/except for bounds checking
    if path.is_relative_to(wiki_root):
        return str(path.relative_to(wiki_root))
    return str(path)


def _is_nested_topical_page(page: Path, wiki_root: Path) -> bool:
    relative_parts = page.relative_to(wiki_root).parts
    return (
        len(relative_parts) > 2
        and relative_parts[0] in _TOPICAL_NAMESPACES
    )


def lint_wiki(
    wiki_root: Path,
    *,
    skip_orphan_check: bool = False,
    authoritative_sourcerefs: bool = False,
    repo_owner: str | None = None,
    repo_name: str | None = None,
) -> list[Violation]:
    """Run lint checks over markdown pages under wiki_root."""
    wiki_root = wiki_root.resolve()
    violations: list[Violation] = []
    pages: list[Path] = []
    for path in sorted(wiki_root.rglob("*.md")):
        if not path.is_file():
            continue
        if path.is_symlink():
            violations.append(
                Violation(
                    page=path,
                    code="symlinked-page",
                    message="symlinked markdown pages are not allowed",
                )
            )
            continue
        resolved_path = path.resolve()
        if not _is_within(resolved_path, wiki_root):
            violations.append(
                Violation(
                    page=path,
                    code="out-of-bounds-page",
                    message="markdown page escapes wiki root",
                )
            )
            continue
        pages.append(path)
    referenced_by: dict[Path, set[Path]] = {page: set() for page in pages}

    def _read_page(p: Path) -> str:
        return p.read_text(encoding="utf-8")

    with ThreadPoolExecutor() as executor:
        # Avoid buffering all contents into a list; map returns an iterator.
        # This keeps peak memory low by only having one file's text loaded at a time per thread,
        # plus the small number of results held in memory waiting to be yielded.
        pages_content_iterator = executor.map(_read_page, pages)

        for page, text in zip(pages, pages_content_iterator):
            if _is_nested_topical_page(page, wiki_root):
                violations.append(
                    Violation(
                        page=page,
                        code="nested-topical-page",
                        message=(
                            "nested topical markdown pages are not allowed in MVP flat namespaces"
                        ),
                    )
                )

            frontmatter, _body = _extract_frontmatter(text)

            if frontmatter is None:
                violations.append(
                    Violation(
                        page=page,
                        code="missing-frontmatter",
                        message="missing YAML frontmatter block",
                    )
                )
            else:
                present_keys = _extract_frontmatter_keys(frontmatter)
                missing_keys = sorted(
                    key for key in REQUIRED_FRONTMATTER_KEYS if key not in present_keys
                )
                for key in missing_keys:
                    violations.append(
                        Violation(
                            page=page,
                            code="missing-frontmatter-key",
                            message=f"required key '{key}' is missing",
                            )
                        )
                if authoritative_sourcerefs and "sources" in present_keys:
                    for source_value in _extract_frontmatter_source_refs(frontmatter):
                        try:
                            sourceref.validate_sourceref(
                                source_value,
                                authoritative=True,
                                repo_root=wiki_root.parent,
                                expected_owner=repo_owner,
                                expected_repo=repo_name,
                            )
                        except sourceref.SourceRefValidationError as exc:
                            violations.append(
                                Violation(
                                    page=page,
                                    code="invalid-sourceref",
                                    message=f"invalid SourceRef '{source_value}': {exc}",
                                )
                            )

            for match in _MARKDOWN_LINK_RE.finditer(text):
                target_path = _resolve_internal_markdown_target(page, match.group(1), wiki_root)
                if target_path is None:
                    continue

                resolved_target_path = target_path.resolve()
                if not _is_within(resolved_target_path, wiki_root):
                    violations.append(
                        Violation(
                            page=page,
                            code="out-of-bounds-link",
                            message=f"internal link leaves wiki root: {match.group(1)}",
                        )
                    )
                    continue

                if not target_path.exists() or not target_path.is_file():
                    violations.append(
                        Violation(
                            page=page,
                            code="missing-link-target",
                            message=(
                                "internal markdown link target does not exist: "
                                f"{_display_path(resolved_target_path, wiki_root)}"
                            ),
                        )
                    )
                    continue

                if resolved_target_path in referenced_by and resolved_target_path != page:
                    referenced_by[resolved_target_path].add(page)

            if _CONTRADICTION_MARKER_RE.search(text):
                violations.append(
                    Violation(
                        page=page,
                        code="unresolved-contradiction-marker",
                        message="unresolved contradiction marker requires escalation",
                    )
                )

    if not skip_orphan_check:
        exempt_from_orphan_check = {
            (wiki_root / "index.md").resolve(),
            (wiki_root / "log.md").resolve(),
        }

        for page in pages:
            if page in exempt_from_orphan_check:
                continue

            if not referenced_by.get(page):
                violations.append(
                    Violation(
                        page=page,
                        code="orphan-page",
                        message="page is not referenced from index or any other page",
                    )
                )

    return sorted(
        violations,
        key=lambda item: (_display_path(item.page, wiki_root), item.code, item.message),
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint wiki frontmatter and cross-links")
    parser.add_argument(
        "--wiki-root",
        default="wiki",
        help="Wiki root directory to lint (default: wiki)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when lint violations are found",
    )
    parser.add_argument(
        "--skip-orphan-check",
        action="store_true",
        help="Skip orphan-page detection for staged index-refresh validation.",
    )
    parser.add_argument(
        "--authoritative-sourcerefs",
        action="store_true",
        help="Require commit-bound authoritative SourceRef validation for frontmatter sources.",
    )
    parser.add_argument(
        "--repo-owner",
        help="Expected repository owner for authoritative SourceRef validation.",
    )
    parser.add_argument(
        "--repo-name",
        help="Expected repository name for authoritative SourceRef validation.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    wiki_root = Path(args.wiki_root)

    if not wiki_root.exists() or not wiki_root.is_dir():
        print(f"ERROR: wiki root does not exist or is not a directory: {wiki_root}", file=sys.stderr)
        return 2
    if args.authoritative_sourcerefs and (not args.repo_owner or not args.repo_name):
        print(
            "ERROR: --authoritative-sourcerefs requires --repo-owner and --repo-name",
            file=sys.stderr,
        )
        return 2

    violations = lint_wiki(
        wiki_root,
        skip_orphan_check=bool(args.skip_orphan_check),
        authoritative_sourcerefs=bool(args.authoritative_sourcerefs),
        repo_owner=args.repo_owner,
        repo_name=args.repo_name,
    )
    for violation in violations:
        print(
            f"{_display_path(violation.page, wiki_root.resolve())}: "
            f"{violation.code}: {violation.message}"
        )

    print(f"Found {len(violations)} violation(s).")

    if args.strict and violations:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
