"""Deterministic wiki index updater."""

from __future__ import annotations

import argparse
import contextlib
import concurrent.futures
from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
import itertools

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.kb.write_utils import LockUnavailableError, exclusive_write_lock

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

SECTION_LAYOUT: tuple[tuple[str, str], ...] = (
    ("Sources", "sources"),
    ("Entities", "entities"),
    ("Concepts", "concepts"),
    ("Analyses", "analyses"),
)
_TOPICAL_NAMESPACES = {section_directory for _, section_directory in SECTION_LAYOUT}

_FRONTMATTER_BLOCK_RE = re.compile(r"^\s*---\s*\n(.*?)(?:\n)?\s*---\s*(?:\n|$)", re.DOTALL)

INDEX_FRONTMATTER = """---
type: process
title: Knowledgebase Index
status: active
sources: []
open_questions: []
confidence: 1
sensitivity: internal
updated_at: "1970-01-01T00:00:00Z"
tags:
  - index
  - catalog
---"""


class IndexGenerationError(Exception):
    """Raised when index generation contracts are not satisfied."""


@dataclass(frozen=True, slots=True)
class PageSummary:
    """Metadata needed for deterministic index rendering."""

    relative_path: str
    title: str
    status: str
    confidence: str
    updated_at: str


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _extract_frontmatter(markdown_text: str, page_path: Path) -> str:
    # ⚡ Bolt Optimization: regex prevents an O(N) memory allocation and splitlines computation
    # on large file bodies, reading only up to the second delimiter instead.
    match = _FRONTMATTER_BLOCK_RE.match(markdown_text)
    if not match:
        # Check if the start delimiter is missing for a more specific error message
        lines = markdown_text.splitlines()
        if not lines or lines[0].strip() != "---":
            raise IndexGenerationError(
                f"{page_path}: missing YAML frontmatter start delimiter"
            )
        raise IndexGenerationError(f"{page_path}: missing YAML frontmatter end delimiter")

    return match.group(1)


def _require_frontmatter_key(frontmatter: str, key: str, page_path: Path) -> str:
    key_match = re.search(rf"(?m)^{re.escape(key)}:\s*(.*)$", frontmatter)
    if key_match is None:
        raise IndexGenerationError(
            f"{page_path}: missing required frontmatter key '{key}'"
        )
    return key_match.group(1).strip()


def _parse_page_summary(page_path: Path, wiki_root: Path) -> PageSummary:
    try:
        markdown_text = page_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise IndexGenerationError(f"{page_path}: unable to read file ({exc})") from exc

    frontmatter = _extract_frontmatter(markdown_text, page_path)
    values: dict[str, str] = {}
    for key in REQUIRED_FRONTMATTER_KEYS:
        values[key] = _require_frontmatter_key(frontmatter, key, page_path)

    for key in ("title", "status", "confidence", "updated_at"):
        if not values[key]:
            raise IndexGenerationError(
                f"{page_path}: frontmatter key '{key}' must be a scalar value"
            )

    return PageSummary(
        relative_path=page_path.relative_to(wiki_root).as_posix(),
        title=_strip_quotes(values["title"]),
        status=_strip_quotes(values["status"]),
        confidence=_strip_quotes(values["confidence"]),
        updated_at=_strip_quotes(values["updated_at"]),
    )


def _collect_section_entries(
    wiki_root: Path,
    section_directory: str,
    executor: concurrent.futures.Executor | None = None,
) -> list[PageSummary]:
    section_root = wiki_root / section_directory
    if not section_root.exists():
        return []

    page_paths = [
        _validate_section_page_path(page_path, wiki_root)
        for page_path in section_root.rglob("*.md")
        if page_path.is_file()
    ]

    if executor:
        # We process files efficiently by passing chunksize
        entries = list(
            executor.map(
                _parse_page_summary,
                page_paths,
                itertools.repeat(wiki_root),
                chunksize=100,
            )
        )
    else:
        entries = [
            _parse_page_summary(page_path, wiki_root) for page_path in page_paths
        ]

    entries.sort(key=lambda entry: (entry.title.casefold(), entry.relative_path))
    return entries


