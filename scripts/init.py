"""Fresh-instance initializer for the knowledgebase template.

Usage:
    python3 scripts/init.py --fresh [--yes]

--fresh   Required flag. Wipes the content layer and scaffolds a clean
          domain-ready instance. Performs these steps in order:
            1. Wipe all content-layer directories (wiki/analyses/, wiki/concepts/,
               wiki/entities/, wiki/sources/, raw/inbox/, raw/processed/,
               raw/assets/, raw/rejected/, raw/github-sources/, raw/drive-sources/)
            2. Remove stale lock files
            3. Write framework stubs: wiki/log.md, wiki/index.md
            4. Write domain scaffolding: raw/processed/SPEC.md (TODO skeleton),
               raw/inbox/example-policy.md (sample source for first ingest run)
            5. Run pip install -e .[dev] to ensure dependencies are current
            6. Run pytest tests/ to confirm the framework is clean
--yes     Skip the confirmation prompt. Requires the INIT_ALLOW_WIPE=1
          environment variable to prevent accidental CI invocation.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.kb.contracts import (
    CUSTOMIZATIONS_LOCK_PATH,
    DRIVE_SOURCES_LOCK_PATH,
    GOVERNANCE_META_LOCK_PATH,
    GITHUB_SOURCES_LOCK_PATH,
    REJECTION_REGISTRY_LOCK_PATH,
)
from scripts.kb.write_utils import (
    check_no_symlink_path,
    write_text_capturing_previous_safe,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories whose entire contents are wiped (dirs themselves are kept).
CONTENT_DIRS = [
    "wiki/analyses",
    "wiki/concepts",
    "wiki/entities",
    "wiki/sources",
    "raw/inbox",
    "raw/processed",
    "raw/assets",
    "raw/rejected",
    "raw/github-sources",
    "raw/drive-sources",
]

# Stale sibling lock files that are auto-removed on fresh init.
# wiki/.kb_write.lock is intentionally excluded — its presence means another
# process may be actively writing and must be investigated before wiping.
LOCK_FILES = [
    REJECTION_REGISTRY_LOCK_PATH,
    GITHUB_SOURCES_LOCK_PATH,
    DRIVE_SOURCES_LOCK_PATH,
    CUSTOMIZATIONS_LOCK_PATH,
    GOVERNANCE_META_LOCK_PATH,
]

_LOG_STUB = """\
---
type: process
title: Knowledgebase Log
status: active
sources: []
open_questions:
  - "First state-change entry pending initial ingest workflow."
confidence: 1
sensitivity: internal
updated_at: "1970-01-01T00:00:00Z"
tags:
  - audit
  - chronology
---

# Knowledgebase Log

Append-only chronology for knowledgebase state changes.

## Policy notes

- Record changes only when repository state changes.
- No-op runs should not append entries.
"""

_INDEX_STUB = """\
---
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
---

# Knowledgebase Index

Catalog generated deterministically from wiki content.

## Sources
_None_

## Entities
_None_

## Concepts
_None_
"""

_SPEC_STUB = """\
# Domain Specification

<!-- TODO: Replace this file with your domain's assumptions and policy decisions.
     This file governs how ingest.py and synthesis workflows interpret your sources. -->

## Assumptions and Defaults

<!-- TODO: List your domain's core assumptions. Example:
1. This repository implements a persistent wiki pattern (not query-time-only RAG).
2. Raw source truth remains immutable once moved to raw/processed/.
3. Confidence rubric is numeric 1..5 for synthesized wiki content.
-->

## Terminology

<!-- TODO: Define canonical terms for your domain. Example:
- **Policy**: ...
- **Authority source**: ...
-->

## Sensitivity Levels

<!-- TODO: Define sensitivity tiers used in frontmatter. Example:
- internal: organization-internal only
- public: safe for public release
-->

## Authority Sources

<!-- TODO: List the authoritative sources for your domain. -->
"""

_SAMPLE_INBOX = """\
# Example Policy Document

