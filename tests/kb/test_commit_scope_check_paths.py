"""Drift contract test: SENSITIVE_PATHS in contracts.py must match CONTEXT.md.

The ``sensitive paths`` term in ``CONTEXT.md`` ## Terms table is the canonical
human-readable definition; ``scripts/kb/contracts.py::SENSITIVE_PATHS`` is the
machine-readable source of truth used by ``check_commit_scope.py``.  This test
enforces set equality so neither side can silently drift from the other.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTEXT_MD = REPO_ROOT / "CONTEXT.md"


def _parse_sensitive_paths_from_context() -> frozenset[str]:
    """Parse the ``sensitive paths`` row from the CONTEXT.md ## Terms table.

    The row looks like::

        | sensitive paths | The explicit allowlist of paths...: `wiki/`, ...,
        `.github/workflows/`. Referenced by ... |

    We extract only the backtick-quoted items between the
    ``"allowlist of paths...:"`` clause and the ``"Referenced by"`` sentinel,
    to avoid picking up unrelated code references later in the same cell.
    """
    text = CONTEXT_MD.read_text(encoding="utf-8")

    # Find the full row content for "sensitive paths" in the ## Terms table.
    row_match = re.search(
        r"\|\s*sensitive paths\s*\|(.+?)(?=\n\||$)",
        text,
        re.DOTALL,
    )
    if not row_match:
        raise ValueError(
            "Could not find 'sensitive paths' row in CONTEXT.md ## Terms table. "
            "Update the row or fix the parser."
        )
    row_content = row_match.group(1)

    # Narrow to the allowlist clause: everything between the colon after
    # "allowlist of paths..." and the "Referenced by" sentinel.
    allowlist_match = re.search(
        r"allowlist of paths[^:]*:\s+(.+?)\.\s+Referenced by",
        row_content,
        re.DOTALL,
    )
    if not allowlist_match:
        raise ValueError(
            "Could not locate allowlist clause in 'sensitive paths' row. "
            "Expected pattern: 'allowlist of paths...:<paths>. Referenced by'."
        )

    allowlist_text = allowlist_match.group(1)

    # Extract all backtick-quoted tokens from the allowlist clause.
    paths = frozenset(re.findall(r"`([^`]+)`", allowlist_text))
    if not paths:
        raise ValueError(
            "No backtick-quoted paths found in the allowlist clause of "
            "'sensitive paths' row in CONTEXT.md."
        )
    return paths


def test_sensitive_paths_match_context_md() -> None:
    """SENSITIVE_PATHS in contracts.py must exactly equal the CONTEXT.md glossary set."""
    if not CONTEXT_MD.exists():
        pytest.skip("CONTEXT.md not found")

    from scripts.kb.contracts import SENSITIVE_PATHS  # noqa: PLC0415 – local import

    context_paths = _parse_sensitive_paths_from_context()
    contracts_paths = frozenset(SENSITIVE_PATHS)

    missing_from_contracts = context_paths - contracts_paths
    extra_in_contracts = contracts_paths - context_paths

    assert not missing_from_contracts, (
        "Paths present in CONTEXT.md 'sensitive paths' but MISSING from "
        f"contracts.SENSITIVE_PATHS: {sorted(missing_from_contracts)}. "
        "Add them to SENSITIVE_PATHS in scripts/kb/contracts.py."
    )
    assert not extra_in_contracts, (
        "Paths present in contracts.SENSITIVE_PATHS but MISSING from "
        f"CONTEXT.md 'sensitive paths': {sorted(extra_in_contracts)}. "
        "Add them to the 'sensitive paths' row in CONTEXT.md ## Terms table."
    )
