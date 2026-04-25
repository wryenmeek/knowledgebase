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

import yaml

from log_rejection import (
    SURFACE,
    _sanitize_markdown,
    _scan_existing_sha256,
    _yaml_quote,
    log_rejection,
)
from scripts.kb.contracts import REJECTION_REGISTRY_LOCK_PATH
from scripts.kb.write_utils import LockUnavailableError


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

    def test_lock_contention_raises_lock_unavailable(self, tmp_path: Path) -> None:
        """ADR-005: lock contention must produce lock_unavailable, not a partial write."""
        import fcntl

        # Pre-acquire the rejection registry lock to simulate a concurrent writer.
        lock_file_path = tmp_path / REJECTION_REGISTRY_LOCK_PATH
        lock_file_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = lock_file_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Lock is held — log_rejection should fail closed.
            result = log_rejection(**_valid_kwargs(tmp_path))
            assert result.status == "fail"
            assert result.reason_code == "lock_unavailable"
            # No partial write should have occurred.
            rejected_dir = tmp_path / "raw" / "rejected"
            assert not any(rejected_dir.glob("*.rejection.md")) if rejected_dir.exists() else True
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()


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


class TestYamlQuote:
    """Security: _yaml_quote must handle all YAML-significant characters."""

    def test_plain_value_unquoted(self) -> None:
        assert _yaml_quote("simple") == "simple"

    def test_colon_triggers_quoting(self) -> None:
        result = _yaml_quote("key: value")
        parsed = yaml.safe_load(f"field: {result}")
        assert parsed["field"] == "key: value"

    def test_hash_triggers_quoting(self) -> None:
        result = _yaml_quote("value # comment injection")
        parsed = yaml.safe_load(f"field: {result}")
        assert parsed["field"] == "value # comment injection"

    def test_newline_escaped_not_literal(self) -> None:
        result = _yaml_quote("line1\nline2")
        # Result must be a quoted scalar, not a multi-line block.
        assert "\n" not in result
        parsed = yaml.safe_load(f"field: {result}")
        assert parsed["field"] == "line1\nline2"

    def test_carriage_return_escaped(self) -> None:
        result = _yaml_quote("value\rmore")
        assert "\r" not in result
        parsed = yaml.safe_load(f"field: {result}")
        assert parsed["field"] == "value\rmore"

    def test_yaml_anchor_character_quoted(self) -> None:
        result = _yaml_quote("&anchor")
        parsed = yaml.safe_load(f"field: {result}")
        assert parsed["field"] == "&anchor"

    def test_yaml_alias_character_quoted(self) -> None:
        result = _yaml_quote("*alias")
        parsed = yaml.safe_load(f"field: {result}")
        assert parsed["field"] == "*alias"

    def test_yaml_tag_character_quoted(self) -> None:
        result = _yaml_quote("!tag value")
        parsed = yaml.safe_load(f"field: {result}")
        assert parsed["field"] == "!tag value"

    def test_frontmatter_boundary_injection(self, tmp_path: Path) -> None:
        """A value containing --- must not corrupt YAML frontmatter."""
        kwargs = _valid_kwargs(tmp_path)
        kwargs["rejection_reason"] = "---\nnew_key: injected"
        result = log_rejection(**kwargs)
        assert result.status == "pass"
        target = tmp_path / "raw" / "rejected" / f"test-source--{'a' * 8}.rejection.md"
        content = target.read_text()
        # YAML frontmatter must parse cleanly — no injected keys.
        end = content.find("\n---", 4)
        fm_text = content[4:end]
        parsed = yaml.safe_load(fm_text)
        assert "new_key" not in parsed


class TestSanitizeMarkdown:
    def test_frontmatter_terminator_escaped(self) -> None:
        result = _sanitize_markdown("---")
        assert "---" not in result.splitlines()

    def test_triple_dash_in_multiline_escaped(self) -> None:
        val = "Line 1\n---\nLine 3"
        result = _sanitize_markdown(val)
        assert "---\n" not in result

    def test_control_chars_stripped(self) -> None:
        result = _sanitize_markdown("hello\x01world")
        assert "\x01" not in result

    def test_normal_text_preserved(self) -> None:
        assert _sanitize_markdown("Missing provenance metadata") == "Missing provenance metadata"

    def test_length_cap(self) -> None:
        long_val = "x" * 3000
        assert len(_sanitize_markdown(long_val)) <= 2000