**Source type:** policy-document
**Authority:** Example Authority Organization
**Date:** 2026-01-01
**Sensitivity:** internal

## Overview

This is a sample source document that ships with the knowledgebase template. It
demonstrates the expected format for inbox source files and lets you verify the
ingest pipeline end-to-end before replacing it with your domain's real sources.

Replace this file (`raw/inbox/example-policy.md`) with your own source material
and update `raw/processed/SPEC.md` with your domain assumptions before running
your first real ingest.

## Section 1 — Purpose

This policy establishes example procedures for managing example resources within
the example organization.

## Section 2 — Scope

These procedures apply to all example stakeholders operating within the example
jurisdiction.

## Section 3 — Procedures

1. Stakeholders submit requests using the standard request form.
2. Reviewers evaluate requests against the criteria in Section 4.
3. Approved requests are logged and actioned within 5 business days.

## Section 4 — Criteria

A request is approved when all of the following conditions are met:

- The request is complete and correctly formatted.
- The requested resource is within scope.
- No conflicting prior decision exists.

## References

- Example Standard v1.0 (2025)
- Example Authority Guidelines (2024)
"""

# Sentinels that must exist at REPO_ROOT to confirm correct location.
_REPO_SENTINELS = ["pyproject.toml", ".git", "AGENTS.md", "schema"]


def _assert_repo_root(root: Path) -> None:
    """Exit with an error if *root* does not look like the repo root."""
    missing = [s for s in _REPO_SENTINELS if not (root / s).exists()]
    if missing:
        sys.exit(
            f"ERROR: {root} does not look like the repo root "
            f"(missing: {', '.join(missing)}). "
            "Do not run this script from an installed or copied location."
        )





def _confirm(prompt: str) -> bool:
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("y", "yes")


def _wipe_dir(path: Path) -> None:
    """Remove all contents of *path* without removing the directory itself.

    Raises OSError if any component of *path* is a symlink (via
    check_no_symlink_path from write_utils) to prevent traversal-to-delete
    outside the repository.
    """
    check_no_symlink_path(path)
    if not path.exists():
        path.mkdir(parents=True)
        return
    for child in path.iterdir():
        if child.is_symlink():
            # Remove the symlink itself — never follow it into an external dir.
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _write(path: Path, content: str) -> None:
    """Write *content* to *path* using an atomic, symlink-safe write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_capturing_previous_safe(path, content)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialize a fresh knowledgebase instance from the template.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "See TEMPLATE.md for the full setup guide.\n"
            "After running this script, edit raw/processed/SPEC.md, AGENTS.md,\n"
            "CONTEXT.md, wiki/CONTEXT.md, and README.md with your domain."
        ),
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        required=True,
        help="Wipe the content layer and scaffold a clean instance.",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip the confirmation prompt. Requires INIT_ALLOW_WIPE=1 env var.",
    )
    args = parser.parse_args(argv)

    # Guard: --yes in CI requires explicit opt-in env var to prevent accidental wipe.
    if args.yes and not os.environ.get("INIT_ALLOW_WIPE"):
        print(
            "ERROR: --yes requires INIT_ALLOW_WIPE=1 to be set in the environment.\n"
            "This prevents accidental content-layer wipes in CI pipelines.\n"
            "For interactive use, omit --yes and answer the prompt instead.",
            file=sys.stderr,
        )
        return 1

    # Guard: verify REPO_ROOT is actually the repo root before touching anything.
    _assert_repo_root(REPO_ROOT)

    print("=" * 60)
    print("  Knowledgebase template initializer")
    print("=" * 60)
    print()
    print("This will PERMANENTLY DELETE all content-layer files:")
    for d in CONTENT_DIRS:
        print(f"  {d}/")
    print()
    print("Framework-layer files (scripts/, tests/, .github/, schema/,")
    print("docs/decisions/, pyproject.toml, etc.) will NOT be touched.")
    print()

    if not args.yes and not _confirm("Proceed?"):
        print("Aborted.")
        return 1

    # Guard: check no concurrent process holds the wiki write lock.
    wiki_lock = REPO_ROOT / "wiki" / ".kb_write.lock"
    if wiki_lock.exists():
        print(
            f"  ✗  {wiki_lock.relative_to(REPO_ROOT)} exists — another process may be "
            "writing to the wiki. Remove the lock file and retry.",
            file=sys.stderr,
        )
        return 1

    # 1. Wipe content directories
    print("\n[1/5] Wiping content directories...")
    for rel in CONTENT_DIRS:
        p = REPO_ROOT / rel
        _wipe_dir(p)
        print(f"  ✓  {rel}/")

    # 2. Remove stale lock files
    for rel in LOCK_FILES:
        p = REPO_ROOT / rel
        # Validate the lock file's parent (not the lock file itself) so that
        # a stale symlink at the lock path can still be unlinked rather than
        # crashing the symlink guard.
        check_no_symlink_path(p.parent)
        # `p.exists()` is False for broken symlinks; OR with `is_symlink()`
        # so cleanup also removes broken symlinks left over from prior runs.
        if p.exists() or p.is_symlink():
            p.unlink()
            print(f"  ✓  removed lock file {rel}")

    # 3. Write framework stubs
    print("\n[2/5] Writing framework stubs...")
    # Intentional full-overwrite exception to the append-only guardrail
    # (AGENTS.md §Guardrails #3): fresh-init is the sole operation permitted
    # to overwrite wiki/log.md with a clean stub.
    _write(REPO_ROOT / "wiki" / "log.md", _LOG_STUB)
    print("  ✓  wiki/log.md")
    _write(REPO_ROOT / "wiki" / "index.md", _INDEX_STUB)
    print("  ✓  wiki/index.md")

    # 4. Write domain scaffolding
    print("\n[3/5] Writing domain scaffolding...")
    _write(REPO_ROOT / "raw" / "processed" / "SPEC.md", _SPEC_STUB)
    print("  ✓  raw/processed/SPEC.md  (TODO: fill in your domain assumptions)")
    _write(REPO_ROOT / "raw" / "inbox" / "example-policy.md", _SAMPLE_INBOX)
    print("  ✓  raw/inbox/example-policy.md  (sample source to test the pipeline)")

    # 5. Install pip dependencies
    print("\n[4/5] Installing pip dependencies...")
    pip_result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", ".[dev]", "-q"],
        cwd=REPO_ROOT,
        timeout=300,
    )
    if pip_result.returncode != 0:
        print("  ✗  pip install failed — check output above", file=sys.stderr)
        return pip_result.returncode
    print("  ✓  pip install -e .[dev]")

    # 6. Run test suite
    print("\n[5/5] Running test suite...")
    pytest_result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=short"],
        cwd=REPO_ROOT,
        timeout=600,
    )
    if pytest_result.returncode != 0:
        print(
            "\n  ✗  Tests failed — your framework may have environment issues.",
            file=sys.stderr,
        )
        print(
            "     Fix the failures before starting your domain configuration.",
            file=sys.stderr,
        )
        return pytest_result.returncode

    print()
    print("=" * 60)
    print("  ✓  Fresh instance ready.")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Edit raw/processed/SPEC.md   — domain assumptions")
    print("  2. Edit AGENTS.md               — agent guardrails")
    print("  3. Edit CONTEXT.md              — repo-level context")
    print("  4. Edit wiki/CONTEXT.md         — wiki taxonomy")
    print("  5. Edit README.md               — project overview")
    print()
    print("Then run your first ingest:")
    print(
        "  python3 scripts/kb/ingest.py "
        "--source raw/inbox/example-policy.md "
        "--wiki-root wiki --schema AGENTS.md"
    )
    print()
    print("See TEMPLATE.md for the full setup guide.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
