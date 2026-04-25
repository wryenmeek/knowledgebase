"""Tests for log-intake-rejection logic (log_rejection.py)."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

# The module lives under .github/skills/log-intake-rejection/logic/
# which is importable via the sys.path manipulation in the module itself.
# For tests we import it via scripts.kb since we test the validators that way.
# But log_rejection uses the optional_surface_common pattern so we import
# it at the repo-root level.
import importlib
import sys

# Add the logic dir to the path so we can import log_rejection
_LOGIC_DIR = str(
    Path(__file__).resolve().parents[2]
    / ".github"
    / "skills"
    / "log-intake-rejection"
    / "logic"
)
if _LOGIC_DIR not in sys.path:
    sys.path.insert(0, _LOGIC_DIR)

from log_rejection import (
    SURFACE,
    _scan_existing_sha256,
    log_rejection,
)


def _valid_kwargs(tmp_path: Path) -> dict:
    return {
        "repo_root": tmp_path,
        "slug": "test-source",
        "sha256": "a" * 64,
        "rejected_date": "2025-01-01T00:00:00Z",
        "source_path": "raw/inbox/test.pdf",
        "rejection_reason": "Missing provenance",
        "rejection_category": "provenance_missing",
        "reviewed_by": "operator",
    }


class TestLogRejection:
    def test_successful_write(self, tmp_path: Path) -> None:
        result = log_rejection(**_valid_kwargs(tmp_path))
        assert result.status == "pass"
        target = tmp_path / "raw" / "rejected" / f"test-source--{'a' * 8}.rejection.md"
        assert target.exists()
        content = target.read_text()
        assert "slug: test-source" in content
        assert f"sha256: {'a' * 64}" in content

    def test_invalid_slug_fails(self, tmp_path: Path) -> None:
        kwargs = _valid_kwargs(tmp_path)
        kwargs["slug"] = "BAD SLUG"
        result = log_rejection(**kwargs)
        assert result.status == "fail"
        assert result.reason_code == "invalid_input"

    def test_invalid_sha256_fails(self, tmp_path: Path) -> None:
        kwargs = _valid_kwargs(tmp_path)
        kwargs["sha256"] = "tooshort"
        result = log_rejection(**kwargs)
        assert result.status == "fail"
        assert result.reason_code == "invalid_input"

    def test_invalid_category_fails(self, tmp_path: Path) -> None:
        kwargs = _valid_kwargs(tmp_path)
        kwargs["rejection_category"] = "not_real"
        result = log_rejection(**kwargs)
        assert result.status == "fail"
        assert result.reason_code == "invalid_input"

    def test_duplicate_sha256_fails(self, tmp_path: Path) -> None:
        # First write succeeds
        result1 = log_rejection(**_valid_kwargs(tmp_path))
        assert result1.status == "pass"
        # Second write with same sha256 but different slug
        kwargs = _valid_kwargs(tmp_path)
        kwargs["slug"] = "different-source"
        result2 = log_rejection(**kwargs)
        assert result2.status == "fail"
        assert result2.reason_code == "duplicate_sha256"

    def test_write_once_same_file_fails(self, tmp_path: Path) -> None:
        result1 = log_rejection(**_valid_kwargs(tmp_path))
        assert result1.status == "pass"
        # Same slug+sha256 → file already exists and sha256 matches
        result2 = log_rejection(**_valid_kwargs(tmp_path))
        assert result2.status == "fail"
        assert result2.reason_code in ("duplicate_sha256", "record_exists")


class TestScanExistingSha256:
    def test_empty_dir(self, tmp_path: Path) -> None:
        assert _scan_existing_sha256(tmp_path) == set()

    def test_finds_sha256(self, tmp_path: Path) -> None:
        record = "---\nsha256: abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234\n---\n"
        (tmp_path / "test--abcd1234.rejection.md").write_text(record)
        result = _scan_existing_sha256(tmp_path)
        assert "abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234" in result

    def test_nonexistent_dir(self) -> None:
        assert _scan_existing_sha256(Path("/nonexistent")) == set()
