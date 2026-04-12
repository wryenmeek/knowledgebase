"""Read-only semantic and structural linting for wiki markdown content."""

from __future__ import annotations

import argparse
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

_FRONTMATTER_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:")
_MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
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


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _normalize_link_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if not target:
        return None

    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()

    if " " in target:
        target = target.split(" ", 1)[0]

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

    if target.startswith("wiki/"):
        candidate = (wiki_root.parent / target).resolve()
    elif target.startswith("/"):
        candidate = (wiki_root / target.lstrip("/")).resolve()
    else:
        candidate = (source_page.parent / target).resolve()

    if candidate.suffix:
        return candidate

    if candidate.is_file():
        return candidate

    return candidate.with_suffix(".md")


def _display_path(path: Path, wiki_root: Path) -> str:
    try:
        return str(path.relative_to(wiki_root))
    except ValueError:
        return str(path)


def lint_wiki(wiki_root: Path) -> list[Violation]:
    """Run lint checks over markdown pages under wiki_root."""
    wiki_root = wiki_root.resolve()
    pages = sorted(path.resolve() for path in wiki_root.rglob("*.md") if path.is_file())

    violations: list[Violation] = []
    referenced_by: dict[Path, set[Path]] = {page: set() for page in pages}

    for page in pages:
        text = page.read_text(encoding="utf-8")
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

            if not _is_within(target_path, wiki_root):
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
                            f"{_display_path(target_path, wiki_root)}"
                        ),
                    )
                )
                continue

            resolved_target = target_path.resolve()
            if resolved_target in referenced_by and resolved_target != page:
                referenced_by[resolved_target].add(page)

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
