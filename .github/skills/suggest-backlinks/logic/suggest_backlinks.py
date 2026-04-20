"""Taxonomy-scoped backlink suggestion scanner for the suggest-backlinks skill.

Read-only only. Scans a candidate page's neighborhood (same namespace + pages
the candidate already links to) for unlinked mentions of the candidate's title.
Emits structured BacklinkProposal objects. Never writes to wiki.

Neighborhood definition (per SKILL.md contract):
  - Same namespace: all .md pages under wiki/<same-namespace-dir>/
  - Linked neighbors: pages the candidate already wikilinks or md-links to

Scope constraint: no repo-wide crawl. Proposals are narrow and human-reviewable.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Add repo root to sys.path for canonical module imports (ADR-011)
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.kb.page_template_utils import parse_page_frontmatter  # noqa: E402

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
MDLINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")  # group 1 = display, group 2 = URL


@dataclass(frozen=True)
class BacklinkProposal:
    source_file: str    # page that should add the link (relative to wiki_root)
    source_line: int    # 1-indexed line number of the unlinked mention
    surface_text: str   # the text that appears unlinked
    suggested_link: str # relative path to the candidate page (from wiki_root)
    rationale: str      # e.g. "namespace:entities" or "linked-neighbor"

    def to_dict(self) -> dict[str, object]:
        return {
            "source_file": self.source_file,
            "source_line": self.source_line,
            "surface_text": self.surface_text,
            "suggested_link": self.suggested_link,
            "rationale": self.rationale,
        }


def _get_candidate_title(page_path: Path) -> str:
    """Extract title from frontmatter via canonical parser, or derive from filename."""
    try:
        fm = parse_page_frontmatter(page_path.read_text(encoding="utf-8"))
        if fm.get("title"):
            return fm["title"]
    except OSError:
        pass
    return page_path.stem.replace("-", " ").replace("_", " ").title()


def _get_namespace(page_path: Path, wiki_root: Path) -> str | None:
    """Return the first path segment under wiki_root (e.g. 'entities')."""
    try:
        parts = page_path.relative_to(wiki_root).parts
        return parts[0] if len(parts) >= 2 else None
    except ValueError:
        return None


def _get_existing_link_targets(page_path: Path) -> set[str]:
    """Return raw link targets found in a page (wikilinks and md link URLs)."""
    targets: set[str] = set()
    try:
        text = page_path.read_text(encoding="utf-8")
        for m in WIKILINK_RE.finditer(text):
            targets.add(m.group(1).strip())
        for m in MDLINK_RE.finditer(text):
            # Use URL path (group 2) for file resolution, not display text (group 1)
            url = m.group(2).strip().split("#")[0].split("?")[0]
            if url:
                targets.add(url)
    except OSError:
        pass
    return targets


def _resolve_link_target(raw: str, wiki_root: Path) -> Path | None:
    """Resolve a raw link target to an absolute wiki file path, or None.

    Handles md link URL paths (e.g. 'entities/part-b.md') and wikilink
    titles (e.g. 'Part B') via kebab-case normalization across namespaces.
    """
    if not raw or raw.startswith(("http://", "https://", "mailto:")):
        return None
    # Try as a relative path to wiki_root (works for explicit md link URLs)
    for candidate in (wiki_root / raw, wiki_root / (raw + ".md")):
        if candidate.resolve().is_file():
            return candidate.resolve()
    # Wikilink title-to-filename: kebab normalization across all namespaces
    kebab = raw.lower().replace(" ", "-")
    for ns_dir in sorted(wiki_root.iterdir()):
        if not ns_dir.is_dir():
            continue
        for name in (kebab, raw.lower()):
            p = (ns_dir / name).with_suffix(".md")
            if p.is_file():
                return p.resolve()
    return None


def _line_already_links_title(line: str, title: str) -> bool:
    """Return True if title already appears inside a link syntax on this line."""
    title_lower = title.lower()
    for m in WIKILINK_RE.finditer(line):
        if title_lower in m.group(1).lower():
            return True
    for m in MDLINK_RE.finditer(line):
        if title_lower in m.group(1).lower():
            return True
    return False


def _scan_neighbor(
    neighbor: Path,
    candidate_path: Path,
    title: str,
    wiki_root: Path,
    rationale: str,
) -> list[BacklinkProposal]:
    """Scan one neighbor page for unlinked whole-word mentions of title."""
    if neighbor.resolve() == candidate_path.resolve():
        return []
    try:
        lines = neighbor.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    pattern = re.compile(r"\b" + re.escape(title) + r"\b", re.IGNORECASE)
    proposals: list[BacklinkProposal] = []
    in_code_block = False

    for lineno, line in enumerate(lines, start=1):
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
        if in_code_block:
            continue
        if pattern.search(line) and not _line_already_links_title(line, title):
            try:
                source_rel = str(neighbor.relative_to(wiki_root))
            except ValueError:
                source_rel = str(neighbor)
            try:
                suggested = str(candidate_path.relative_to(wiki_root))
            except ValueError:
                suggested = str(candidate_path)
            proposals.append(BacklinkProposal(
                source_file=source_rel,
                source_line=lineno,
                surface_text=title,
                suggested_link=suggested,
                rationale=rationale,
            ))

    return proposals


def scan(candidate: str | Path, wiki_root: str | Path = "wiki") -> list[BacklinkProposal]:
    """Scan the candidate page's neighborhood for unlinked mentions.

    Neighborhood:
      1. Same-namespace pages (wiki/<namespace>/*.md siblings)
      2. Pages the candidate already explicitly links to

    Returns a list of BacklinkProposal objects. Empty list on missing candidate,
    empty corpus, or no findings. Never writes to wiki.
    """
    candidate_path = Path(candidate).resolve()
    wiki_root_path = Path(wiki_root).resolve()

    if not candidate_path.is_file():
        return []

    title = _get_candidate_title(candidate_path)
    if not title:
        return []

    proposals: list[BacklinkProposal] = []
    seen: set[Path] = {candidate_path}

    # Neighborhood 1: same namespace
    namespace = _get_namespace(candidate_path, wiki_root_path)
    if namespace:
        ns_dir = wiki_root_path / namespace
        if ns_dir.is_dir():
            for neighbor in sorted(ns_dir.rglob("*.md")):
                neighbor_r = neighbor.resolve()
                if neighbor_r not in seen:
                    seen.add(neighbor_r)
                    proposals.extend(
                        _scan_neighbor(
                            neighbor, candidate_path, title, wiki_root_path,
                            f"namespace:{namespace}",
                        )
                    )

    # Neighborhood 2: pages the candidate already links to
    for link_target in _get_existing_link_targets(candidate_path):
        resolved = _resolve_link_target(link_target, wiki_root_path)
        if resolved is not None and resolved not in seen:
            seen.add(resolved)
            proposals.extend(
                _scan_neighbor(
                    resolved, candidate_path, title, wiki_root_path,
                    "linked-neighbor",
                )
            )

    return proposals


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: suggest-backlinks <candidate-page> [--wiki-root <path>]"""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Suggest backlink opportunities for a wiki page (read-only)."
    )
    parser.add_argument("candidate", help="Path to the candidate wiki page")
    parser.add_argument(
        "--wiki-root", default="wiki", help="Path to the wiki root directory (default: wiki)"
    )
    args = parser.parse_args(argv)

    proposals = scan(args.candidate, args.wiki_root)
    print(json.dumps([p.to_dict() for p in proposals], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
