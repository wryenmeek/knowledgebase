"""
Synthesize concept pages from an extraction bundle.

Reads the JSON bundle produced by extract_entities.py, acquires the wiki write lock,
and either creates new wiki/concepts/<slug>.md pages or appends to existing ones
(append-only: new SourceRef + open_questions; existing prose is never overwritten).

Soft-skipped bundles (soft_skipped: true) are accepted and produce no writes.

CLI usage:
    python3 synthesize_concept_page.py \\
        --extraction-bundle /tmp/extraction-bundle.json \\
        --wiki-root wiki
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # repo root

from scripts.kb.write_utils import (
    LockUnavailableError,
    exclusive_write_lock,
    write_text_capturing_previous_safe,
)

# _synthesis_utils is co-located in the synthesize-entity-page skill logic dir
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1].parent / "synthesize-entity-page" / "logic"),
)
from _synthesis_utils import (
    _sanitize_llm_str,
    append_to_existing_page,
    find_duplicate,
    render_draft_page,
    scan_existing_pages,
    title_to_slug,
    validate_draft_frontmatter,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Synthesize concept pages from an extraction bundle."
    )
    parser.add_argument(
        "--extraction-bundle",
        required=True,
        help="Path to extraction bundle JSON from extract_entities.py",
    )
    parser.add_argument("--wiki-root", default="wiki", help="Wiki root directory")
    return parser.parse_args()


def _write_concept_drafts(
    concepts: list[dict],
    wiki_root: Path,
    source_ref: str,
) -> dict[str, list[str]]:
    """Write concept draft pages under wiki_root/concepts/.

    Returns dict with keys 'created', 'updated', 'skipped', 'errors'.
    Must be called while holding exclusive_write_lock.
    """
    results: dict[str, list[str]] = {
        "created": [],
        "updated": [],
        "skipped": [],
        "errors": [],
    }
    concepts_dir = wiki_root / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)

    existing = scan_existing_pages(wiki_root, "concepts")

    for concept in concepts:
        title: str = (concept.get("title") or "").strip()
        if not title:
            results["skipped"].append("(empty title)")
            continue

        aliases: list[str] = concept.get("aliases") or []
        matches = find_duplicate(existing, title, aliases)

        if len(matches) > 1:
            results["skipped"].append(
                f"{title}: ambiguous — {len(matches)} existing matches (fail-closed)"
            )
            print(
                f"warning: concept '{title}' skipped — {len(matches)} ambiguous matches",
                file=sys.stderr,
            )
            continue

        open_questions: list[str] = concept.get("open_questions") or []

        if len(matches) == 1:
            page_path = Path(matches[0]["path"])
            try:
                modified = append_to_existing_page(page_path, source_ref, open_questions)
                if modified:
                    results["updated"].append(f"{title} ({page_path.name})")
                else:
                    results["skipped"].append(f"{title}: no new data to append")
            except Exception as exc:
                results["errors"].append(f"{title}: update failed: {exc}")
            continue

        slug = title_to_slug(title)
        page_path = concepts_dir / f"{slug}.md"

        if page_path.exists():
            results["skipped"].append(
                f"{title}: slug collision — {slug}.md exists (fail-closed)"
            )
            print(
                f"warning: concept '{title}' skipped — slug collision {slug}.md",
                file=sys.stderr,
            )
            continue

        draft = render_draft_page(
            page_type="concept",
            title=_sanitize_llm_str(title),
            aliases=[_sanitize_llm_str(a) for a in aliases],
            source_ref=source_ref,
            summary=_sanitize_llm_str(concept.get("summary") or "", max_len=1000),
            evidence=_sanitize_llm_str(concept.get("evidence") or "", max_len=1000),
            tags=[_sanitize_llm_str(t) for t in (concept.get("tags") or [])],
            open_questions=[_sanitize_llm_str(q) for q in open_questions],
        )

        missing = validate_draft_frontmatter(draft)
        if missing:
            results["errors"].append(
                f"{title}: draft missing frontmatter keys: {missing}"
            )
            print(
                f"warning: concept '{title}' draft invalid (missing keys: {missing})",
                file=sys.stderr,
            )
            continue

        try:
            write_text_capturing_previous_safe(page_path, draft)
            results["created"].append(f"{title} ({page_path.name})")
            existing.append({"title": title, "aliases": aliases, "path": str(page_path)})
        except OSError as exc:
            results["errors"].append(f"{title}: write failed: {exc}")

    return results


def run(
    extraction_bundle_path: str,
    wiki_root: str,
    *,
    repo_root: Path | None = None,
) -> int:
    """Synthesize concept pages. Returns 0 on success, 1 on hard error."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[4]

    bundle_path = Path(extraction_bundle_path)
    if not bundle_path.exists():
        print(f"error: extraction bundle not found: {extraction_bundle_path}", file=sys.stderr)
        return 1

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    if bundle.get("soft_skipped"):
        print("info: extraction was soft-skipped — no concept pages to synthesize.")
        return 0

    concepts = bundle.get("concepts") or []
    if not concepts:
        print("info: no concepts in bundle — nothing to synthesize.")
        return 0

    source_ref: str = bundle.get("source_ref") or ""
    wiki_root_path = repo_root / wiki_root

    try:
        with exclusive_write_lock(repo_root):
            results = _write_concept_drafts(concepts, wiki_root_path, source_ref)
    except LockUnavailableError as exc:
        print(f"error: lock unavailable: {exc}", file=sys.stderr)
        return 1

    created = results["created"]
    updated = results["updated"]
    skipped = results["skipped"]
    errors = results["errors"]

    if created:
        print(f"concept pages created: {len(created)}")
        for entry in created:
            print(f"  + {entry}")
    if updated:
        print(f"concept pages updated (append-only): {len(updated)}")
        for entry in updated:
            print(f"  ~ {entry}")
    if skipped:
        print(f"concept pages skipped: {len(skipped)}")
        for entry in skipped:
            print(f"  - {entry}", file=sys.stderr)
    if errors:
        print(f"concept page errors: {len(errors)}", file=sys.stderr)
        for entry in errors:
            print(f"  ! {entry}", file=sys.stderr)

    return 1 if errors else 0


def main() -> int:
    args = _parse_args()
    return run(
        extraction_bundle_path=args.extraction_bundle,
        wiki_root=args.wiki_root,
    )


if __name__ == "__main__":
    sys.exit(main())
