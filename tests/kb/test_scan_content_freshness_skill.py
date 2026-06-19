"""Contract checks for the scan-content-freshness skill."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPO_ROOT / ".github" / "skills" / "scan-content-freshness"
SKILL_PATH = SKILL_ROOT / "SKILL.md"


def test_skill_is_thin_and_routes_to_repo_script_with_typed_args() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "## Overview" in text
    assert "## When to Use" in text
    assert "## Contract" in text
    assert "## Assertions" in text
    assert "## Commands" in text
    assert "scripts/validation/check_doc_freshness.py" in text
    assert "--scope" in text
    assert "--as-of" in text
    assert "--max-age-days" in text
    assert "typed" in text.lower()
    assert not (SKILL_ROOT / "logic").exists()