def _validate_section_page_path(page_path: Path, wiki_root: Path) -> Path:
    relative_parts = page_path.relative_to(wiki_root).parts
    if len(relative_parts) > 2 and relative_parts[0] in _TOPICAL_NAMESPACES:
        raise IndexGenerationError(
            f"{page_path.relative_to(wiki_root).as_posix()}: "
            "nested topical markdown pages are not allowed in MVP flat namespaces"
        )
    if page_path.is_symlink():
        raise IndexGenerationError(
            f"{page_path.relative_to(wiki_root).as_posix()}: symlinked markdown pages are not allowed"
        )
    resolved_path = page_path.resolve()
    if not resolved_path.is_relative_to(wiki_root):
        raise IndexGenerationError(
            f"{page_path.relative_to(wiki_root).as_posix()}: page escapes wiki root"
        )
    return page_path


def generate_index_content(wiki_root: Path) -> str:
    """Build deterministic index markdown content from wiki pages."""
    if not wiki_root.is_dir():
        raise IndexGenerationError(
            f"{wiki_root}: wiki root does not exist or is not a directory"
        )

    lines: list[str] = [
        INDEX_FRONTMATTER,
        "",
        "# Knowledgebase Index",
        "",
        "Catalog generated deterministically from wiki content.",
        "",
    ]

    with concurrent.futures.ProcessPoolExecutor() as executor:
        for section_title, section_directory in SECTION_LAYOUT:
            entries = _collect_section_entries(wiki_root, section_directory, executor)
            lines.append(f"## {section_title}")
            if entries:
                for entry in entries:
                    lines.append(
                        f"- [{entry.title}]({entry.relative_path}) "
                        f"_(status: {entry.status}; confidence: {entry.confidence}; "
                        f"updated_at: {entry.updated_at})_"
                    )
            else:
                lines.append("- _None_")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate deterministic wiki/index.md content from wiki pages."
    )
    parser.add_argument(
        "--wiki-root",
        required=True,
        type=Path,
        help="Path to the wiki root directory (for example: wiki).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when wiki/index.md differs from generated content.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write generated content to wiki/index.md only when content differs.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for deterministic index generation."""
    args = _build_parser().parse_args(argv)
    wiki_root = args.wiki_root.resolve()

    try:
        generated_content = generate_index_content(wiki_root)
    except IndexGenerationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not args.write and not args.check:
        print(generated_content, end="")
        return 0

    if args.check:
        return _check_index_drift(wiki_root, generated_content)

    try:
        with exclusive_write_lock(wiki_root.parent):
            return _write_index_if_changed(wiki_root, generated_content)
    except LockUnavailableError as exc:
        print(f"error: {exc.failure_reason}", file=sys.stderr)
        return 1


def _check_index_drift(wiki_root: Path, generated_content: str) -> int:
    index_path = wiki_root / "index.md"
    try:
        existing_content = (
            index_path.read_text(encoding="utf-8") if index_path.exists() else ""
        )
    except OSError as exc:
        print(
            f"error: {index_path}: unable to read existing index ({exc})",
            file=sys.stderr,
        )
        return 1

    if existing_content == generated_content:
        print("unchanged")
        return 0

    print("drifted")
    return 1


def _write_index_if_changed(wiki_root: Path, generated_content: str) -> int:
    index_path = wiki_root / "index.md"
    try:
        existing_content = (
            index_path.read_text(encoding="utf-8") if index_path.exists() else ""
        )
    except OSError as exc:
        print(
            f"error: {index_path}: unable to read existing index ({exc})",
            file=sys.stderr,
        )
        return 1

    if existing_content == generated_content:
        print("unchanged")
        return 0

    temp_index_path = index_path.with_name(f"{index_path.name}.tmp")
    temp_created = False
    try:
        with _open_temp_index_path(temp_index_path) as handle:
            temp_created = True
            handle.write(generated_content)
        os.replace(temp_index_path, index_path)
    except OSError as exc:
        if temp_created:
            with contextlib.suppress(OSError):
                temp_index_path.unlink()
        print(f"error: {index_path}: unable to write index ({exc})", file=sys.stderr)
        return 1

    print("written")
    return 0


def _open_temp_index_path(temp_index_path: Path):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temp_index_path, flags, 0o600)
    return os.fdopen(fd, "w", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    raise SystemExit(main())
