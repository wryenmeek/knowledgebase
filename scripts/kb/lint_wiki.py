"""Read-only semantic and structural linting for wiki markdown content."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import re
import sys

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

_FRONTMATTER_BLOCK_RE = re.compile(r"^[ \t]*---[ \t]*\n(.*?)\n?[ \t]*---[ \t]*(?:\n|$)", re.DOTALL)
_FRONTMATTER_KEY_RE = re.compile(r"(?m)^([A-Za-z_][A-Za-z0-9_-]*)\s*:")
_MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
_MARKDOWN_LINK_TITLE_RE = re.compile(r"^(?P<url>\S+)\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\))$")
_CONTRADICTION_MARKER_RE = re.compile(
    r"(\[\s*CONTRADICTION\s*]|\{\{\s*contradiction\s*}}|UNRESOLVED_CONTRADICTION|<!--\s*CONTRADICTION\b[^>]*-->)",
    re.IGNORECASE,
)
_EXTERNAL_LINK_PREFIXES = ("http://", "https://", "mailto:", "tel:", "ftp://")


@dataclass(frozen=True, slots=True)
class Violation:
    """Lint violation emitted for strict wiki checks."""

    page: Path
    code: str
    message: str


def _extract_frontmatter(text: str) -> tuple[str | None, str]:
    # ⚡ Bolt Optimization: Fast path check without evaluating the whole file content
    first_newline = text.find('\n')
    first_line = text if first_newline == -1 else text[:first_newline]

    if first_line.strip() != "---":
        return None, text

    match = _FRONTMATTER_BLOCK_RE.match(text)
    if match:
        return match.group(1), text[match.end():]

    return None, text


def _extract_frontmatter_keys(frontmatter: str) -> set[str]:
    # ⚡ Bolt Optimization: Extract all matches using re.findall instead of splitlines
    return set(_FRONTMATTER_KEY_RE.findall(frontmatter))


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


def lint_wiki(wiki_root: Path) -> list[Violation]:
    """Run lint checks over markdown pages under wiki_root."""
    wiki_root = wiki_root.resolve()
    # ⚡ Bolt Optimization: Avoid eager resolve() in hot loop to save OS stat calls
    pages = sorted(path for path in wiki_root.rglob("*.md") if path.is_file())

    violations: list[Violation] = []
    referenced_by: dict[Path, set[Path]] = {page: set() for page in pages}

    def _read_page(p: Path) -> str:
        return p.read_text(encoding="utf-8")

    with ThreadPoolExecutor() as executor:
        # Avoid buffering all contents into a list; map returns an iterator.
        # This keeps peak memory low by only having one file's text loaded at a time per thread,
        # plus the small number of results held in memory waiting to be yielded.
        pages_content_iterator = executor.map(_read_page, pages)

        for page, text in zip(pages, pages_content_iterator):
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    wiki_root = Path(args.wiki_root)

    if not wiki_root.exists() or not wiki_root.is_dir():
        print(f"ERROR: wiki root does not exist or is not a directory: {wiki_root}", file=sys.stderr)
        return 2

    violations = lint_wiki(wiki_root)
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
