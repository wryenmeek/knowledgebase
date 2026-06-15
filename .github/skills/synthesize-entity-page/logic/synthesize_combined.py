"""
Combined entity+concept page synthesis under a single wiki write lock.

Acquires the write lock once, synthesizes entity pages, then concept pages
in a single critical section. This eliminates the lock window that exists when
entity and concept synthesis scripts run as independent processes (#115).

CLI usage:
    python3 synthesize_combined.py \\
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
    is_write_lock_held,
)

# Import inner write functions from their respective skill logic modules.
# Both modules guard execution with `if __name__ == "__main__":`, so importing
# them here does not trigger their CLI main() functions.
_HERE = Path(__file__).resolve().parent
_CONCEPT_LOGIC = (
    _HERE.parents[1] / "synthesize-concept-page" / "logic"
)
# Both paths must be explicit so the imports resolve outside of CI-3 / test harness contexts.
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_CONCEPT_LOGIC))

from synthesize_concept_page import _write_concept_drafts  # type: ignore[import]
from synthesize_entity_page import _write_entity_drafts  # type: ignore[import]


class LockContractViolationError(RuntimeError):
    """Raised when lock_already_held kwarg is used without holding the lock."""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Synthesize entity and concept pages in a single lock acquisition."
    )
    parser.add_argument(
        "--extraction-bundle",
        required=True,
        help="Path to extraction bundle JSON from extract_entities.py",
    )
    parser.add_argument(
        "--wiki-root",
        default="wiki",
        help="Wiki root directory relative to repo root (default: wiki)",
    )
    return parser.parse_args()


def run(
    extraction_bundle_path: str,
    wiki_root: str,
    *,
    repo_root: Path | None = None,
    lock_already_held: bool = False,
) -> int:
    """Synthesize entity and concept pages under a single lock.

    ``lock_already_held`` is for callers that already acquired
    ``wiki/.kb_write.lock`` before invoking this combined writer (for example,
    a future checkpoint-registry orchestration path). The guard verifies this
    process holds the lock before skipping the nested acquisition.
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[4]

    bundle_path = Path(extraction_bundle_path)
    if not bundle_path.exists():
        print(f"error: extraction bundle not found: {extraction_bundle_path}", file=sys.stderr)
        return 1

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    if bundle.get("soft_skipped"):
        print("info: extraction was soft-skipped — nothing to synthesize.")
        return 0

    source_ref: str = bundle.get("source_ref") or ""
    wiki_root_path = repo_root / wiki_root
    entities = bundle.get("entities") or []
    concepts = bundle.get("concepts") or []

    if not entities and not concepts:
        print("info: no entities or concepts in bundle — nothing to synthesize.")
        return 0

    try:
        if lock_already_held:
            if not is_write_lock_held(repo_root):
                raise LockContractViolationError("lock_already_held=True requires this process to hold wiki/.kb_write.lock")
            entity_results = _write_entity_drafts(entities, wiki_root_path, source_ref)
            concept_results = _write_concept_drafts(concepts, wiki_root_path, source_ref)
        else:
            with exclusive_write_lock(repo_root):
                entity_results = _write_entity_drafts(entities, wiki_root_path, source_ref)
                concept_results = _write_concept_drafts(concepts, wiki_root_path, source_ref)
    except LockUnavailableError as exc:
        print(f"error: lock unavailable: {exc}", file=sys.stderr)
        return 1
    except LockContractViolationError as exc:
        print(f"error: synthesis structural violation: {exc}", file=sys.stderr)
        return 1

    rc = 0
    for label, results in (("entity", entity_results), ("concept", concept_results)):
        if results["created"]:
            print(f"{label} pages created: {len(results['created'])}")
            for entry in results["created"]:
                print(f"  + {entry}")
        if results.get("updated"):
            print(f"{label} pages updated (append-only): {len(results['updated'])}")
            for entry in results["updated"]:
                print(f"  ~ {entry}")
        if results.get("skipped"):
            print(f"{label} pages skipped: {len(results['skipped'])}")
            for entry in results["skipped"]:
                print(f"  - {entry}", file=sys.stderr)
        if results["errors"]:
            print(f"{label} page errors: {len(results['errors'])}", file=sys.stderr)
            for entry in results["errors"]:
                print(f"  ! {entry}", file=sys.stderr)
            rc = 1

    return rc


def main() -> int:
    args = _parse_args()
    return run(args.extraction_bundle, args.wiki_root)


if __name__ == "__main__":
    raise SystemExit(main())
